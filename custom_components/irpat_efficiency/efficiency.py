"""Energy diagnostics on explicitly aligned five-minute observations."""
from math import isfinite

SLOT = 300


def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)


def energy_summary(thermal_w, electrical_w, start, end, *, mode,
                   boundary_confirmed=False, tariff=None, area_m2=None):
    """Integrate matched power intervals only; thermal power is signed to building.

    Inputs must represent the same system boundary and requested operating mode,
    including defrost and auxiliary consumption. Keys are UTC seconds as strings.
    Missing endpoints invalidate an interval; never bridge gaps.
    """
    if mode not in ('heating', 'cooling') or end <= start or start % SLOT or end % SLOT:
        raise ValueError('invalid_interval_or_mode')
    result = dict(status='review_required', coverage=0.0, thermal_kwh=None,
                  electrical_kwh=None, cop=None, cost=None, thermal_kwh_m2=None)
    if boundary_confirmed is not True:
        return result
    q = e = 0.0
    count = 0
    for s in range(start, end, SLOT):
        a, b = str(s), str(s + SLOT)
        p1, p2 = thermal_w.get(a), thermal_w.get(b)
        e1, e2 = electrical_w.get(a), electrical_w.get(b)
        if not all(finite(v) for v in (p1,p2,e1,e2)) or min(e1,e2) < 0:
            continue
        q += (p1+p2)/2 * SLOT/3600000
        e += (e1+e2)/2 * SLOT/3600000
        count += 1
    if not count:
        return {**result, 'status': 'insufficient_data'}
    if mode == 'cooling':
        q = -q
    coverage = count * SLOT / (end-start)
    result.update(status='complete' if coverage == 1 else 'partial',
                  coverage=coverage, thermal_kwh=q, electrical_kwh=e,
                  cop=q/e if e > 0 else None)
    if finite(tariff) and tariff >= 0:
        result['cost'] = e * tariff
    if finite(area_m2) and area_m2 > 0:
        result['thermal_kwh_m2'] = q / area_m2
    return result


def counter_delta(previous, current):
    """A decreasing cumulative meter cannot establish energy across a reset."""
    if not all(finite(v) for v in (previous,current)) or not 0 <= previous <= current:
        return None
    return current-previous


def apparent_loss_w_per_k(thermal_kwh, degree_hours, *, reviewed=False, coverage=0):
    """Observed heat input per degree-hour, not a certified heat loss coefficient."""
    if reviewed is not True or coverage != 1:
        return None
    if not all(finite(v) for v in (thermal_kwh,degree_hours)) or thermal_kwh <= 0 or degree_hours <= 0:
        return None
    return 1000*thermal_kwh/degree_hours


def fuel_efficiency(thermal_kwh, fuel_kwh, *, basis, boundary_confirmed=False):
    """Useful heat / fuel energy, on explicitly stated LHV or HHV basis."""
    if boundary_confirmed is not True or basis not in ('LHV','HHV'):
        return None
    if not all(finite(v) for v in (thermal_kwh,fuel_kwh)) or thermal_kwh < 0 or fuel_kwh <= 0:
        return None
    return thermal_kwh/fuel_kwh
