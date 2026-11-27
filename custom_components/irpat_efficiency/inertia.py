"""Observed temperature drift, not a measurement of insulation or heat capacity."""
from math import isfinite

SLOT = 300


def _valid(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def cooling_drift(indoor, outdoor, start, end, *, heat_off_confirmed=False,
                  comparable=False):
    """Evaluate a reviewed natural cooling interval, never switch equipment off.

    Series use UTC five-minute timestamps as string keys. Require all slots
    including endpoints, and at least two hours. The normalized indicator is
    observed temperature drop divided by indoor/outdoor degree-hours.
    """
    result = {"status": "insufficient_data", "drop_c": None, "rate_c_per_h": None,
              "normalized_per_h": None, "degree_hours": None, "coverage": 0.0}
    if heat_off_confirmed is not True or comparable is not True:
        return {**result, "status": "review_required"}
    if (not isinstance(start, int) or not isinstance(end, int) or start % SLOT
            or end % SLOT or not 7200 <= end - start <= 7 * 86400):
        return result
    keys = [str(s) for s in range(start, end + SLOT, SLOT)]
    pairs = [(indoor.get(k), outdoor.get(k)) for k in keys]
    result["coverage"] = sum(_valid(a) and _valid(b) for a, b in pairs) / len(keys)
    if result["coverage"] != 1:
        return result
    hours = (end - start) / 3600
    drop = pairs[0][0] - pairs[-1][0]
    result.update(status="observed", drop_c=drop, rate_c_per_h=drop / hours,
                  duration_h=hours)
    gaps = [a - b for a, b in pairs]
    if min(gaps) <= 0 or drop <= 0:
        return result
    degree_hours = sum((a + b) / 2 * SLOT / 3600 for a, b in zip(gaps, gaps[1:]))
    result.update(degree_hours=degree_hours, normalized_per_h=drop / degree_hours)
    return result
