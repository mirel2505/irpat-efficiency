import unittest
from copy import deepcopy
from custom_components.irpat_efficiency.report_inputs import prepare_capture


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.t = {'rooms': [{'id':'a','area_m2':30}, {'id':'b','area_m2':10}],
                  'bindings': [{'room_id':'a','entity_id':'sensor.a'}, {'room_id':'b','entity_id':'sensor.b'}],
                  'outdoor_entity_id':'sensor.outside'}
        self.series = {i: {str(t): v for t in range(0,86401,300)}
                       for i,v in [('a',22),('b',20),('__outdoor__',2)]}

    def prepare(self, **kw):
        args = dict(now=86400, configuration_since=0)
        args.update(kw)
        return prepare_capture(self.t,self.series,0,86400,**args)

    def test_weighted(self):
        r = self.prepare()
        self.assertEqual(r['indoor']['0'],21.5)
        self.assertEqual(r['weighting_method'],'area_weighted')
        self.assertEqual(r['outdoor']['86400'],2)

    def test_equal_weight(self):
        self.t['rooms'][0].pop('area_m2')
        r = self.prepare()
        self.assertEqual(r['indoor']['0'],21)
        self.assertEqual(r['weighting_method'],'equal_room_weight')

    def test_missing_endpoint(self):
        del self.series['a']['86400']
        with self.assertRaisesRegex(ValueError,'incomplete_temperature_history'):
            self.prepare()

    def test_configuration_epoch(self):
        for since in (None,1):
            with self.assertRaisesRegex(ValueError,'configuration_changed'):
                self.prepare(configuration_since=since)

    def test_future(self):
        with self.assertRaisesRegex(ValueError,'invalid_interval'):
            self.prepare(now=86399)

    def test_signature(self):
        a = self.prepare()['measurement_signature']
        self.t['rooms'].reverse()
        self.t['bindings'].reverse()
        self.assertEqual(a,self.prepare()['measurement_signature'])
        self.t['bindings'][0]['entity_id']='sensor.other'
        self.assertNotEqual(a,self.prepare()['measurement_signature'])

    def test_duplicate_or_missing_sensor(self):
        for entity in ('sensor.a','sensor.outside'):
            self.t['bindings'][1]['entity_id']=entity
            with self.assertRaisesRegex(ValueError,'missing_temperature_configuration'):
                self.prepare()
        self.t['bindings'].pop()
        with self.assertRaisesRegex(ValueError,'missing_temperature_configuration'):
            self.prepare()

    def test_nonfinite(self):
        self.series['__outdoor__']['300']=float('nan')
        with self.assertRaisesRegex(ValueError,'incomplete_temperature_history'):
            self.prepare()
