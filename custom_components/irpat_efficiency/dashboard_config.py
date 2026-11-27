"""Validated administrator configuration actions for the graphical setup."""
from copy import deepcopy
import hashlib
import json

from .topology import TopologyError, add_item, empty_topology
from .topology_edit import edit_item
from .topology_remove import remove_selection
from .registry_import import import_all, import_floor, import_room, _link, confirm_sensors
from .room_setup import room_candidates
from .ha_registry_reader import read_structure, read_entities
from .storage_identity import generation
from .temperature_reader import read_rooms, read_binding


def revision(entry):
    payload = [generation(entry), entry.options.get("topology", empty_topology())]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def temperature_entities(hass):
    """Include registered and unregistered temperature sensors, and thermostats."""
    entities = {e["entity_id"]: e for e in read_entities(hass)}
    for state in hass.states.async_all():
        entities.setdefault(state.entity_id, {
            "entity_id": state.entity_id, "name": state.name,
            "area_id": None, "device_class": state.attributes.get("device_class"),
            "disabled": False})
    result = {}
    for eid, item in entities.items():
        if item.get("disabled"):
            continue
        state = hass.states.get(eid)
        unit = state.attributes.get("unit_of_measurement") if state else None
        if eid.startswith(("climate.", "weather.")) or (eid.startswith("sensor.") and
                (item.get("device_class") == "temperature" or unit in ("°C", "°F", "K", "C", "F"))):
            result[eid] = {**item, "temperature_c": read_binding(hass, item)["temperature_c"]}
    return result


def snapshot(hass, entry):
    topology = entry.options.get("topology", empty_topology())
    floors, areas = read_structure(hass)
    return {"revision": revision(entry), "topology": topology,
            "native_floors": floors, "native_areas": areas,
            "entities": list(temperature_entities(hass).values()),
            "room_temperatures": read_rooms(hass, topology)}


def _room_fields(payload):
    return {k: payload[k] for k in ("area_m2", "heating_target_c", "cooling_target_c") if k in payload}


def apply_action(hass, topology, action, p):
    """Apply a single confirmed action; no service calls or registry writes."""
    data = deepcopy(topology)
    if action == "import":
        floors, areas = read_structure(hass)
        fallback = p.get("fallback_floor")
        selected = p.get("area_ids")
        if selected is not None and (not isinstance(selected, list) or len(set(selected)) != len(selected)
                                     or not set(selected) <= areas.keys()):
            raise TopologyError("invalid_reference")
        if p.get("single_native_floor"):
            data, fallback = import_floor(data, floors, p["single_native_floor"])
        elif p.get("fallback_name"):
            name = p["fallback_name"]
            if not isinstance(name, str):
                raise TopologyError("invalid_name")
            same = [f for f in data["floors"] if f["name"].casefold() == name.strip().casefold()]
            if len(same) == 1:
                fallback = same[0]["id"]
            elif not same:
                data, fallback = add_item(data, "floors", name)
            else:
                raise TopologyError("registry_conflict")
        if p.get("single_floor") is True:
            if not any(f["id"] == fallback for f in data["floors"]):
                raise TopologyError("invalid_reference")
            for aid in selected if selected is not None else areas:
                linked = next((r for r in data["rooms"] if r.get("ha_area_id") == aid), None)
                if linked:
                    linked["floor_id"] = fallback
                else:
                    data, _ = _link(data, "rooms", "ha_area_id", aid, areas[aid]["name"], fallback)
        elif selected is not None:
            for aid in selected:
                if areas[aid].get("floor_id") not in floors and not fallback:
                    continue
                data, _ = import_room(data, floors, areas, aid, fallback)
        else:
            data = import_all(data, floors, areas, fallback)
        entities = list(temperature_entities(hass).values())
        for room in data["rooms"]:
            _, preferred = room_candidates(hass, data, room, entities)
            if preferred:
                data = confirm_sensors(data, room["id"], entities, preferred)
        return data
    if action == "merge_floor":
        if p.get("confirmed") is not True or p["id"] == p["target_id"]:
            raise TopologyError("invalid_reference")
        if not {p["id"], p["target_id"]} <= {f["id"] for f in data["floors"]}:
            raise TopologyError("invalid_reference")
        for group in ("rooms", "manifolds"):
            for item in data[group]:
                if item["floor_id"] == p["id"]:
                    item["floor_id"] = p["target_id"]
        return remove_selection(data, "floors", [p["id"]], confirmed=True)
    if action == "move_room":
        room = next((r for r in data["rooms"] if r["id"] == p["id"]), None)
        if not room or not any(f["id"] == p["floor_id"] for f in data["floors"]):
            raise TopologyError("invalid_reference")
        room["floor_id"] = p["floor_id"]
        return data
    if action == "targets":
        mode = p["mode"]
        if mode not in ("heating", "cooling"):
            raise TopologyError("invalid_mode")
        ids = p.get("room_ids")
        if not isinstance(ids, list) or not ids or not set(ids) <= {r["id"] for r in data["rooms"]}:
            raise TopologyError("invalid_reference")
        for room in list(data["rooms"]):
            if room["id"] in ids:
                data = edit_item(data, "rooms", room["id"], room["name"], **{mode+"_target_c": p["value"]})
        return data
    if action == "zone_settings":
        zone = next((z for z in data["zones"] if z["id"] == p["id"]), None)
        if not zone:
            raise TopologyError("invalid_reference")
        return edit_item(data, "zones", zone["id"], zone["name"],
                         operating_mode=p["operating_mode"], circuit_control=p["circuit_control"])
    if action == "add_floor":
        return add_item(data, "floors", p["name"])[0]
    if action == "add_room":
        return add_item(data, "rooms", p["name"], floor_id=p["floor_id"], **_room_fields(p))[0]
    if action == "edit_room":
        return edit_item(data, "rooms", p["id"], p["name"], **_room_fields(p))
    if action == "rename":
        if p["collection"] not in ("floors", "zones", "sources", "manifolds"):
            raise TopologyError("invalid_reference")
        return edit_item(data, p["collection"], p["id"], p["name"])
    if action == "bind":
        entity = temperature_entities(hass).get(p["entity_id"])
        if not entity or not p["entity_id"].startswith(("sensor.", "climate.")):
            raise TopologyError("invalid_entity")
        if any(b["entity_id"] == p["entity_id"] for b in data.get("telemetry", [])):
            raise TopologyError("duplicate_entity")
        return add_item(data, "bindings", entity["name"][:120], room_id=p["room_id"],
                        entity_id=p["entity_id"])[0]
    if action == "outdoor":
        eid = p.get("entity_id")
        if not eid:
            data.pop("outdoor_entity_id", None)
        elif eid not in temperature_entities(hass) or not eid.startswith(("sensor.", "weather.")):
            raise TopologyError("invalid_entity")
        elif any(b["entity_id"] == eid for b in data["bindings"] + data.get("telemetry", [])):
            raise TopologyError("duplicate_entity")
        else:
            data["outdoor_entity_id"] = eid
        return data
    if action == "add_zone":
        return add_item(data, "zones", p["name"])[0]
    if action == "add_manifold":
        count = p["count"]
        if type(count) is not int or not 1 <= count <= 100:
            raise TopologyError("invalid_position")
        zone_id = p.get("zone_id")
        if not zone_id and not data["zones"]:
            data, zone_id = add_item(data, "zones", p["zone_name"])
        data, mid = add_item(data, "manifolds", p["name"], floor_id=p["floor_id"], zone_id=zone_id)
        for position in range(1, count + 1):
            data, _ = add_item(data, "circuits", str(position), manifold_id=mid, position=position)
        return data
    if action == "add_circuit":
        return add_item(data, "circuits", str(p["position"]), manifold_id=p["manifold_id"],
                        position=p["position"])[0]
    if action == "map_circuit":
        old = next((c for c in data["circuits"] if c["id"] == p["id"]), None)
        if old is None:
            raise TopologyError("invalid_reference")
        room_id = p.get("room_id") or None
        if old.get("room_id") == room_id:
            return data
        # A different physical association gets a new identity. Prior journal
        # records remain archived and are never attributed to the new room.
        data = remove_selection(data, "circuits", [old["id"]], confirmed=True)
        return add_item(data, "circuits", old["name"], manifold_id=old["manifold_id"],
                        position=old["position"], room_id=room_id, length_m=old.get("length_m"))[0]
    if action == "add_source":
        zones = p.get("zone_ids", [])
        if not isinstance(zones, list):
            raise TopologyError("invalid_reference")
        return add_item(data, "sources", p["name"], source_type=p["source_type"], zone_ids=zones)[0]
    if action == "remove":
        if p.get("confirmed") is not True:
            raise TopologyError("remove_confirmation_required")
        return remove_selection(data, p["collection"], [p["id"]], confirmed=True,
                                detach_zone_sources=p.get("detach_zone_sources", False))
    raise TopologyError("invalid_reference")
