"""Local history collection independent of the browser panel."""
from datetime import timedelta
import asyncio
import logging
import hashlib
import json

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .storage_identity import storage_key
from .history import compare_room
from .history_persistence import current_series, save_sample
from .temperature_reader import MAX_REPORT_AGE_SECONDS, read_rooms, read_binding
from .topology import empty_topology
from .temperature import summarize_room
from .zone_analysis import zone_diagnostics
from .thermal_review import zone_weather
from .balance_advice import recommendations

OUTDOOR_KEY = "__outdoor__"

_LOGGER = logging.getLogger(__name__)


class RoomHistory:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, 1, storage_key(entry, "history"))
        self.data = {}
        self._cancel = None
        self._lock = asyncio.Lock()
        self._closed = False
        self.save_failed = False
        self.configuration_hash = None
        self.configuration_since = None

    @staticmethod
    def fingerprint(topology):
        return hashlib.sha256(json.dumps(topology, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def diagnostics(self, topology, journal):
        since = self.configuration_since if self.configuration_hash == self.fingerprint(topology) else None
        if self.save_failed:
            since = None
        now = dt_util.utcnow().timestamp()
        return {mode: zone_diagnostics(topology, self.data, now, journal, since, mode)
                for mode in ("heating", "cooling")}

    def advice(self, topology, journal):
        since = self.configuration_since if self.configuration_hash == self.fingerprint(topology) and not self.save_failed else None
        return recommendations(topology, self.data, dt_util.utcnow().timestamp(), journal, since)

    def outdoor_overview(self, topology):
        entity_id = topology.get("outdoor_entity_id")
        if not entity_id:
            return None
        reading = read_binding(self.hass, {"entity_id": entity_id, "name": "Outdoor"})
        state = self.hass.states.get(entity_id)
        if state:
            reading["name"] = state.name
        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        current = current_series(self.data, self.configuration_hash, self.configuration_since, self.fingerprint(topology))
        return {"reading": reading, "history": compare_room(current.get(OUTDOOR_KEY, {}), dt_util.utcnow().timestamp(), tz) if tz else {}}

    def weather_observations(self, topology):
        """Produce unreviewed, synchronized weather summaries per zone."""
        if self.save_failed or self.configuration_hash != self.fingerprint(topology):
            return {}
        return zone_weather(topology, self.data, dt_util.utcnow().timestamp(),
                            self.configuration_since)

    async def async_start(self):
        stored = await self.store.async_load()
        if stored is not None:
            if not isinstance(stored, dict) or not isinstance(stored.get("rooms"), dict):
                raise ValueError("Invalid irPaT history store")
            self.data = stored["rooms"]
            self.configuration_hash = stored.get("configuration_hash")
            self.configuration_since = stored.get("configuration_since")
        self._cancel = async_track_time_interval(self.hass, self.async_sample, timedelta(minutes=5))

    async def async_sample(self, now):
        async with self._lock:
            if self._closed:
                return
            topology = self.entry.options.get("topology", empty_topology())
            fingerprint = self.fingerprint(topology)
            rooms = read_rooms(self.hass, topology)
            values = {}
            for identifier, room in rooms.items():
                fresh = [r for r in room["readings"]
                         if r.get("status") == "reported" and r.get("age_seconds") is not None
                         and 0 <= r["age_seconds"] <= MAX_REPORT_AGE_SECONDS]
                # Do not average a changing subset of sensors in history.
                if fresh and len(fresh) == len(room["readings"]):
                    result = summarize_room(fresh)
                    if result["valid_count"] == len(fresh):
                        values[identifier] = result["temperature_c"]
            entity_id = topology.get("outdoor_entity_id")
            if entity_id:
                reading = read_binding(self.hass, {"entity_id": entity_id, "name": "Outdoor"})
                if (reading.get("status") == "reported" and reading.get("age_seconds") is not None
                        and 0 <= reading["age_seconds"] <= MAX_REPORT_AGE_SECONDS
                        and reading["temperature_c"] is not None):
                    values[OUTDOOR_KEY] = reading["temperature_c"]
            try:
                saved = await save_sample(self.store, self.data, self.configuration_hash,
                                          self.configuration_since, fingerprint,
                                          dt_util.utcnow().timestamp(), values)
                self.data = saved["rooms"]
                self.configuration_hash = saved["configuration_hash"]
                self.configuration_since = saved["configuration_since"]
                self.save_failed = False
            except Exception:
                self.save_failed = True
                _LOGGER.exception("Could not persist room history")

    def overview(self, topology):
        now = dt_util.utcnow().timestamp()
        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        if tz is None:
            return {}
        series = current_series(self.data, self.configuration_hash,
                                self.configuration_since, self.fingerprint(topology))
        return {room["id"]: compare_room(series.get(room["id"], {}), now, tz)
                for room in topology["rooms"]}

    async def async_stop(self):
        self._closed = True
        if self._cancel:
            self._cancel()
            self._cancel = None
        async with self._lock:
            pass
