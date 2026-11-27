"""Read-only Home Assistant telemetry adapter."""
from homeassistant.util import dt as dt_util

from .telemetry import convert


def read_telemetry(hass, topology, max_age=900):
    """Expose report age and normalized values; reject stale/future reports."""
    now = dt_util.utcnow()
    result = []
    for binding in topology.get("telemetry", []):
        sample = {**binding, "value": None, "unit": None,
                  "timestamp": None, "age_seconds": None, "status": "unavailable"}
        state = hass.states.get(binding["entity_id"])
        if state is not None and state.state not in ("unknown", "unavailable"):
            reported = getattr(state, "last_reported", None) or state.last_updated
            age = (now - reported).total_seconds()
            value, unit = convert(binding["role"], state.state, state.attributes.get("unit_of_measurement"))
            sample.update(unit=unit, timestamp=reported.timestamp(), age_seconds=age)
            if not 0 <= age <= max_age:
                sample["status"] = "stale"
            elif value is None:
                sample["status"] = "invalid"
            else:
                sample.update(value=value, status="reported")
        result.append(sample)
    return result
