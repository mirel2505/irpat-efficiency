"""Optional, typed sensor bindings and explicit unit conversion."""
from copy import deepcopy
from math import isfinite

ROLE_GROUPS = {
    'rooms': ('humidity', 'surface_temperature'),
    'sources': ('supply_temperature', 'return_temperature', 'flow', 'electrical_power',
                'electrical_energy', 'thermal_power', 'thermal_energy', 'compressor', 'defrost',
                'burner', 'pump', 'pressure'),
    'manifolds': ('supply_temperature', 'return_temperature', 'flow', 'pressure', 'pump'),
}
TEMPERATURES = ('surface_temperature', 'supply_temperature', 'return_temperature')
BINARY = ('compressor', 'defrost', 'burner', 'pump')
UNITS = {
    'humidity': ('%', {'%': 1}),
    'flow': ('m³/h', {'m³/h': 1, 'm3/h': 1, 'L/min': .06, 'l/min': .06, 'L/h': .001, 'l/h': .001}),
    'electrical_power': ('W', {'W': 1, 'kW': 1000}),
    'thermal_power': ('W', {'W': 1, 'kW': 1000}),
    'electrical_energy': ('kWh', {'Wh': .001, 'kWh': 1, 'MWh': 1000}),
    'thermal_energy': ('kWh', {'Wh': .001, 'kWh': 1, 'MWh': 1000}),
    'pressure': ('bar', {'bar': 1, 'kPa': .01, 'Pa': .00001, 'MPa': 10}),
}


def set_binding(topology, group, owner_id, role, entity_id, name=None):
    """Replace or remove one role; never rename the Home Assistant entity."""
    if role not in ROLE_GROUPS.get(group, ()):
        raise ValueError('invalid_role')
    if not any(item['id'] == owner_id for item in topology.get(group, [])):
        raise ValueError('invalid_reference')
    data = deepcopy(topology)
    bindings = data.setdefault('telemetry', [])
    bindings[:] = [b for b in bindings if (b['group'], b['owner_id'], b['role']) != (group, owner_id, role)]
    if entity_id is None:
        return data
    prefix = 'binary_sensor.' if role in BINARY else 'sensor.'
    if not isinstance(entity_id, str) or not entity_id.startswith(prefix) or len(entity_id) == len(prefix):
        raise ValueError('invalid_entity')
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name.strip()) > 120):
        raise ValueError('invalid_name')
    bindings.append(dict(group=group, owner_id=owner_id, role=role, entity_id=entity_id,
                         name=name.strip() if name else role))
    return data


def convert(role, value, unit):
    """Return normalized (value, unit) or (None, canonical unit)."""
    if role in BINARY:
        return ({'on': True, 'off': False}.get(value) if isinstance(value, str) else None, None)
    if role in TEMPERATURES:
        from .temperature import temperature_c
        return temperature_c(value, unit), '°C'
    if role not in UNITS:
        raise ValueError('invalid_role')
    canonical, factors = UNITS[role]
    if isinstance(value, bool) or unit not in factors:
        return None, canonical
    try:
        number = float(value) * factors[unit]
    except (TypeError, ValueError, OverflowError):
        return None, canonical
    if not isfinite(number) or (number < 0 and role not in ('thermal_power', 'thermal_energy')):
        return None, canonical
    if role == 'humidity' and not 0 < number <= 100:
        return None, canonical
    return number, canonical
