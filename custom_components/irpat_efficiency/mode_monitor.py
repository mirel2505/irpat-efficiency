"""Local journal of observed source mode transitions, without device commands."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import logging

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .mode_history import observation, transition
from .topology import empty_topology

_LOGGER = logging.getLogger(__name__)


class ModeMonitor:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, 1, f"{DOMAIN}.modes.{entry.entry_id}")
        self.events = []
        self.previous = {}
        self.last_sample = None
        self.cancel = None
        self.closed = False
        self.lock = asyncio.Lock()
        self.save_failed = False
        self.dirty = False

    async def async_start(self):
        saved = await self.store.async_load()
        if saved is not None:
            if not isinstance(saved, dict) or not isinstance(saved.get("events"), list):
                raise ValueError("invalid_mode_history")
            self.events = saved["events"]
        self.cancel = async_track_time_interval(self.hass, self.async_sample, timedelta(seconds=30))

    async def async_sample(self, now):
        async with self.lock:
            if self.closed:
                return
            stamp = dt_util.utcnow().timestamp()
            if self.last_sample is not None and not 0 < stamp-self.last_sample <= 90:
                self.previous.clear()
            self.last_sample = stamp
            topology = self.entry.options.get("topology", empty_topology())
            current = {}
            for source in topology["sources"]:
                binding = source.get("mode_binding")
                if not binding:
                    continue
                sid = source["id"]
                state = self.hass.states.get(binding["entity_id"])
                obs = None
                if state is not None:
                    reported = getattr(state, "last_reported", None) or state.last_updated
                    obs = observation(binding, state.state, state.last_changed.timestamp(),
                                      reported.timestamp(), stamp)
                event = transition(self.previous.get(sid), obs, stamp)
                if event:
                    self.events.append({"source_id": sid, **event})
                    self.dirty = True
                current[sid] = obs
            self.previous = current
            kept = [e for e in self.events if e["observed_at"] >= stamp-30*86400][-3000:]
            if len(kept) != len(self.events):
                self.events = kept
                self.dirty = True
            if self.dirty:
                try:
                    await self.store.async_save({"events": deepcopy(self.events)})
                    self.dirty = self.save_failed = False
                except Exception:
                    self.save_failed = True
                    _LOGGER.exception("Could not save reported mode observations")

    def overview(self, topology):
        return {s["id"]: {"recent": deepcopy([e for e in self.events if e["source_id"] == s["id"]][-20:]),
                          "save_failed": self.save_failed}
                for s in topology["sources"] if s.get("mode_binding")}

    async def async_stop(self):
        self.closed = True
        if self.cancel:
            self.cancel()
            self.cancel = None
        async with self.lock:
            pass
