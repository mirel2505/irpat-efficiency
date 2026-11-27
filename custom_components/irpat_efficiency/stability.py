"""Consecutive observation windows; not proof of hydraulic balance."""
from math import isfinite

DAY = 86400
SLOT = 300


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def stability(rooms, series, end, *, eligible, configuration_since,
              last_adjustment=None, days=5, tolerance=0.3,
              min_coverage=0.9, min_within=0.95):
    """Check consecutive complete 24-hour windows ending at a UTC sample boundary."""
    if isinstance(days, bool) or not isinstance(days, int) or not 3 <= days <= 7:
        raise ValueError("invalid_days")
    if not finite(tolerance) or tolerance <= 0 or not 0 < min_coverage <= 1 or not 0 < min_within <= 1:
        raise ValueError("invalid_threshold")
    result = {"status": "collecting", "required_days": days, "consecutive_days": 0,
              "daily": [], "observed_only": True}
    if not eligible:
        result["status"] = "monitor_only"
        return result
    if not rooms or configuration_since is None:
        return result
    if len({r["id"] for r in rooms}) != len(rooms) or not all(finite(r.get("target_c")) for r in rooms):
        return result
    end = int(end) // SLOT * SLOT
    boundary = max(configuration_since, last_adjustment if last_adjustment is not None else configuration_since)
    for offset in range(days):
        stop = end - offset * DAY
        start = stop - DAY
        if start < boundary:
            break
        aligned = [s for s in range(start, stop, SLOT) if all(
            finite(series.get(r["id"], {}).get(str(s))) for r in rooms)]
        coverage = len(aligned) / (DAY // SLOT)
        fractions = {r["id"]: sum(abs(series[r["id"]][str(s)] - r["target_c"]) <= tolerance + 1e-9
                                     for s in aligned) / len(aligned) for r in rooms} if aligned else {}
        passed = coverage >= min_coverage and bool(fractions) and all(v >= min_within for v in fractions.values())
        result["daily"].append({"start": start, "end": stop, "coverage": coverage,
                                "within_fraction": fractions, "passed": passed})
        if not passed:
            break
        result["consecutive_days"] += 1
    if result["consecutive_days"] == days:
        result["status"] = "stable_observed"
    elif result["daily"] and not result["daily"][-1]["passed"]:
        result["status"] = "criteria_not_met"
    elif last_adjustment is not None and end - last_adjustment < DAY:
        result["status"] = "settling"
    return result
