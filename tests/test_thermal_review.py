import unittest
from datetime import datetime, timezone
from custom_components.irpat_efficiency.topology import empty_topology, add_item
from custom_components.irpat_efficiency.thermal_review import zone_weather, review_curve, review_inertia


class ThermalReviewTests(unittest.TestCase):
    def setUp(self):
        t, f = add_item(empty_topology(), 'floors', 'Floor')
        t, self.z = add_item(t, 'zones', 'Zone', operating_mode='weather', circuit_control='manual')
        t, self.r = add_item(t, 'rooms', 'Room', floor_id=f, heating_target_c=22)
        t, self.m = add_item(t, 'manifolds', 'Manifold', floor_id=f, zone_id=self.z)
        t, _ = add_item(t, 'circuits', 'Loop', manifold_id=self.m, room_id=self.r, position=1)
        t, _ = add_item(t, 'bindings', 'Sensor', room_id=self.r, entity_id='sensor.room')
        t['outdoor_entity_id'] = 'sensor.outside'
        self.t = t
        self.end = 3*86400
        self.s = {self.r: {str(s):21 for s in range(0,self.end+1,300)},
                  '__outdoor__': {str(s):2 for s in range(0,self.end+1,300)}}

    def curve(self, **kw):
        args = dict(now=self.end, since=0, reviewed=True)
        args.update(kw)
        return review_curve(self.t,self.s,[],self.z,self.end,[0,86400,172800],**args)

    def test_reviewed_curve_reuses_displayed_data(self):
        self.assertFalse(zone_weather(self.t,self.s,self.end,0)[self.z][0]['comparable'])
        result = self.curve()
        self.assertEqual(result['status'],'review_offset')
        self.assertEqual(result['direction'],'raise')

    def test_unreviewed_and_old_epoch(self):
        with self.assertRaisesRegex(ValueError,'review_required'):
            self.curve(reviewed=False)
        with self.assertRaisesRegex(ValueError,'incompatible_history'):
            self.curve(since=1)

    def test_onoff_stays_monitor_only(self):
        self.t['zones'][0]['operating_mode']='onoff'
        self.assertEqual(self.curve()['status'],'monitor_only')

    def test_adjustment_excludes_old_windows(self):
        journal=[{'manifold_id':self.m,'phase':'after','timestamp':datetime.fromtimestamp(100,timezone.utc).isoformat()}]
        with self.assertRaisesRegex(ValueError,'adjustment_since_observation'):
            review_curve(self.t,self.s,journal,self.z,self.end,[0,86400,172800],now=self.end,since=0,reviewed=True)

    def test_duplicate_window_rejected(self):
        with self.assertRaisesRegex(ValueError,'invalid_interval'):
            review_curve(self.t,self.s,[],self.z,self.end,[0,0],now=self.end,since=0,reviewed=True)

    def test_inertia_review_and_rate(self):
        self.s[self.r]['7200']=20
        result=review_inertia(self.t,self.s,self.r,0,7200,now=self.end,since=0,heat_off_confirmed=True,comparable=True)
        self.assertEqual(result['status'],'observed')
        self.assertEqual(result['rate_c_per_h'],.5)
        self.assertTrue(result['advisory_only'])

    def test_inertia_gap_and_unreviewed(self):
        del self.s[self.r]['300']
        args=dict(now=self.end,since=0,heat_off_confirmed=True,comparable=True)
        self.assertEqual(review_inertia(self.t,self.s,self.r,0,7200,**args)['status'],'insufficient_data')
        args['comparable']=False
        self.assertEqual(review_inertia(self.t,self.s,self.r,0,7200,**args)['status'],'review_required')

    def test_inertia_future_epoch_and_sensor_conflicts(self):
        for now,since in [(7100,0),(self.end,1)]:
            with self.assertRaisesRegex(ValueError,'invalid_interval'):
                review_inertia(self.t,self.s,self.r,0,7200,now=now,since=since)
        self.t['outdoor_entity_id']='sensor.room'
        with self.assertRaisesRegex(ValueError,'missing_temperature_configuration'):
            review_inertia(self.t,self.s,self.r,0,7200,now=self.end,since=0)
        self.assertNotIn(self.z,zone_weather(self.t,self.s,self.end,0))
