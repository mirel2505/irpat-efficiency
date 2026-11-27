"""Topology-aware, descriptive thermal diagnostics."""
from datetime import datetime
from .calculations import balancing_capability
from .history import bucket
from .thermal_balance import analyze_zone
from .stability import stability
from .topology import temperature_conflicts


def zone_diagnostics(topology, series, now, journal, configuration_since, mode):
    """Use only samples collected under the current configuration."""
    end = bucket(now)
    start = end - 86400
    zones = {z["id"]: z for z in topology["zones"]}
    manifolds = {m["id"]: m["zone_id"] for m in topology["manifolds"]}
    room_zones = {}
    for circuit in topology["circuits"]:
        room = circuit.get("room_id")
        zone = manifolds.get(circuit["manifold_id"])
        if room and zone in zones:
            room_zones.setdefault(room, set()).add(zone)
    conflicts = temperature_conflicts(topology)
    results = {}
    for zid, zone in zones.items():
        rooms = [{"id": r["id"], "area_m2": r.get("area_m2"),
                  "target_c": r.get(f"{mode}_target_c")}
                 for r in topology["rooms"] if room_zones.get(r["id"]) == {zid}]
        shared = [rid for rid, membership in room_zones.items()
                  if zid in membership and len(membership) > 1]
        duplicate_sensors = bool(conflicts.intersection(r["id"] for r in rooms))
        capability = balancing_capability(zone["operating_mode"], zone["circuit_control"])
        adjustments = [datetime.fromisoformat(item["timestamp"]).timestamp()
                       for item in journal if manifolds.get(item["manifold_id"]) == zid
                       and item["phase"] in ("before", "after")]
        last = max(adjustments, default=None)
        if configuration_since is None or configuration_since > start:
            result = {"status": "configuration_collecting", "rooms": {}, "coverage": 0}
        elif shared:
            result = {"status": "shared_rooms", "rooms": {}, "coverage": 0}
        elif duplicate_sensors:
            result = {"status": "duplicate_temperature_sensor", "rooms": {}, "coverage": 0}
        else:
            result = analyze_zone(rooms, series, start, end,
                                  eligible=capability != "monitor_only", last_adjustment=last)
        result["stability"] = stability(
            rooms, series, end, eligible=capability != "monitor_only" and not shared and not duplicate_sensors,
            configuration_since=configuration_since, last_adjustment=last,
        )
        result.update(zone_id=zid, name=zone["name"], capability=capability,
                      shared_room_ids=shared, mode=mode, window_hours=24,
                      advisory_only=True)
        results[zid] = result
    return results
