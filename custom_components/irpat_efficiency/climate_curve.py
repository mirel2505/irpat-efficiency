"""Conservative heating-curve diagnostics from reviewed daily observations."""
from math import isfinite
from statistics import mean


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def diagnose_curve(days, *, capability, mode, tolerance=0.3):
    """Return hypotheses, not settings. Each day must be reviewed as comparable.

    outdoor_c and common_error_c are aligned daily means. No cooling slope
    inference, and no recommendation in ON/OFF or unverified operation.
    """
    result = {"status": "insufficient_data", "direction": None, "days": 0}
    if capability not in ("weather_compensation", "fixed_supply") or mode != "heating":
        return {**result, "status": "monitor_only"}
    if not finite(tolerance) or tolerance <= 0:
        raise ValueError("invalid_tolerance")
    usable = {}
    for d in days:
        stamp = d.get("day")
        if (not isinstance(stamp, str) or not stamp or d.get("comparable") is not True
                or not finite(d.get("coverage")) or not 0.9 <= d["coverage"] <= 1
                or not finite(d.get("outdoor_c")) or not finite(d.get("common_error_c"))
                or not finite(d.get("max_residual_c")) or not 0 <= d["max_residual_c"] <= tolerance):
            continue
        if stamp in usable:
            return {**result, "status": "duplicate_day"}
        usable[stamp] = d
    rows = list(usable.values())
    result["days"] = len(rows)
    if len(rows) < 3:
        return result
    x = [d["outdoor_c"] for d in rows]
    y = [d["common_error_c"] for d in rows]
    avg = mean(y)
    result.update(mean_error_c=avg, outdoor_span_c=max(x)-min(x))
    # Fixed-supply comparisons require a narrow range of outdoor conditions.
    if capability == "fixed_supply" and max(x)-min(x) > 2:
        return {**result, "status": "weather_changed"}
    if capability == "weather_compensation" and len(rows) >= 5 and max(x)-min(x) >= 5:
        mx = mean(x)
        slope = sum((a-mx)*(b-avg) for a,b in zip(x,y)) / sum((a-mx)**2 for a in x)
        result["error_slope_c_per_c"] = slope
        if abs(slope)*(max(x)-min(x)) > 2*tolerance:
            return {**result, "status": "review_slope", "direction": "steeper" if slope > 0 else "flatter"}
    if max(y)-min(y) <= 2*tolerance and all(v > tolerance for v in y):
        return {**result, "status": "review_offset" if capability == "weather_compensation" else "review_fixed_supply", "direction": "lower"}
    if max(y)-min(y) <= 2*tolerance and all(v < -tolerance for v in y):
        return {**result, "status": "review_offset" if capability == "weather_compensation" else "review_fixed_supply", "direction": "raise"}
    if all(abs(v) <= tolerance + 1e-9 for v in y):
        return {**result, "status": "near_targets"}
    return {**result, "status": "inconclusive"}


def comfort_direction(delta_c, *, mode, capability):
    """A desired indoor shift does not imply the same supply-temperature shift."""
    if not finite(delta_c) or mode not in ("heating", "cooling"):
        raise ValueError("invalid_request")
    if capability not in ("weather_compensation", "fixed_supply"):
        return "monitor_only"
    if delta_c == 0:
        return "unchanged"
    if mode == "cooling" and delta_c < 0:
        return "condensation_review_required"
    return "raise_supply" if delta_c > 0 else "lower_supply"
