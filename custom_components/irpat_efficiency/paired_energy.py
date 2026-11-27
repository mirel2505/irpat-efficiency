"""Estimated signed heat for matched meter and reported-mode observations."""
from .energy_history import finite


def matched_heat(before, after):
    """Return (mode, signed kWh) for compatible consecutive observations.

    This is a sampled estimate, not a whole-period COP. Explicit defrost,
    standby, DHW and mixed/unknown modes are excluded. Negative heat is kept
    when the reported mode remains heating. HA timestamps are report times.
    """
    a, b = before.get('pair'), after.get('pair')
    if not a or not b:
        return None, None
    if any(x.get('confirmed') is not True for x in (a, b)):
        return None, None
    q1, q2 = a.get('thermal'), b.get('thermal')
    m1, m2 = a.get('mode'), b.get('mode')
    if not q1 or not q2 or not m1 or not m2:
        return None, None
    if q1.get('entity_id') != q2.get('entity_id') or not q1.get('entity_id'):
        return None, None
    if any(x.get('status') != 'reported' for x in (q1, q2)):
        return None, None
    t1, t2 = before.get('timestamp'), after.get('timestamp')
    u1, u2 = q1.get('timestamp'), q2.get('timestamp')
    p1, p2 = q1.get('value'), q2.get('value')
    if not all(finite(x) for x in (t1, t2, u1, u2, p1, p2)):
        return None, None
    if not 240 <= t2-t1 <= 360 or max(abs(u1-t1), abs(u2-t2)) > 5 or u2 <= u1:
        return None, None
    if any(m1[k] != m2[k] for k in ('signature', 'raw', 'mode', 'changed_at')):
        return None, None
    if m1['mode'] not in ('heating', 'cooling'):
        return None, None
    if not (m1['changed_at'] <= min(t1, u1) <= max(t1, u1) <= m1['observed_at'] <= min(t2, u2)
            and max(t2, u2) <= m2['reported_at'] <= m2['observed_at']
            and m2['observed_at']-m1['observed_at'] <= 360):
        return None, None
    return m1['mode'], (p1+p2)/2*(u2-u1)/3600000


def pair_signature(topology, source_id):
    """JSON-stable measurement identity, independent of sensor availability."""
    source = next((s for s in topology.get('sources', []) if s['id'] == source_id), {})
    binding = source.get('mode_binding')
    if (source.get('source_type') != 'heat_pump' or not binding
            or source.get('power_boundary_confirmed') is not True
            or source.get('energy_boundary_confirmed') is not True):
        return None
    bindings = [b for b in topology.get('telemetry', []) if b['group'] == 'sources']
    roles = ('electrical_energy', 'electrical_power', 'thermal_power')
    selected = {b['role']: b['entity_id'] for b in bindings
                if b['owner_id'] == source_id and b['role'] in roles}
    if not all(role in selected for role in roles) or len(set(selected.values())) != len(roles):
        return None
    if any(b['owner_id'] != source_id and b['entity_id'] in selected.values()
           for b in bindings):
        return None
    return {'meters': selected, 'mode': binding}
