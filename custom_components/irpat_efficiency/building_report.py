"""Reviewed building comparisons; weather normalization is not causal proof."""
from math import isfinite
from uuid import uuid4
from copy import deepcopy

SLOT = 300


def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)


def snapshot(indoor, outdoor, start, end, *, room_ids, boundary_id,
             thermal_kwh, electric_kwh=None, reviewed=False):
    """Capture a complete aligned whole-building heating observation.

    Indoor values are a consistent representative building temperature.
    Thermal energy must be reviewed net heat at the building boundary,
    including losses during defrost; partial Q/E estimates are not eligible.
    """
    if (type(start) is not int or type(end) is not int or start % SLOT or end % SLOT
            or not 86400 <= end-start <= 7*86400):
        raise ValueError('invalid_interval')
    if (not room_ids or any(not isinstance(i, str) or not i for i in room_ids)
            or len(set(room_ids)) != len(room_ids) or not isinstance(boundary_id, str)
            or not boundary_id.strip()):
        raise ValueError('invalid_boundary')
    if reviewed is not True or not finite(thermal_kwh) or thermal_kwh <= 0:
        raise ValueError('review_required')
    if electric_kwh is not None and (not finite(electric_kwh) or electric_kwh < 0):
        raise ValueError('invalid_energy')
    pairs = [(indoor.get(str(t)), outdoor.get(str(t))) for t in range(start, end+SLOT, SLOT)]
    if not all(finite(a) and finite(b) and a > b for a,b in pairs):
        raise ValueError('incomplete_or_nonheating_data')
    hours = (end-start)/3600
    dh = sum(((a-b)+(c-d))/2*SLOT/3600 for (a,b),(c,d) in zip(pairs,pairs[1:]))
    return {'id': uuid4().hex, 'start': start, 'end': end, 'hours': hours,
            'room_ids': sorted(room_ids), 'boundary_id': boundary_id,
            'thermal_kwh': thermal_kwh, 'electric_kwh': electric_kwh,
            'degree_hours': dh, 'apparent_w_per_k': 1000*thermal_kwh/dh,
            'indoor_mean_c': (pairs[0][0]/2+sum(a for a,b in pairs[1:-1])+pairs[-1][0]/2)/(len(pairs)-1),
            'outdoor_mean_c': (pairs[0][1]/2+sum(b for a,b in pairs[1:-1])+pairs[-1][1]/2)/(len(pairs)-1),
            'reviewed': True}


def compare(before, after, *, intervention_at, comparable=False):
    """Compare reviewed observations; lower normalized input is not proven savings."""
    if (comparable is not True or before.get('reviewed') is not True
            or after.get('reviewed') is not True):
        raise ValueError('review_required')
    if not finite(intervention_at) or not before['end'] <= intervention_at <= after['start']:
        raise ValueError('invalid_intervention_date')
    if any(before[k] != after[k] for k in ('room_ids', 'boundary_id')):
        raise ValueError('incompatible_boundary')
    x,y = before['apparent_w_per_k'],after['apparent_w_per_k']
    if not finite(x) or not finite(y) or min(x,y) <= 0:
        raise ValueError('invalid_energy')
    return {'before': deepcopy(before), 'after': deepcopy(after),
            'intervention_at': intervention_at, 'normalized_change_pct': 100*(y/x-1),
            'thermal_kwh_per_day_before': before['thermal_kwh']*24/before['hours'],
            'thermal_kwh_per_day_after': after['thermal_kwh']*24/after['hours'],
            'causal_savings_confirmed': False}
