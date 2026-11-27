"""Advisory condensation assessment; never a substitute for hardware protection."""
from math import isfinite

from .calculations import dew_point_c


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _reading(sample, now, max_age):
    if not isinstance(sample, dict):
        return None
    value, stamp = sample.get("value"), sample.get("timestamp")
    if not _finite(value) or not _finite(stamp) or not 0 <= now - stamp <= max_age:
        return None
    return value, stamp


def assess_room(air, humidity, *, now, surface=None, supply=None,
                margin_c=2.0, max_age=900, max_skew=300):
    """Read Celsius and percent RH; timestamps in UTC seconds.

    A measured surface and a supply-water proxy are separate comparisons.
    Above-margin is not a declaration of safe cooling.
    """
    if not all(_finite(v) for v in (now, margin_c, max_age, max_skew)) or margin_c <= 0 or max_age <= 0 or max_skew < 0:
        raise ValueError("invalid_threshold")
    result = {"dew_point_c": None, "surface": {"status": "unknown"},
              "supply_proxy": {"status": "unknown"}, "status": "unknown",
              "hardware_protection_required": True}
    a, h = _reading(air, now, max_age), _reading(humidity, now, max_age)
    if a is None or h is None or abs(a[1] - h[1]) > max_skew:
        return result
    dew = dew_point_c(a[0], h[0])
    if dew is None:
        return result
    result["dew_point_c"] = dew
    for key, sample in (("surface", surface), ("supply_proxy", supply)):
        v = _reading(sample, now, max_age)
        if v is None or not -60 <= v[0] <= 100:
            continue
        stamps = (a[1], h[1], v[1])
        if max(stamps) - min(stamps) > max_skew:
            continue
        gap = v[0] - dew
        state = "at_or_below_dew_point" if gap <= 0 else "low_margin" if gap < margin_c else "above_margin"
        result[key] = {"status": state, "temperature_c": v[0], "margin_c": gap}
    states = {result[k]["status"] for k in ("surface", "supply_proxy")}
    if "at_or_below_dew_point" in states or "low_margin" in states:
        result["status"] = "review_risk"
    elif result["surface"]["status"] == "above_margin":
        result["status"] = "surface_above_margin"
    elif result["supply_proxy"]["status"] == "above_margin":
        result["status"] = "proxy_only"
    return result


def summarize_zone(rooms, expected_ids):
    """A missing room cannot be interpreted as a low-risk zone."""
    ids = set(expected_ids)
    assessed = {i: rooms.get(i, {}).get("status", "unknown") for i in ids}
    if "review_risk" in assessed.values():
        status = "review_risk"
    elif ids and all(v == "surface_above_margin" for v in assessed.values()):
        status = "observed_surfaces_above_margin"
    else:
        status = "incomplete_surface_coverage"
    return {"status": status, "room_count": len(ids), "room_statuses": assessed,
            "hardware_protection_required": True}
