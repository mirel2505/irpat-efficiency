"""Remove unreferenced configuration objects without touching historical stores."""
from copy import deepcopy

from .topology import COLLECTIONS, SCHEMA_VERSION, TopologyError


def remove_item(topology, collection, identifier, *, confirmed=False):
    """No cascading deletion, device commands, or reuse of retired IDs."""
    if topology.get('schema_version') != SCHEMA_VERSION or collection not in COLLECTIONS:
        raise TopologyError('invalid_schema')
    if not any(item['id'] == identifier for item in topology[collection]):
        raise TopologyError('invalid_reference')
    if confirmed is not True:
        raise TopologyError('remove_confirmation_required')
    dependencies = {
        'floors': (('rooms', 'floor_id'), ('manifolds', 'floor_id')),
        'zones': (('manifolds', 'zone_id'),),
        'rooms': (('circuits', 'room_id'), ('bindings', 'room_id')),
        'manifolds': (('circuits', 'manifold_id'),),
    }
    if any(item.get(field) == identifier
           for group, field in dependencies.get(collection, ())
           for item in topology[group]):
        raise TopologyError('object_in_use')
    if collection == 'zones' and any(identifier in s.get('zone_ids', []) for s in topology['sources']):
        raise TopologyError('object_in_use')
    # Telemetry belongs to the removed object only; remove its associations,
    # not the HA entities or archived observations. No other object is removed.
    data = deepcopy(topology)
    data[collection] = [item for item in data[collection] if item['id'] != identifier]
    if 'telemetry' in data:
        data['telemetry'] = [b for b in data['telemetry']
                             if (b['group'], b['owner_id']) != (collection, identifier)]
    return data


def removal_preview(topology, collection, identifiers):
    """Show the exact selected objects and any blocking references."""
    if collection not in COLLECTIONS or not isinstance(identifiers, list) or not identifiers:
        raise TopologyError('invalid_reference')
    chosen = set(identifiers)
    if len(chosen) != len(identifiers) or not chosen <= {x['id'] for x in topology[collection]}:
        raise TopologyError('invalid_reference')
    dependencies = {
        'floors': (('rooms', 'floor_id'), ('manifolds', 'floor_id')),
        'zones': (('manifolds', 'zone_id'),),
        'rooms': (('circuits', 'room_id'), ('bindings', 'room_id')),
        'manifolds': (('circuits', 'manifold_id'),),
    }
    blockers = [item['name'] for group, field in dependencies.get(collection, ())
                for item in topology[group] if item.get(field) in chosen]
    sources = [s['name'] for s in topology['sources']
               if collection == 'zones' and chosen.intersection(s.get('zone_ids', []))]
    return {'selected': [x['name'] for x in topology[collection] if x['id'] in chosen],
            'blockers': blockers, 'sources': sources}


def remove_selection(topology, collection, identifiers, *, confirmed=False, detach_zone_sources=False):
    """Atomic batch removal. Explicitly detach unused zones from retained sources."""
    preview = removal_preview(topology, collection, identifiers)
    if confirmed is not True:
        raise TopologyError('remove_confirmation_required')
    if preview['blockers'] or (preview['sources'] and detach_zone_sources is not True):
        raise TopologyError('object_in_use')
    data = deepcopy(topology)
    if collection == 'zones':
        for source in data['sources']:
            source['zone_ids'] = [z for z in source['zone_ids'] if z not in identifiers]
    for identifier in identifiers:
        data = remove_item(data, collection, identifier, confirmed=True)
    return data
