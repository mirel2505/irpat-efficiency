"""Optional local defrost monitor with bounded completed-event history."""
import asyncio
from collections import Counter
from datetime import timedelta
import logging

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .storage_identity import storage_key
from .event_journal import EventJournal
from .defrost import enabled_sources, observe
from .telemetry_reader import read_telemetry
from .topology import empty_topology

_LOGGER = logging.getLogger(__name__)


class DefrostMonitor:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, 1, storage_key(entry, "defrost"))
        self.journal = EventJournal(self.store, "end", 2000)
        self.states = {}
        self.signatures = {}
        self.cancel = None
        self.lock = asyncio.Lock()
        self.closed = False

    async def async_start(self):
        await self.journal.async_load()
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
            meter_counts = Counter(b["entity_id"] for b in topology.get("telemetry", [])
                                   if b["group"] == "sources" and b["role"] == "electrical_energy")
            for sid in set(self.states) - enabled:
                self.states.pop(sid, None)
                self.signatures.pop(sid, None)
            for source in topology["sources"]:
                sid = source["id"]
                if sid not in enabled:
                    continue
                roles = ("defrost", "electrical_energy", "supply_temperature")
                signature = tuple(index.get((sid, role), {}).get("entity_id") for role in roles)
                confirmed = (source.get("energy_boundary_confirmed") is True
                             and signature[1] is not None and meter_counts[signature[1]] == 1)
                signature = (*signature, confirmed)
                if self.signatures.get(sid) != signature:
                    self.states.pop(sid, None)
                    self.signatures[sid] = signature
                def value(role):
                    reading = index.get((sid, role), {})
                    return (reading.get("value") if reading.get("status") == "reported"
                            and reading.get("timestamp") is not None
                            and 0 <= stamp-reading["timestamp"] <= 60 else None)
                state, event = observe(self.states.get(sid), {
                    "timestamp": stamp, "active": value("defrost"),
                    "electric_kwh": value("electrical_energy"), "supply_c": value("supply_temperature"),
                }, boundary_confirmed=confirmed)
                self.states[sid] = state
                if event:
                    self.journal.append({"source_id": sid, **event})
            try:
                await self.journal.async_flush(stamp)
            except Exception:
                _LOGGER.exception("Could not save defrost observations")

    def overview(self, topology):
        return {sid: self.journal.overview(sid)
                for sid in enabled_sources(topology)}

    async def async_stop(self):
        self.closed = True
        if self.cancel:
            self.cancel()
            self.cancel = None
        async with self.lock:
            try:
                await self.journal.async_flush(dt_util.utcnow().timestamp())
            except Exception:
                _LOGGER.exception("Final defrost journal save failed; pending observations may be lost")
