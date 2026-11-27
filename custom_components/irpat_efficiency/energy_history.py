"""Daily energy ledger; no inferred consumption across missing intervals."""
from datetime import date, datetime, time, timedelta
from math import isfinite

SLOT = 300


def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)


def append_interval(ledger, start, end, electric_kwh, signed_thermal_kwh, *,
                    timezone, mode=None, boundary_confirmed=False):
    """Accumulate one aligned interval, exactly once, in local calendar days.

    Both energy inputs are interval deltas, not cumulative readings.
    Positive signed thermal energy means heat delivered to the building.
    Mode must be confirmed for the entire interval (including defrost).
    """
    if (type(start) is not int or type(end) is not int or start % SLOT
            or end-start != SLOT):
        raise ValueError('invalid_interval')
    if start < ledger.get('last_end', start):
        return False
    day = datetime.fromtimestamp(start, timezone).date().isoformat()
    if datetime.fromtimestamp(end-1, timezone).date().isoformat() != day:
        raise ValueError('crosses_local_day')
    row = ledger.setdefault('days', {}).setdefault(day, {
        'electric_kwh': 0.0, 'electric_seconds': 0, 'modes': {}})
    ledger['last_end'] = end
    if not finite(electric_kwh) or electric_kwh < 0:
        return True
    row['electric_kwh'] += electric_kwh
    row['electric_seconds'] += SLOT
    if (boundary_confirmed is True and mode in ('heating', 'cooling')
            and finite(signed_thermal_kwh)):
        m = row['modes'].setdefault(mode, {'thermal_kwh': 0.0, 'electric_kwh': 0.0, 'seconds': 0})
        m['thermal_kwh'] += signed_thermal_kwh if mode == 'heating' else -signed_thermal_kwh
        m['electric_kwh'] += electric_kwh
        m['seconds'] += SLOT
    return True


def meter_delta(before, after):
    """Reject invalid or decreasing counters; never infer across a reset."""
    if not all(finite(v) for v in (before, after)) or not 0 <= before <= after:
        return None
    return after-before


def summarize(ledger, first, stop, *, timezone, now, tariff=None):
    """Summarize [first, stop) local dates, clipped to completed sample slots.

    Costs assume a single constant tariff; COP is for matched, confirmed-mode
    intervals only. Missing historical days contribute no observed energy.
    """
    if not isinstance(first, date) or not isinstance(stop, date) or first >= stop:
        raise ValueError('invalid_dates')
    start = datetime.combine(first, time.min, timezone).timestamp()
    end = min(datetime.combine(stop, time.min, timezone).timestamp(), int(now)//SLOT*SLOT)
    expected = max(0, end-start)
    electric = 0.0
    seconds = 0
    modes = {k: {'thermal_kwh': 0.0, 'electric_kwh': 0.0, 'seconds': 0} for k in ('heating', 'cooling')}
    for key, row in ledger.get('days', {}).items():
        if first.isoformat() <= key < stop.isoformat():
            electric += row['electric_kwh']
            seconds += row['electric_seconds']
            for mode, m in row['modes'].items():
                for field in modes[mode]:
                    modes[mode][field] += m[field]
    if seconds > expected:
        raise ValueError('ledger_after_cutoff')
    for m in modes.values():
        m['cop'] = m['thermal_kwh']/m['electric_kwh'] if m['electric_kwh'] > 0 else None
        m['coverage'] = m['seconds']/expected if expected else None
        if not m['seconds']:
            m['thermal_kwh'] = m['electric_kwh'] = None
    return {'status': 'complete' if seconds and seconds == expected else 'partial' if seconds else 'insufficient_data',
            'expected_seconds': expected, 'observed_seconds': seconds,
            'coverage': seconds/expected if expected else None,
            'electric_kwh': electric if seconds else None,
            'estimated_cost': electric*tariff if seconds and finite(tariff) and tariff >= 0 else None,
            'modes': modes}


def period_dates(today):
    """Calendar periods, including the current incomplete day."""
    tomorrow = today + timedelta(days=1)
    return {'daily': (today, tomorrow), 'weekly': (today-timedelta(days=today.weekday()), tomorrow),
            'monthly': (today.replace(day=1), tomorrow), 'annual': (today.replace(month=1, day=1), tomorrow)}
