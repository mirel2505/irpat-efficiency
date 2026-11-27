"""Local journal of observed source mode transitions, without device commands."""
import asyncio
from datetime import timedelta
import logging

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .storage_identity import storage_key
from .event_journal import EventJournal
from .mode_history import observation, transition
from .topology import empty_topology

_LOGGER = logging.getLogger(__name__)


class ModeMonitor:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, 1, storage_key(entry, "modes"))
        self.journal = EventJournal(self.store, "observed_at", 3000)
        self.previous = {}
        self.last_sample = None
        self.cancel = None
        self.closed = False
        self.lock = asyncio.Lock()

    async def async_start(self):
        await self.journal.async_load()
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
                    self.journal.append({"source_id": sid, **event})
                current[sid] = obs
            self.previous = current
            try:
                await self.journal.async_flush(stamp)
            except Exception:
                _LOGGER.exception("Could not save reported mode observations")

    def overview(self, topology):
        return {sid: self.journal.overview(sid)
                for sid in (s['id'] for s in topology['sources'] if s.get('mode_binding'))}

    async def async_stop(self):
        self.closed = True
        if self.cancel:
            self.cancel()
            self.cancel = None
        async with self.lock:
            try:
                await self.journal.async_flush(dt_util.utcnow().timestamp())
            except Exception:
                _LOGGER.exception("Final mode journal save failed; pending observations may be lost")
