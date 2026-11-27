"""Guided room configuration; explicit physical circuit mapping."""
from copy import deepcopy

from .registry_import import sensor_candidates, confirm_sensors
from .topology import TopologyError, add_item


def room_candidates(hass, topology, room, entities):
    """Suggest HA's designated room temperature, otherwise one unambiguous candidate."""
    if not room.get("ha_area_id"):
        return {"temperature": {}, "humidity": {}}, []
    candidates = sensor_candidates(topology, room["id"], entities)
    if any(b["room_id"] == room["id"] for b in topology["bindings"]):
        return candidates, []
    from homeassistant.helpers import area_registry as ar
    area = ar.async_get(hass).async_get_area(room["ha_area_id"])
    designated = area.temperature_entity_id if area else None
    if designated in candidates["temperature"]:
        return candidates, [designated]
    if len(candidates["temperature"]) == 1:
        return candidates, list(candidates["temperature"])
    return candidates, []


def parse_positions(count, positions):
    """Count refers only to additional circuits. Never guess physical positions."""
    if isinstance(count, bool) or not isinstance(count, (int, float)) or not 0 <= count <= 100 or int(count) != count:
        raise TopologyError("invalid_position")
    if not count:
        if positions and positions.strip():
            raise TopologyError("invalid_position")
        return []
    try:
        values = [int(x.strip()) for x in positions.split(",")]
    except (ValueError, AttributeError):
        raise TopologyError("invalid_position") from None
    if len(values) != count or len(set(values)) != count or any(not 1 <= v <= 1000 for v in values):
        raise TopologyError("invalid_position")
    return values


def complete_room(topology, room_id, entities, *, temperatures=None, humidity=None,
                  manual_temperature=None, manifold_id=None, count=0, positions=None):
    """Apply all selected sensors and newly mapped circuits atomically."""
    room = next((r for r in topology["rooms"] if r["id"] == room_id), None)
    if room is None:
        raise TopologyError("invalid_reference")
    data = deepcopy(topology)
    if room.get("ha_area_id"):
        data = confirm_sensors(data, room_id, entities, temperatures or [], humidity)
    elif temperatures or humidity:
        raise TopologyError("invalid_entity")
    if manual_temperature:
        if any(b["entity_id"] == manual_temperature for b in data.get("telemetry", [])):
            raise TopologyError("duplicate_entity")
        data, _ = add_item(data, "bindings", manual_temperature[:120],
                           room_id=room_id, entity_id=manual_temperature)
    values = parse_positions(count, positions)
    if values and not any(m["id"] == manifold_id for m in data["manifolds"]):
        raise TopologyError("invalid_reference")
    for position in values:
        suffix = f" · {position}"
        data, _ = add_item(data, "circuits", room["name"][:120-len(suffix)] + suffix,
                           room_id=room_id, manifold_id=manifold_id, position=position)
    return data
