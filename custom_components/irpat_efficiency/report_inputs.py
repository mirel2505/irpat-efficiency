"""Prepare reviewed building report inputs from retained room history."""
import hashlib
import json
from math import isfinite

SLOT = 300


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def prepare_capture(topology, series, start, end, *, now, configuration_since):
    """Use all configured rooms and complete aligned slots from one config epoch."""
    if (type(start) is not int or type(end) is not int or start % SLOT or end % SLOT
            or not 86400 <= end-start <= 7*86400 or not finite(now) or end > now):
        raise ValueError('invalid_interval')
    if not finite(configuration_since) or start < configuration_since:
        raise ValueError('configuration_changed')
    rooms = sorted(topology.get('rooms', []), key=lambda room: room['id'])
    ids = [r['id'] for r in rooms]
    outdoor_id = topology.get('outdoor_entity_id')
    if not ids or len(set(ids)) != len(ids) or not outdoor_id:
        raise ValueError('missing_temperature_configuration')
    bindings = {i: [] for i in ids}
    for binding in topology.get('bindings', []):
        if binding['room_id'] in bindings:
            bindings[binding['room_id']].append(binding['entity_id'])
    sensors = [entity for values in bindings.values() for entity in values]
    if any(not values for values in bindings.values()) or len(set(sensors)) != len(sensors) or outdoor_id in sensors:
        raise ValueError('missing_temperature_configuration')
    areas = [room.get('area_m2') for room in rooms]
    weighted = all(finite(a) and a > 0 for a in areas)
    weights = areas if weighted else [1] * len(ids)
    outdoor, indoor = {}, {}
    for stamp in range(start, end+SLOT, SLOT):
        key = str(stamp)
        values = [series.get(i, {}).get(key) for i in ids]
        outside = series.get('__outdoor__', {}).get(key)
        if not all(finite(v) for v in [outside, *values]):
            raise ValueError('incomplete_temperature_history')
        indoor[key] = sum(v*w for v,w in zip(values,weights))/sum(weights)
        outdoor[key] = outside
    method = 'area_weighted' if weighted else 'equal_room_weight'
    identity = {'rooms': ids, 'bindings': {i: sorted(bindings[i]) for i in ids},
                'outdoor': outdoor_id, 'weights': weights, 'method': method}
    signature = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'indoor': indoor, 'outdoor': outdoor, 'room_ids': ids,
            'measurement_signature': signature, 'weighting_method': method}
