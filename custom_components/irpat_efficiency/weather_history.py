"""Synchronized daily weather observations; no automatic comparability claims."""
from math import isfinite
from statistics import mean

DAY = 86400
SLOT = 300


def valid(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def daily_observations(rooms, series, outdoor, end, *, since, days=7):
    """Return disjoint UTC 24-hour windows using identical indoor/outdoor slots.

    All observations are unreviewed; they cannot feed adjustment hypotheses
    until actual operating conditions and disturbances are checked.
    """
    if since is None or not rooms or not isinstance(days, int) or not 1 <= days <= 7:
        return []
    ids = [r['id'] for r in rooms]
    targets = {r['id']: r.get('target_c') for r in rooms}
    if len(set(ids)) != len(ids) or not all(valid(v) for v in targets.values()):
        return []
    areas = [r.get('area_m2') for r in rooms]
    weighted = all(valid(a) and a > 0 for a in areas)
    end = int(end) // SLOT * SLOT
    observations = []
    for offset in range(days):
        stop = end - offset * DAY
        start = stop - DAY
        if start < since:
            break
        keys = [str(s) for s in range(start, stop, SLOT)]
        aligned = [k for k in keys if valid(outdoor.get(k)) and all(
            valid(series.get(i, {}).get(k)) for i in ids)]
        coverage = len(aligned) / len(keys)
        errors = {i: mean(series[i][k] - targets[i] for k in aligned)
                  for i in ids} if aligned else {}
        common = (sum(errors[i] * a for i, a in zip(ids, areas)) / sum(areas)
                  if weighted else mean(errors.values())) if errors else None
        # Check relative balance throughout the window, not only daily averages.
        balanced_slots = 0
        for k in aligned:
            instantaneous = [series[i][k] - targets[i] for i in ids]
            offset_c = (sum(e*a for e, a in zip(instantaneous, areas)) / sum(areas)
                        if weighted else mean(instantaneous))
            if all(abs(e-offset_c) <= .3 + 1e-9 for e in instantaneous):
                balanced_slots += 1
        observations.append(dict(day=str(start), start=start, end=stop,
             room_errors_c=errors, relative_balance_fraction=balanced_slots/len(aligned) if aligned else 0,
            outdoor_c=mean(outdoor[k] for k in aligned) if aligned else None,
            common_error_c=common,
            max_residual_c=max(abs(e-common) for e in errors.values()) if errors else None,
            coverage=coverage, comparable=False))
    return observations
