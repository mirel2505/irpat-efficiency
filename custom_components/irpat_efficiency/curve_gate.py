"""Shared source-level gate: balance first, then common temperature correction."""
from datetime import datetime
from .calculations import balancing_capability
from .topology import temperature_conflicts
from .weather_history import daily_observations, valid, DAY, SLOT

TOLERANCE = 0.3
EPS = 1e-9
SETTLING = 2 * DAY


def coupled_zones(topology, zone_id):
    """Transitive source links; unknown source assignment is conservatively shared."""
    all_zones = {z["id"] for z in topology["zones"]}
    links = [set(s.get("zone_ids", [])) & all_zones for s in topology.get("sources", [])]
    assigned = set().union(*links) if links else set()
    if assigned != all_zones:
        return all_zones
    group = {zone_id}
    while True:
        expanded = group.union(*(link for link in links if link & group))
        if expanded == group:
            return group
        group = expanded


def group_inputs(topology, zone_id, journal):
    """Return complete room membership and latest intervention for a source group."""
    zones = coupled_zones(topology, zone_id)
    if not zones or any(balancing_capability(z["operating_mode"], z["circuit_control"]) == "monitor_only"
                        for z in topology["zones"] if z["id"] in zones):
        return None, None
    mids = {m["id"]: m["zone_id"] for m in topology["manifolds"]}
    membership = {}
    for c in topology["circuits"]:
        zid = mids.get(c["manifold_id"])
        rid = c.get("room_id")
        if zid in zones and not rid:
            return None, None
        if rid and zid:
            membership.setdefault(rid, set()).add(zid)
    # A room with a configured heating target but no circuit cannot establish
    # complete balance. Do not silently exclude it from source recommendations.
    if any(valid(r.get("heating_target_c")) and not membership.get(r["id"])
           for r in topology["rooms"]):
        return None, None
    rooms = [dict(id=r["id"], area_m2=r.get("area_m2"), target_c=r.get("heating_target_c"))
             for r in topology["rooms"] if membership.get(r["id"], set()) & zones]
    ids = {r["id"] for r in rooms}
    bound = {b["room_id"] for b in topology["bindings"]}
    if (not rooms or not ids <= bound or ids & temperature_conflicts(topology)
            or any(len(membership[i]) != 1 for i in ids)
            or not all(valid(r["target_c"]) for r in rooms)
            or set().union(*(membership[i] for i in ids)) != zones
            or not topology.get("outdoor_entity_id")):
        return None, None
    relevant = [j for j in journal if mids.get(j["manifold_id"]) in zones]
    stamps = [datetime.fromisoformat(j["timestamp"]).timestamp() for j in relevant
              if j["phase"] in ("before", "after", "adjustment")]
    for mid in {j["manifold_id"] for j in relevant}:
        stamps.append(min(datetime.fromisoformat(j["timestamp"]).timestamp()
                          for j in relevant if j["manifold_id"] == mid))
    return rooms, max(stamps, default=None)


def balanced_day(row):
    return (row.get("coverage", 0) >= .9
            and valid(row.get("max_residual_c"))
            and row["max_residual_c"] <= TOLERANCE + EPS
            and row.get("relative_balance_fraction", 0) >= .95)


def common_sign(row):
    """Every room must be too warm or too cold relative to its own target."""
    errors = list(row.get("room_errors_c", {}).values())
    if errors and all(e > TOLERANCE + EPS for e in errors):
        return 1
    if errors and all(e < -TOLERANCE - EPS for e in errors):
        return -1
    return 0


def gate(topology, series, journal, zone_id, now, since):
    rooms, last = group_inputs(topology, zone_id, journal)
    if rooms is None or not valid(since):
        return "balance_data_required", None, rooms, last
    end = int(now) // SLOT * SLOT
    start = end - SETTLING
    if last is not None and last > start:
        return "settling", None, rooms, last
    rows = daily_observations(rooms, series, series.get("__outdoor__", {}), end, since=since, days=2)
    if len(rows) != 2 or any(r["coverage"] < .9 for r in rows):
        return "balance_data_required", None, rooms, last
    if any(not balanced_day(r) for r in rows):
        return "balance_required", None, rooms, last
    outdoor = [r["outdoor_c"] for r in rows]
    if abs(outdoor[0] - outdoor[1]) > 2 or max(outdoor) >= min(r["target_c"] for r in rooms) - 3:
        return "weather_not_comparable", None, rooms, last
    signs = [common_sign(r) for r in rows]
    if signs[0] and signs[0] == signs[1]:
        return "eligible", signs[0], rooms, last
    if all(abs(e) <= TOLERANCE + EPS for r in rows for e in r["room_errors_c"].values()):
        return "near_targets", None, rooms, last
    return "no_common_error", None, rooms, last
