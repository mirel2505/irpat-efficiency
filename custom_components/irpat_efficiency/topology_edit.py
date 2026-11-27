"""Identity-preserving edits of existing topology; no destructive migrations."""
from copy import deepcopy

from .topology import SCHEMA_VERSION, TopologyError, add_item, rename_item

# Structural reassignment is deliberately excluded: a historical circuit or
# energy source must not silently acquire a new physical meaning.
EDIT_FIELDS = {
    'floors': (),
    'zones': ('operating_mode', 'circuit_control'),
    'sources': (),
    'rooms': ('area_m2', 'heating_target_c', 'cooling_target_c'),
    'manifolds': (),
    'circuits': ('position', 'length_m'),
    'bindings': ('entity_id',),
}
OPTIONAL_FIELDS = ('area_m2', 'heating_target_c', 'cooling_target_c', 'length_m')


def edit_item(topology, collection, identifier, name, **changes):
    """Validate through the existing creation rules; preserve IDs and metadata."""
    if topology.get('schema_version') != SCHEMA_VERSION or collection not in EDIT_FIELDS:
        raise TopologyError('invalid_schema')
    if not set(changes) <= set(EDIT_FIELDS[collection]):
        raise TopologyError('unsupported_edit')
    original = next((item for item in topology[collection] if item['id'] == identifier), None)
    if original is None:
        raise TopologyError('invalid_reference')
    if not changes or all(original.get(key) == value for key, value in changes.items()):
        return rename_item(topology, collection, identifier, name)
    data = deepcopy(topology)
    index = next(i for i, item in enumerate(data[collection]) if item['id'] == identifier)
    old = data[collection].pop(index)
    fields = {key: value for key, value in old.items() if key not in ('id', 'name')}
    fields.update(changes)
    # Remove only this record during validation so its own position/entity
    # does not appear as a duplicate; all other references remain intact.
    validated, _ = add_item(data, collection, name, **fields)
    replacement = validated[collection].pop()
    replacement['id'] = identifier
    validated[collection].insert(index, {**old, **replacement})
    return validated
