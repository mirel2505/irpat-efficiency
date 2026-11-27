"""Reviewed climate hypotheses and natural cooling from retained samples."""
from datetime import datetime

from .calculations import balancing_capability
from .climate_curve import diagnose_curve, finite
from .curve_gate import gate, balanced_day, SETTLING
from .inertia import cooling_drift
from .topology import temperature_conflicts
from .weather_history import daily_observations

SLOT = 300
DAY = 86400


def zone_weather(topology, series, end, since):
    """Shared source for displayed and reviewed weather observations."""
    if not topology.get('outdoor_entity_id') or not finite(since):
        return {}
    membership = {}
    manifolds = {m['id']: m['zone_id'] for m in topology['manifolds']}
    for circuit in topology['circuits']:
        room, zone = circuit.get('room_id'), manifolds.get(circuit['manifold_id'])
        if room and zone:
            membership.setdefault(room, set()).add(zone)
    conflicts = temperature_conflicts(topology)
    bound = {b['room_id'] for b in topology['bindings']}
    result = {}
    for zone in topology['zones']:
        zid = zone['id']
        if any(zid in zones and len(zones) > 1 for zones in membership.values()):
            continue
        rooms = [{'id': r['id'], 'area_m2': r.get('area_m2'), 'target_c': r.get('heating_target_c')}
                 for r in topology['rooms'] if membership.get(r['id']) == {zid}]
        ids = {r['id'] for r in rooms}
        if conflicts & ids or not ids <= bound:
            continue
        result[zid] = daily_observations(rooms, series, series.get('__outdoor__', {}), end, since=since)
    return result


def review_curve(topology, series, journal, zone_id, end, starts, *, now, since, reviewed=False):
    """Recompute selected disjoint windows; manual review is not mode evidence."""
    if reviewed is not True:
        raise ValueError('review_required')
    if (type(end) is not int or end % SLOT or not finite(now) or end > now
            or not finite(since) or not isinstance(starts, list) or not 1 <= len(starts) <= 7
            or any(type(s) is not int for s in starts) or len(set(starts)) != len(starts)):
        raise ValueError('invalid_interval')
    zone = next((z for z in topology['zones'] if z['id'] == zone_id), None)
    if zone is None:
        raise ValueError('invalid_zone')
    rows = {d['start']: d for d in zone_weather(topology, series, end, since).get(zone_id, [])}
    if not set(starts) <= rows.keys():
        raise ValueError('incompatible_history')
    mids = {m['id'] for m in topology['manifolds'] if m['zone_id'] == zone_id}
    adjustments = [datetime.fromisoformat(s['timestamp']).timestamp() for s in journal
                   if s['manifold_id'] in mids and s['phase'] in ('before', 'after', 'adjustment')]
    # Do not use data preceding or spanning the latest logged intervention.
    if adjustments and min(starts) < max(adjustments):
        raise ValueError('adjustment_since_observation')
    capability = balancing_capability(zone['operating_mode'], zone['circuit_control'])
    if capability == 'monitor_only':
        result = {'status': 'monitor_only', 'direction': None, 'days': 0}
    else:
        status, _, rooms, last = gate(topology, series, journal, zone_id, now, since)
        if status != 'eligible':
            result = {'status': status, 'direction': None, 'days': 0}
        else:
            grouped = {d['start']: d for d in daily_observations(
                rooms, series, series.get('__outdoor__', {}), end, since=since)}
            if last is not None and min(starts) < last + SETTLING:
                result = {'status': 'settling', 'direction': None, 'days': 0}
            elif not all(s in grouped and balanced_day(grouped[s]) for s in starts):
                result = {'status': 'balance_required', 'direction': None, 'days': 0}
            else:
                result = diagnose_curve([{**grouped[s], 'comparable': True} for s in starts],
                                        capability=capability, mode='heating')
    return {**result, 'zone_id': zone_id, 'reviewed_by_user': True, 'advisory_only': True}


def review_inertia(topology, series, room_id, start, end, *, now, since,
                   heat_off_confirmed=False, comparable=False):
    """Natural cooling of a single configured room; never infer whole-house U-value."""
    if (type(start) is not int or type(end) is not int or start % SLOT or end % SLOT
            or not 7200 <= end-start <= 7*DAY or not finite(now) or end > now
            or not finite(since) or start < since):
        raise ValueError('invalid_interval')
    if (not topology.get('outdoor_entity_id') or room_id in temperature_conflicts(topology)
            or not any(r['id'] == room_id for r in topology['rooms'])
            or not any(b['room_id'] == room_id for b in topology['bindings'])):
        raise ValueError('missing_temperature_configuration')
    result = cooling_drift(series.get(room_id, {}), series.get('__outdoor__', {}), start, end,
                           heat_off_confirmed=heat_off_confirmed, comparable=comparable)
    return {**result, 'room_id': room_id, 'start': start, 'end': end, 'advisory_only': True}
