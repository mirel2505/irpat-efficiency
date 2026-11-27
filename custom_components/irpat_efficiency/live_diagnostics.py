"""Read-only instant diagnostics from normalized, time-aligned telemetry."""
from datetime import datetime
from math import isfinite

from .calculations import thermal_power_w
from .condensation import assess_room


def _valid(sample, now):
    if not sample or sample.get('status') != 'reported':
        return False
    v, t = sample.get('value'), sample.get('timestamp')
    return all(isinstance(x, (int, float)) and not isinstance(x, bool) and isfinite(x)
               for x in (v, t)) and 0 <= now-t <= 900


def _aligned(samples, now):
    return all(_valid(s, now) for s in samples) and max(s['timestamp'] for s in samples)-min(s['timestamp'] for s in samples) <= 300


def source_metrics(source, samples, now):
    """Separate measured and calculated heat; never assume water properties."""
    def get(role):
        return samples.get(role)
    def value(role):
        s = get(role)
        return s['value'] if _valid(s, now) else None
    result = {'delta_t_c': None, 'thermal_measured_w': value('thermal_power'),
              'thermal_calculated_w': None, 'electrical_w': value('electrical_power'),
              'signed_power_ratio': None, 'cop_status': 'boundary_unconfirmed'}
    supply, ret, flow = (get(k) for k in ('supply_temperature','return_temperature','flow'))
    if _aligned([supply, ret], now):
        result['delta_t_c'] = supply['value']-ret['value']
    if _aligned([supply, ret, flow], now):
        result['thermal_calculated_w'] = thermal_power_w(flow['value'], supply['value'], ret['value'],
            source.get('density_kg_m3'), source.get('cp_j_kgk'))
    if source.get('source_type') != 'heat_pump':
        result['cop_status'] = 'not_heat_pump'
    elif source.get('power_boundary_confirmed') is True:
        q, e = get('thermal_power'), get('electrical_power')
        result['cop_status'] = 'insufficient_data'
        if _aligned([q,e], now) and e['value'] > 0:
            result['signed_power_ratio'] = q['value']/e['value']
            result['cop_status'] = 'observed_signed_ratio'
    return result


def live_diagnostics(topology, telemetry, rooms, now):
    index = {(s['group'],s['owner_id'],s['role']):s for s in telemetry}
    sources = {s['id']: source_metrics(s, {role: v for (g,i,role),v in index.items()
               if g == 'sources' and i == s['id']}, now) for s in topology['sources']}
    condensation = {}
    for room in topology['rooms']:
        rid = room['id']
        readings = rooms.get(rid, {}).get('readings', [])
        air = None
        # Do not attach one sensor's timestamp to an average of multiple sensors.
        if len(readings) == 1 and readings[0].get('reported_at'):
            r = readings[0]
            try:
                stamp = datetime.fromisoformat(r['reported_at'])
                if stamp.tzinfo is not None:
                    air = {'value': r.get('temperature_c'), 'timestamp': stamp.timestamp()}
            except (TypeError, ValueError):
                pass
        mids = {c['manifold_id'] for c in topology['circuits'] if c.get('room_id') == rid}
        supply = index.get(('manifolds', next(iter(mids)), 'supply_temperature')) if len(mids) == 1 else None
        condensation[rid] = assess_room(air, index.get(('rooms',rid,'humidity')), now=now,
            surface=index.get(('rooms',rid,'surface_temperature')), supply=supply)
    return {'sources': sources, 'condensation': condensation}
