"""Optional per-source defrost observations; no inference from missing states."""
from math import isfinite


def enabled_sources(topology):
    """Only heat pumps (including explicitly configured hybrid sources) with a binding."""
    bound = {b['owner_id'] for b in topology.get('telemetry', [])
             if b['group'] == 'sources' and b['role'] == 'defrost'}
    return {s['id'] for s in topology.get('sources', [])
            if s['id'] in bound and s.get('source_type') in ('heat_pump', 'hybrid')}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _delta(first, last):
    return last - first if _number(first) and _number(last) and 0 <= first <= last else None


def observe(previous, sample, *, max_gap=90, boundary_confirmed=False):
    """Pure transition tracker for regularly sampled binary state.

    A cycle must have an observed off->on->off sequence with no invalid
    readings or excessive sampling gaps. Counter differences are optional
    and require monotonic readings throughout, with a confirmed boundary.
    Durations and energy are sampled estimates, not exact event timestamps.
    Returns (new_state, completed_event_or_none), without mutating inputs.
    """
    stamp, active = sample.get('timestamp'), sample.get('active')
    if not _number(stamp) or type(active) is not bool:
        return None, None
    old = previous or {}
    if previous and not 0 < stamp - old['timestamp'] <= max_gap:
        old = {}
    energy = sample.get('electric_kwh')
    energy = energy if _number(energy) and energy >= 0 else None
    supply = sample.get('supply_c')
    supply = supply if _number(supply) else None
    state = {'timestamp': stamp, 'active': active, 'electric_kwh': energy, 'start': None}
    if active and old.get('active') is False:
        state['start'] = {'timestamp': stamp, 'electric_kwh': energy,
                          'energy_valid': boundary_confirmed is True and energy is not None,
                          'supply_start_c': supply, 'supply_min_c': supply}
    elif old.get('active') is True and old.get('start') is not None:
        start = dict(old['start'])
        start['energy_valid'] = (start['energy_valid'] and boundary_confirmed is True
                                 and _delta(old.get('electric_kwh'), energy) is not None)
        if active:
            if supply is not None:
                prior = start['supply_min_c']
                start['supply_min_c'] = supply if prior is None else min(prior, supply)
            state['start'] = start
        else:
            initial, minimum = start['supply_start_c'], start['supply_min_c']
            event = {'start': start['timestamp'], 'end': stamp, 'duration_s': stamp-start['timestamp'],
                     'electric_kwh': _delta(start['electric_kwh'], energy) if start['energy_valid'] else None,
                     'observed_supply_drop_c': initial-minimum if initial is not None and minimum is not None else None,
                     'sampled_estimate': True}
            return state, event
    return state, None
