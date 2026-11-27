"""Read-only optional electricity meter collection."""
from datetime import timedelta
import logging

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .energy_store import EnergyStore
from .source_settings import estimate_cost
from .telemetry_reader import read_telemetry
from .topology import empty_topology

_LOGGER = logging.getLogger(__name__)


class EnergyMonitor:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.history = EnergyStore(Store(hass, 1, f"{DOMAIN}.energy.{entry.entry_id}"))
        self.cancel = None
        self.save_failed = False

    @staticmethod
    def meter_samples(topology, telemetry):
        sources = {s["id"] for s in topology["sources"]}
        return {s["owner_id"]: s for s in telemetry
                if s["group"] == "sources" and s["role"] == "electrical_energy"
                and s["owner_id"] in sources}

    async def async_start(self):
        await self.history.async_load()
        self.cancel = async_track_time_interval(
            self.hass, self.async_sample, timedelta(minutes=5))

    async def async_sample(self, now):
        topology = self.entry.options.get("topology", empty_topology())
        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        if tz is None:
            return
        samples = self.meter_samples(topology, read_telemetry(self.hass, topology))
        try:
            await self.history.async_sample(samples, dt_util.utcnow().timestamp(), tz)
            self.save_failed = False
        except Exception:
            self.save_failed = True
            _LOGGER.exception("Could not persist energy history")

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
