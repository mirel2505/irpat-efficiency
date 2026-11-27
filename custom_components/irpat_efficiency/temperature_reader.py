"""Read selected HA states; never send device commands."""
from homeassistant.util import dt as dt_util

from .temperature import summarize_room, temperature_c

# Provisional freshness limit for HA reports, not physical measurement age.
MAX_REPORT_AGE_SECONDS = 7200


def read_binding(hass, binding):
    """Return a snapshot with source timestamp and explicit failure reason."""
    entity_id = binding["entity_id"]
    state = hass.states.get(entity_id)
    reading = {"entity_id": entity_id, "name": binding["name"],
               "temperature_c": None, "reported_at": None, "status": "unavailable"}
    if state is None or state.state in ("unknown", "unavailable"):
        return reading
    reported = getattr(state, "last_reported", None) or state.last_updated
    reading["reported_at"] = reported.isoformat()
    age = (dt_util.utcnow() - reported).total_seconds()
    reading["age_seconds"] = age
    if age < 0 or age > MAX_REPORT_AGE_SECONDS:
        reading["status"] = "future" if age < 0 else "stale"
        return reading
    if entity_id.startswith("climate."):
        value = state.attributes.get("current_temperature")
        unit = state.attributes.get("temperature_unit") or hass.config.units.temperature_unit
    else:
        value = state.state
        unit = state.attributes.get("unit_of_measurement")
    reading["temperature_c"] = temperature_c(value, unit)
    reading["status"] = "reported" if reading["temperature_c"] is not None else "invalid"
    return reading


def read_rooms(hass, topology):
    """Read all configured rooms once; a room is never counted per circuit."""
    readings = {}
    for binding in topology["bindings"]:
        readings.setdefault(binding["room_id"], []).append(read_binding(hass, binding))
    result = {}
    for room in topology["rooms"]:
        samples = readings.get(room["id"], [])
        result[room["id"]] = {
            "readings": samples,
            "heating": summarize_room(samples, room.get("heating_target_c")),
            "cooling": summarize_room(samples, room.get("cooling_target_c")),
        }
    return result
