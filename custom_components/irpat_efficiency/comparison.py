"""Reviewed before/after heating comparisons, not causal savings estimates."""
from math import isfinite

SLOT = 300
DAY = 86400


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def heating_observation(indoor, outdoor, start, end, thermal_kwh, *,
                        scope_id, measurement_id, full_heat_coverage=False):
    """Use complete simultaneous temperature endpoints and net space heat.

    Indoor series must represent the same building/zone and averaging method
    as the heat measurement. The caller must verify full net heat coverage,
    including all sources and losses during defrost, with no DHW contribution.
    """
    result = dict(status='insufficient_data', start=start, end=end,
                  scope_id=scope_id, measurement_id=measurement_id,
                  coverage=0.0, degree_hours=None, thermal_kwh=None,
                  apparent_w_per_k=None, indoor_mean_c=None, outdoor_mean_c=None)
    if (type(start) is not int or type(end) is not int or start % SLOT or end % SLOT
            or not DAY <= end-start <= 31*DAY or not scope_id or not measurement_id):
        return result
    keys = [str(s) for s in range(start, end+SLOT, SLOT)]
    pairs = [(indoor.get(k), outdoor.get(k)) for k in keys]
    result['coverage'] = sum(finite(a) and finite(b) for a,b in pairs)/len(keys)
    if result['coverage'] != 1 or full_heat_coverage is not True or not finite(thermal_kwh) or thermal_kwh <= 0:
        return result
    gaps = [a-b for a,b in pairs]
    if min(gaps) <= 0:
        return result
    def integral(values):
        return sum((a+b)/2*SLOT/3600 for a,b in zip(values, values[1:]))
    hours = (end-start)/3600
    degree_hours = integral(gaps)
    result.update(status='observed', degree_hours=degree_hours, thermal_kwh=thermal_kwh,
                  apparent_w_per_k=1000*thermal_kwh/degree_hours,
                  indoor_mean_c=integral([a for a,b in pairs])/hours,
                  outdoor_mean_c=integral([b for a,b in pairs])/hours)
    return result


def compare(before, after, intervention_at, *, reviewed=False, indoor_tolerance_c=0.5):
    """Compare reviewed nonoverlapping windows at equal comfort, not attribute causality."""
    result = dict(status='review_required', apparent_change_pct=None,
                  apparent_reduction_pct=None, causal_savings=False)
    if reviewed is not True:
        return result
    if not finite(intervention_at) or not finite(indoor_tolerance_c) or indoor_tolerance_c < 0:
        return {**result, 'status': 'invalid_comparison'}
    if any(p.get('status') != 'observed' or p.get('coverage') != 1 for p in (before, after)):
        return {**result, 'status': 'insufficient_data'}
    if (not before.get('scope_id') or not before.get('measurement_id')
            or any(before.get(k) != after.get(k) for k in ('scope_id','measurement_id'))
            or not all(finite(p.get(k)) for p in (before,after) for k in ('start','end','indoor_mean_c','apparent_w_per_k'))
            or not before['start'] < before['end'] <= intervention_at <= after['start'] < after['end']
            or min(before['apparent_w_per_k'], after['apparent_w_per_k']) <= 0
            or abs(before['indoor_mean_c']-after['indoor_mean_c']) > indoor_tolerance_c):
        return {**result, 'status': 'not_comparable'}
    change = 100*(after['apparent_w_per_k']/before['apparent_w_per_k']-1)
    return {**result, 'status': 'observed_comparison', 'apparent_change_pct': change,
            'apparent_reduction_pct': -change}
