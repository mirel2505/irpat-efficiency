"""Read-only registry import, preserving local identity and manual settings."""
from copy import deepcopy

from .topology import add_item, TopologyError
from .telemetry import set_binding


def _link(data, group, key, native_id, name, floor_id=None):
    """Reuse stable native ID, or one unambiguous matching manual object."""
    linked = [x for x in data[group] if x.get(key) == native_id]
    if len(linked) > 1:
        raise TopologyError("registry_conflict")
    if linked:
        return data, linked[0]["id"]
    matches = [x for x in data[group] if x["name"].strip().casefold() == name.strip().casefold()
               and (group == "floors" or x["floor_id"] == floor_id)]
    if matches:
        if len(matches) != 1 or matches[0].get(key):
            raise TopologyError("registry_conflict")
        data = deepcopy(data)
        item = next(x for x in data[group] if x["id"] == matches[0]["id"])
        item[key] = native_id
        return data, item["id"]
    fields = {"floor_id": floor_id} if group == "rooms" else {}
    data, identifier = add_item(data, group, name, **fields)
    data[group][-1][key] = native_id
    return data, identifier


def import_floor(topology, floors, native_id):
    if native_id not in floors:
        raise TopologyError("invalid_reference")
    return _link(topology, "floors", "ha_floor_id", native_id, floors[native_id])


def import_room(topology, floors, areas, native_id, fallback=None):
    if native_id not in areas:
        raise TopologyError("invalid_reference")
    area = areas[native_id]
    # A previously linked room is never moved or renamed by reimport.
    existing = [x for x in topology["rooms"] if x.get("ha_area_id") == native_id]
    if existing:
        if len(existing) != 1:
            raise TopologyError("registry_conflict")
        return topology, existing[0]["id"]
    if area.get("floor_id") in floors:
        topology, floor_id = import_floor(topology, floors, area["floor_id"])
    else:
        floor_id = fallback
        if not any(x["id"] == floor_id for x in topology["floors"]):
            raise TopologyError("registry_floor_required")
    return _link(topology, "rooms", "ha_area_id", native_id, area["name"], floor_id)


def import_all(topology, floors, areas, fallback=None):
    """Atomic import; unassigned areas require an explicit fallback floor."""
    data = deepcopy(topology)
    for native_id in floors:
        data, _ = import_floor(data, floors, native_id)
    for native_id in areas:
        if (areas[native_id].get("floor_id") not in floors and fallback is None
                and not any(x.get("ha_area_id") == native_id for x in data["rooms"])):
            continue
        data, _ = import_room(data, floors, areas, native_id, fallback)
    return data


def sensor_candidates(topology, room_id, entities):
    """Filter already used entities; never replace existing humidity automatically."""
    room = next((x for x in topology["rooms"] if x["id"] == room_id), None)
    if not room or not room.get("ha_area_id"):
        raise TopologyError("invalid_reference")
    used = {x["entity_id"] for x in topology["bindings"] + topology.get("telemetry", [])}
    used.add(topology.get("outdoor_entity_id"))
    humidity_set = any(x["group"] == "rooms" and x["owner_id"] == room_id and x["role"] == "humidity"
                       for x in topology.get("telemetry", []))
    result = {"temperature": {}, "humidity": {}}
    for entity in entities:
        eid = entity["entity_id"]
        if entity["area_id"] != room["ha_area_id"] or eid in used or entity.get("disabled"):
            continue
        kind = entity.get("device_class")
        if eid.startswith("climate.") or (eid.startswith("sensor.") and kind == "temperature"):
            result["temperature"][eid] = entity["name"]
        elif eid.startswith("sensor.") and kind == "humidity" and not humidity_set:
            result["humidity"][eid] = entity["name"]
    return result


def confirm_sensors(topology, room_id, entities, temperatures, humidity=None):
    candidates = sensor_candidates(topology, room_id, entities)
    if not isinstance(temperatures, list) or len(set(temperatures)) != len(temperatures):
        raise TopologyError("invalid_entity")
    if not set(temperatures) <= candidates["temperature"].keys():
        raise TopologyError("invalid_entity")
    if humidity and humidity not in candidates["humidity"]:
        raise TopologyError("invalid_entity")
    data = deepcopy(topology)
    for eid in temperatures:
        data, _ = add_item(data, "bindings", candidates["temperature"][eid][:120],
                           room_id=room_id, entity_id=eid)
    if humidity:
        data = set_binding(data, "rooms", room_id, "humidity", humidity,
                           candidates["humidity"][humidity][:120])
    return data
