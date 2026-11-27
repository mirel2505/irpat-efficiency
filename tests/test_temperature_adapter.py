"""Test the actual room reader with simulated Home Assistant states."""
import importlib
import sys
import unittest
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

PACKAGE='custom_components.irpat_efficiency.'


class TemperatureAdapterTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.fromtimestamp(10000,timezone.utc)
        modules={name:ModuleType(name) for name in ('homeassistant','homeassistant.util','homeassistant.util.dt')}
        modules['homeassistant.util.dt'].utcnow=lambda:self.now
        modules['homeassistant.util'].dt=modules['homeassistant.util.dt']
        patcher=patch.dict(sys.modules,modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop(PACKAGE+'temperature_reader',None)
        self.reader=importlib.import_module(PACKAGE+'temperature_reader')
        self.hass=SimpleNamespace(states={},config=SimpleNamespace(units=SimpleNamespace(temperature_unit='°C')))

    def state(self,entity,value,age=0,**attributes):
        stamp=datetime.fromtimestamp(10000-age,timezone.utc)
        self.hass.states[entity]=SimpleNamespace(state=str(value),attributes=attributes,
                                                last_reported=stamp,last_updated=stamp)

    def read(self,entity):
        return self.reader.read_binding(self.hass,{'entity_id':entity,'name':entity})

    def test_future(self):
        self.state('sensor.test',22,-5,unit_of_measurement='°C')
        result=self.read('sensor.test')
        self.assertEqual(result['status'],'future')
        self.assertIsNone(result['temperature_c'])
        self.assertEqual(result['age_seconds'],-5)

    def test_old(self):
        self.state('sensor.test',22,7201,unit_of_measurement='°C')
        result=self.read('sensor.test')
        self.assertEqual(result['status'],'stale')
        self.assertIsNone(result['temperature_c'])

    def test_climate_reads_actual_not_setpoint(self):
        self.state('climate.room','heat',0,current_temperature=21.5,temperature=24)
        self.assertEqual(self.read('climate.room')['temperature_c'],21.5)

    def test_fahrenheit(self):
        self.state('sensor.test',68,7200,unit_of_measurement='°F')
        self.assertEqual(self.read('sensor.test')['temperature_c'],20)

    def test_partial_room_excludes_stale_sensor(self):
        self.state('sensor.a',20,0,unit_of_measurement='°C')
        self.state('sensor.b',30,7201,unit_of_measurement='°C')
        topology={'rooms':[{'id':'room','heating_target_c':22}],
                  'bindings':[{'room_id':'room','entity_id':'sensor.'+name,'name':name} for name in ('a','b')]}
        heating=self.reader.read_rooms(self.hass,topology)['room']['heating']
        self.assertEqual(heating['temperature_c'],20)
        self.assertEqual(heating['valid_count'],1)
        self.assertEqual(heating['configured_count'],2)
