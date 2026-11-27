"""Optional local defrost monitor with bounded completed-event history."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import logging

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .defrost import enabled_sources, observe
from .telemetry_reader import read_telemetry
from .topology import empty_topology

_LOGGER = logging.getLogger(__name__)


class DefrostMonitor:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, 1, f"{DOMAIN}.defrost.{entry.entry_id}")
        self.events = []
        self.states = {}
        self.signatures = {}
        self.cancel = None
        self.lock = asyncio.Lock()
        self.closed = False
        self.dirty = False
        self.save_failed = False

    async def async_start(self):
        stored = await self.store.async_load()
        if stored is not None:
            if not isinstance(stored, dict) or not isinstance(stored.get("events"), list):
                raise ValueError("invalid_defrost_history")
            self.events = stored["events"]
        self.cancel = async_track_time_interval(self.hass, self.async_sample, timedelta(seconds=30))

    async def async_sample(self, now):
        async with self.lock:
            if self.closed:
                return
            topology = self.entry.options.get("topology", empty_topology())
            enabled = enabled_sources(topology)
            stamp = dt_util.utcnow().timestamp()
            readings = read_telemetry(self.hass, topology) if enabled else []
            index = {(s["owner_id"], s["role"]): s for s in readings if s["group"] == "sources"}
            for sid in set(self.states) - enabled:
                self.states.pop(sid, None)
                self.signatures.pop(sid, None)
            for source in topology["sources"]:
                sid = source["id"]
                if sid not in enabled:
                    continue
                roles = ("defrost", "electrical_energy", "supply_temperature")
                signature = tuple(index.get((sid, role), {}).get("entity_id") for role in roles)
                if self.signatures.get(sid) != signature:
                    self.states.pop(sid, None)
                    self.signatures[sid] = signature
                def value(role):
                    reading = index.get((sid, role), {})
                    return reading.get("value") if reading.get("status") == "reported" else None
                state, event = observe(self.states.get(sid), {
                    "timestamp": stamp, "active": value("defrost"),
                    "electric_kwh": value("electrical_energy"), "supply_c": value("supply_temperature"),
                }, boundary_confirmed=source.get("energy_boundary_confirmed") is True)
                self.states[sid] = state
                if event:
                    self.events.append({"source_id": sid, **event})
                    self.dirty = True
            kept = [e for e in self.events if e["end"] >= stamp-30*86400][-2000:]
            if len(kept) != len(self.events):
                self.events = kept
                self.dirty = True
            if self.dirty:
                try:
                    await self.store.async_save({"events": deepcopy(self.events)})
                    self.dirty = self.save_failed = False
                except Exception:
                    self.save_failed = True
                    _LOGGER.exception("Could not save defrost observations")

    def overview(self, topology):
        return {sid: {"recent": deepcopy([e for e in self.events if e["source_id"] == sid][-20:]),
                      "save_failed": self.save_failed}
                for sid in enabled_sources(topology)}

    async def async_stop(self):
        self.closed = True
        if self.cancel:
            self.cancel()
            self.cancel = None
        async with self.lock:
            pass
