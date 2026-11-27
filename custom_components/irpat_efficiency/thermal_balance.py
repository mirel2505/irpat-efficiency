"""Conservative thermal balance diagnostics using aligned room samples."""
from math import isfinite
from statistics import mean


def analyze_zone(rooms, series, start, end, *, eligible, last_adjustment=None,
                 tolerance=0.3, min_coverage=0.9):
    """Describe observed deviations, not a prescription or balance certification.

    Times are UTC five-minute slot boundaries. All rooms use identical slots.
    """
    result = {"status": "insufficient_data", "coverage": 0.0, "rooms": {},
              "common_error_c": None, "weighting": None}
    if not eligible:
        result["status"] = "monitor_only"
        return result
    if last_adjustment is not None and last_adjustment > start:
        result["status"] = "settling"
        return result
    if end - start < 86400 or start % 300 or end % 300 or not rooms:
        return result
    ids = [r["id"] for r in rooms]
    if len(set(ids)) != len(ids):
        return result
    targets = {r["id"]: r.get("target_c") for r in rooms}
    def valid(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
    if not all(valid(v) for v in targets.values()):
        return result
    slots = range(start, end, 300)
    aligned = [s for s in slots if all(valid(series.get(i, {}).get(str(s))) for i in ids)]
    result["coverage"] = len(aligned) / len(slots)
    if not aligned or result["coverage"] < min_coverage:
        return result
    errors = {i: [series[i][str(s)] - targets[i] for s in aligned] for i in ids}
    averages = {i: mean(v) for i, v in errors.items()}
    areas = [r.get("area_m2") for r in rooms]
    weighted = all(valid(a) and a > 0 for a in areas)
    common = (sum(averages[i] * a for i, a in zip(ids, areas)) / sum(areas)
              if weighted else mean(averages.values()))
    result.update(common_error_c=common, weighting="area" if weighted else "equal_rooms",
                  status="observed")
    for i in ids:
        residual = averages[i] - common
        result["rooms"][i] = {"mean_error_c": averages[i], "residual_c": residual,
                              "within_fraction": sum(abs(v) <= tolerance + 1e-9 for v in errors[i]) / len(aligned)}
    local = any(abs(v["residual_c"]) > tolerance + 1e-9 for v in result["rooms"].values())
    global_error = abs(common) > tolerance + 1e-9
    result["pattern"] = ("mixed" if local and global_error else "distribution" if local else
                         "common" if global_error else "near_targets")
    return result
