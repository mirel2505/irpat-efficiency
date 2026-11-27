"""Read-only optional electricity meter collection."""
import logging

from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .storage_identity import storage_key
from .energy_store import EnergyStore
from .fuel_monitor import FuelMonitor
from .mode_history import observation
from .paired_energy import pair_signature
from .source_settings import estimate_cost
from .telemetry_reader import read_telemetry
from .topology import empty_topology

_LOGGER = logging.getLogger(__name__)


class EnergyMonitor:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.history = EnergyStore(Store(hass, 1, storage_key(entry, "energy")))
        self.fuel = FuelMonitor(hass, entry)
        self.fuel_save_failed = False
        self.cancel = None
        self.save_failed = False

    @staticmethod
    def meter_samples(topology, telemetry):
        sources = {s["id"] for s in topology["sources"]}
        fuel_meters = {s.get("fuel", {}).get("meter_entity") for s in topology["sources"]}
        return {s["owner_id"]: {**s, "pair_signature": pair_signature(topology, s["owner_id"]),
                                **({"blocked": True} if s["entity_id"] in fuel_meters else {})}
                for s in telemetry
                if s["group"] == "sources" and s["role"] == "electrical_energy"
                and s["owner_id"] in sources}

    async def async_start(self):
        await self.history.async_load()
        await self.fuel.history.async_load()
        self.cancel = async_track_utc_time_change(
            self.hass, self.async_sample, minute=range(0, 60, 5), second=0)

    async def async_sample(self, now):
        topology = self.entry.options.get("topology", empty_topology())
        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        if tz is None:
            return
        telemetry = read_telemetry(self.hass, topology)
        samples = self.meter_samples(topology, telemetry)
        thermal = {s["owner_id"]: s for s in telemetry
                   if s["group"] == "sources" and s["role"] == "thermal_power"}
        for source in topology["sources"]:
            sid = source["id"]
            binding = source.get("mode_binding")
            if sid not in samples or not binding or source.get("source_type") != "heat_pump":
                continue
            state = self.hass.states.get(binding["entity_id"])
            mode = None
            if state is not None:
                reported = getattr(state, "last_reported", None) or state.last_updated
                mode = observation(binding, state.state, state.last_changed.timestamp(),
                                   reported.timestamp(), dt_util.utcnow().timestamp())
            samples[sid]["pair"] = {
                "confirmed": samples[sid]["pair_signature"] is not None,
                "thermal": thermal.get(sid), "mode": mode,
            }
        try:
            await self.history.async_sample(samples, dt_util.utcnow().timestamp(), tz)
            self.save_failed = False
        except Exception:
            self.save_failed = True
            _LOGGER.exception("Could not persist energy history")
        try:
            stamp = dt_util.utcnow().timestamp()
            await self.fuel.history.async_sample(self.fuel.samples(topology, stamp), stamp, tz)
            self.fuel_save_failed = False
        except Exception:
            self.fuel_save_failed = True
            _LOGGER.exception("Could not persist fuel history")

    def overview(self, topology, telemetry):
        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        if tz is None:
            return {}
        samples = self.meter_samples(topology, telemetry)
        try:
            result = self.history.overview(samples, dt_util.utcnow().timestamp(), tz)
            for source in topology["sources"]:
                for row in result.get(source["id"], {}).values():
                    row["current_tariff_cost"] = estimate_cost(row["electric_kwh"], source)
            return result
        except ValueError:
            return {}

    async def async_stop(self):
        if self.cancel:
            self.cancel()
            self.cancel = None
        await self.history.async_close()
        await self.fuel.history.async_close()
