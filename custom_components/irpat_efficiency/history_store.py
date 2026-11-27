"""Local history collection independent of the browser panel."""
from datetime import timedelta
from copy import deepcopy
import asyncio
import logging

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .history import compare_room, record_samples
from .temperature_reader import read_rooms
from .topology import empty_topology
from .temperature import summarize_room

_LOGGER = logging.getLogger(__name__)
# Provisional HA state-report freshness limit; not device measurement age.
MAX_REPORT_AGE_SECONDS = 7200


class RoomHistory:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, 1, f"{DOMAIN}.history.{entry.entry_id}")
        self.data = {}
        self._cancel = None
        self._lock = asyncio.Lock()
        self._closed = False
        self.save_failed = False

    async def async_start(self):
        stored = await self.store.async_load()
        if stored is not None:
            if not isinstance(stored, dict) or not isinstance(stored.get("rooms"), dict):
                raise ValueError("Invalid irPaT history store")
            self.data = stored["rooms"]
        self._cancel = async_track_time_interval(self.hass, self.async_sample, timedelta(minutes=5))

    async def async_sample(self, now):
        async with self._lock:
            if self._closed:
                return
            topology = self.entry.options.get("topology", empty_topology())
            rooms = read_rooms(self.hass, topology)
            values = {}
            for identifier, room in rooms.items():
                fresh = [r for r in room["readings"]
                         if r.get("age_seconds") is not None
                         and r["age_seconds"] <= MAX_REPORT_AGE_SECONDS]
                # Do not average a changing subset of sensors in history.
                if fresh and len(fresh) == len(room["readings"]):
                    result = summarize_room(fresh)
                    if result["valid_count"] == len(fresh):
                        values[identifier] = result["temperature_c"]
            record_samples(self.data, dt_util.utcnow().timestamp(), values)
            try:
                await self.store.async_save({"rooms": deepcopy(self.data)})
                self.save_failed = False
            except Exception:
                self.save_failed = True
                _LOGGER.exception("Could not persist room history")

    def overview(self, topology):
        now = dt_util.utcnow().timestamp()
        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        if tz is None:
            return {}
        return {room["id"]: compare_room(self.data.get(room["id"], {}), now, tz)
                for room in topology["rooms"]}

    async def async_stop(self):
        self._closed = True
        if self._cancel:
            self._cancel()
            self._cancel = None
        async with self._lock:
            pass
