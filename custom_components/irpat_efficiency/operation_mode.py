"""Optional explicit mapping of reported equipment operating states."""
from copy import deepcopy
from math import isfinite

MODES = ('heating', 'cooling', 'dhw', 'standby', 'defrost', 'off')


def configure_mode(topology, source_id, entity_id=None, **states):
    """Assign exact raw sensor states; never infer from selected HVAC mode."""
    data = deepcopy(topology)
    source = next((s for s in data.get('sources', []) if s['id'] == source_id), None)
    if source is None:
        raise ValueError('invalid_reference')
    if entity_id is None:
        source.pop('mode_binding', None)
        return data
    if not isinstance(entity_id, str) or not entity_id.startswith('sensor.') or len(entity_id) <= 7:
        raise ValueError('invalid_entity')
    mapping = {}
    for mode, raw in states.items():
        if mode not in MODES:
            raise ValueError('invalid_mode')
        if raw is None or raw == '':
            continue
        if (not isinstance(raw, str) or not raw.strip() or len(raw) > 120
                or raw in ('unknown', 'unavailable') or raw in mapping):
            raise ValueError('invalid_mode_mapping')
        mapping[raw] = mode
    if not mapping:
        raise ValueError('invalid_mode_mapping')
    source['mode_binding'] = {'entity_id': entity_id, 'mapping': mapping}
    return data


def classify_mode(binding, raw, reported_at, now, *, max_age=300):
    """Identify only the reported snapshot, not a confirmed continuous interval."""
    result = {'mode': None, 'status': 'not_configured', 'interval_confirmed': False}
    if not binding:
        return result
    if raw is None or raw in ('unknown', 'unavailable'):
        return {**result, 'status': 'unavailable'}
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)
               for v in (reported_at, now, max_age)) or max_age <= 0 or not 0 <= now-reported_at <= max_age:
        return {**result, 'status': 'stale'}
    mode = binding['mapping'].get(raw) if isinstance(raw, str) else None
    return {**result, 'mode': mode, 'status': 'reported' if mode in MODES else 'unmapped'}
