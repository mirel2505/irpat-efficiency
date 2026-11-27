"""Review saved hydraulic observations against a manual reference profile."""
from .profile_store import compare_profile
from .stability import finite


def review_profile(topology, profile, snapshot):
    """Return raw differences only, without implying comparable conditions."""
    mid = snapshot['manifold_id']
    manifold = next((m for m in topology['manifolds'] if m['id'] == mid), None)
    if manifold is None or manifold['zone_id'] != profile['zone_id']:
        raise ValueError('topology_changed')
    rows = compare_profile(profile, topology, snapshot)
    if not set(snapshot['flows_lmin']) <= set(rows):
        raise ValueError('topology_changed')
    result = []
    circuits = sorted((c for c in topology['circuits'] if c['manifold_id'] == mid),
                      key=lambda c: c['position'])
    for circuit in circuits:
        row = rows[circuit['id']]
        reference, observed = row['reference_lmin'], row['observed_lmin']
        if not finite(reference) or reference < 0:
            raise ValueError('invalid_flow')
        if observed is not None and (not finite(observed) or observed < 0):
            raise ValueError('invalid_flow')
        result.append({'circuit_id': circuit['id'], 'name': circuit['name'],
                       'position': circuit['position'], **row,
                       'difference_lmin': observed-reference if observed is not None else None})
    return {'profile_id': profile['id'], 'snapshot_id': snapshot['id'], 'manifold_id': mid,
            'profile_mode': profile['mode'], 'observed_at': snapshot['timestamp'],
            'comparable_confirmed': False, 'automatic_restore': False, 'rows': result}
