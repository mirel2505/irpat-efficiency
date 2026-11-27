"""Conservative directional heating advice, based on two synchronized days.

No valve commands or calculated flow changes. Operating conditions must still
be reviewed by the user; thresholds are provisional, not commissioning norms.
"""
from datetime import datetime
from statistics import mean

from .calculations import balancing_capability
from .thermal_balance import analyze_zone
from .topology import temperature_conflicts
from .weather_history import valid

DAY = 86400
SLOT = 300
TOLERANCE = 0.3
MAX_WEATHER_CHANGE = 2.0


def recommendations(topology, series, now, journal, since):
    """Return reasons to wait or a directional hypothesis for each heating zone."""
    end = int(now) // SLOT * SLOT
    start = end - 2 * DAY
    result = {}
    membership = {}
    mids = {m["id"]: m["zone_id"] for m in topology["manifolds"]}
    for c in topology["circuits"]:
        if c.get("room_id") and c["manifold_id"] in mids:
            membership.setdefault(c["room_id"], set()).add(mids[c["manifold_id"]])
    for zone in topology["zones"]:
        zid = zone["id"]
        row = result[zid] = {"status": "collecting", "name": zone["name"], "rooms": {},
                             "coverage": 0, "hours": 48, "outdoor_means_c": [],
                             "advisory_only": True, "review_required": True,
                             "window_start": start, "window_end": end}
        if balancing_capability(zone["operating_mode"], zone["circuit_control"]) == "monitor_only":
            row["status"] = "configure_operation"
            continue
        circuits = [c for c in topology["circuits"] if mids.get(c["manifold_id"]) == zid]
        rooms = [dict(id=r["id"], area_m2=r.get("area_m2"), target_c=r.get("heating_target_c"))
                 for r in topology["rooms"] if zid in membership.get(r["id"], set())]
        ids = {r["id"] for r in rooms}
        bound = {b["room_id"] for b in topology["bindings"]}
        if (len(rooms) < 2 or any(not c.get("room_id") for c in circuits)
                or any(membership[rid] != {zid} for rid in ids)
                or ids & temperature_conflicts(topology)
                or not ids <= bound or not all(valid(r["target_c"]) for r in rooms)):
            row["status"] = "configure_rooms"
            continue
        if not topology.get("outdoor_entity_id"):
            row["status"] = "configure_outdoor"
            continue
        if not valid(since) or since > start:
            continue
        changes = [datetime.fromisoformat(x["timestamp"]).timestamp() for x in journal
                   if mids.get(x["manifold_id"]) == zid and x["phase"] in ("before", "after")]
        if changes and max(changes) > start:
            row["status"] = "settling"
            continue
        outdoor = series.get("__outdoor__", {})
        days = []
        for begin in (start, start + DAY):
            keys = [str(s) for s in range(begin, begin + DAY, SLOT)
                    if valid(outdoor.get(str(s))) and all(valid(series.get(i, {}).get(str(s))) for i in ids)]
            if len(keys) / (DAY // SLOT) < .9:
                break
            filtered = {i: {k: series[i][k] for k in keys} for i in ids}
            obs = analyze_zone(rooms, filtered, begin, begin + DAY, eligible=True)
            if obs["status"] != "observed":
                break
            days.append(obs)
            row["outdoor_means_c"].append(mean(outdoor[k] for k in keys))
        if len(days) != 2:
            row["status"] = "insufficient_data"
            continue
        row["coverage"] = min(d["coverage"] for d in days)
        # Compare only similar outdoor conditions with a meaningful heating load.
        if (abs(row["outdoor_means_c"][0] - row["outdoor_means_c"][1]) > MAX_WEATHER_CHANGE
                or max(row["outdoor_means_c"]) >= min(r["target_c"] for r in rooms) - 3):
            row["status"] = "weather_not_comparable"
            continue
        row["common_errors_c"] = [d["common_error_c"] for d in days]
        row["status"] = "review_conditions"
        for rid in ids:
            errors = [d["rooms"][rid]["mean_error_c"] for d in days]
            residuals = [d["rooms"][rid]["residual_c"] for d in days]
            # A common error cannot justify reducing every loop. Require both
            # absolute and relative error to persist in the same direction.
            if all(e > TOLERANCE and r > TOLERANCE for e, r in zip(errors, residuals)):
                direction = "decrease"
            elif all(e < -TOLERANCE and r < -TOLERANCE for e, r in zip(errors, residuals)):
                direction = "increase"
            elif all(abs(e) <= TOLERANCE + 1e-9 for e in errors):
                direction = "hold"
            else:
                direction = "observe"
            row["rooms"][rid] = {"direction": direction, "mean_error_c": mean(errors),
                                 "relative_error_c": mean(residuals),
                                 "circuits": [dict(id=c["id"], position=c["position"],
                                                  manifold_id=c["manifold_id"])
                                              for c in circuits if c["room_id"] == rid]}
        if all(abs(x) > TOLERANCE for x in row["common_errors_c"]) and all(
                x * row["common_errors_c"][0] > 0 for x in row["common_errors_c"]):
            row["common_direction"] = "review_supply"
    return result
