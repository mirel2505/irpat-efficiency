"""Versioned topology model, independent of Home Assistant."""
from __future__ import annotations

from copy import deepcopy
import math
from uuid import uuid4

from .const import OPERATING_MODES, CIRCUIT_CONTROLS

SCHEMA_VERSION = 1
COLLECTIONS = ("floors", "zones", "sources", "rooms", "manifolds", "circuits", "bindings")
SOURCE_TYPES = ("heat_pump", "gas", "electric", "biomass", "district", "hybrid", "other", "unintegrated")


class TopologyError(ValueError):
    """Invalid topology or reference."""


def empty_topology() -> dict:
    return {"schema_version": SCHEMA_VERSION, **{key: [] for key in COLLECTIONS}}


def _name(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 120:
        raise TopologyError("invalid_name")
    return value.strip()


def _reference(data: dict, collection: str, identifier: str) -> None:
    if not any(item["id"] == identifier for item in data[collection]):
        raise TopologyError("invalid_reference")


def _positive(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise TopologyError("invalid_number")
    return float(value)


def _temperature(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 5 <= value <= 40:
        raise TopologyError("invalid_number")
    return float(value)


def add_item(topology: dict, collection: str, name: str, **fields) -> tuple[dict, str]:
    """Return a new topology with a validated item, leaving input untouched."""
    if topology.get("schema_version") != SCHEMA_VERSION or collection not in COLLECTIONS:
        raise TopologyError("invalid_schema")
    data = deepcopy(topology)
    item = {"id": uuid4().hex, "name": _name(name)}
    if collection == "floors":
        pass
    elif collection == "zones":
        mode = fields.get("operating_mode", "unknown")
        control = fields.get("circuit_control", "unknown")
        if mode not in OPERATING_MODES or control not in CIRCUIT_CONTROLS:
            raise TopologyError("invalid_mode")
        item.update(operating_mode=mode, circuit_control=control)
    elif collection == "sources":
        kind = fields.get("source_type", "unintegrated")
        if kind not in SOURCE_TYPES:
            raise TopologyError("invalid_source")
        zones = fields.get("zone_ids", [])
        for zone_id in zones:
            _reference(data, "zones", zone_id)
        item.update(source_type=kind, zone_ids=list(dict.fromkeys(zones)))
    elif collection == "rooms":
        floor = fields.get("floor_id")
        _reference(data, "floors", floor)
        item.update(floor_id=floor, area_m2=_positive(fields.get("area_m2")),
                    heating_target_c=_temperature(fields.get("heating_target_c")),
                    cooling_target_c=_temperature(fields.get("cooling_target_c")))
    elif collection == "manifolds":
        floor = fields.get("floor_id")
        zone = fields.get("zone_id")
        _reference(data, "floors", floor)
        _reference(data, "zones", zone)
        item.update(floor_id=floor, zone_id=zone)
    elif collection == "circuits":
        manifold = fields.get("manifold_id")
        room = fields.get("room_id")
        position = fields.get("position")
        _reference(data, "manifolds", manifold)
        if room is not None:
            _reference(data, "rooms", room)
        if isinstance(position, bool) or not isinstance(position, int) or position < 1:
            raise TopologyError("invalid_position")
        if any(c["manifold_id"] == manifold and c["position"] == position for c in data["circuits"]):
            raise TopologyError("duplicate_position")
        item.update(manifold_id=manifold, room_id=room, position=position,
                    length_m=_positive(fields.get("length_m")))
    elif collection == "bindings":
        room = fields.get("room_id")
        entity = fields.get("entity_id")
        _reference(data, "rooms", room)
        if not isinstance(entity, str) or not entity.startswith(("sensor.", "climate.")):
            raise TopologyError("invalid_entity")
        if entity == data.get("outdoor_entity_id") or any(b["entity_id"] == entity for b in data["bindings"]):
            raise TopologyError("duplicate_entity")
        item.update(room_id=room, entity_id=entity,
                    attribute="current_temperature" if entity.startswith("climate.") else None)
    data[collection].append(item)
    return data, item["id"]


def rename_item(topology: dict, collection: str, identifier: str, name: str) -> dict:
    """Rename an item without changing its identity or references."""
    if collection not in COLLECTIONS:
        raise TopologyError("invalid_schema")
    _reference(topology, collection, identifier)
    data = deepcopy(topology)
    for item in data[collection]:
        if item["id"] == identifier:
            item["name"] = _name(name)
            break
    return data


def temperature_conflicts(topology: dict) -> set[str]:
    """Rooms whose temperature readings are not independent of other rooms/outdoors."""
    owners = {}
    conflicts = set()
    for binding in topology.get("bindings", []):
        entity, room = binding["entity_id"], binding["room_id"]
        if entity == topology.get("outdoor_entity_id"):
            conflicts.add(room)
        if entity in owners:
            conflicts.update((owners[entity], room))
        owners[entity] = room
    return conflicts
