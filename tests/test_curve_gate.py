import unittest
from custom_components.irpat_efficiency.curve_gate import gate
from custom_components.irpat_efficiency.topology import add_item, empty_topology

class CurveGateTests(unittest.TestCase):
    def setUp(self):
        t, f = add_item(empty_topology(), "floors", "Floor")
        t, self.z = add_item(t, "zones", "Zone", operating_mode="weather", circuit_control="manual")
        t, self.m = add_item(t, "manifolds", "Manifold", floor_id=f, zone_id=self.z)
        self.ids = []
        for i,target in enumerate((22,24)):
            t,r = add_item(t,"rooms",str(i),floor_id=f,heating_target_c=target)
            t,_ = add_item(t,"bindings",str(i),room_id=r,entity_id=f"sensor.t{i}")
            t,_ = add_item(t,"circuits",str(i),manifold_id=self.m,room_id=r,position=i+1)
            self.ids.append(r)
        t["outdoor_entity_id"]="sensor.outside"
        self.t=t
        self.end=172800
        self.keys=[str(s) for s in range(0,self.end,300)]
    def check(self,a,b,journal=()):
        series={self.ids[0]:dict(zip(self.keys,a)),self.ids[1]:dict(zip(self.keys,b)),
                "__outdoor__":dict.fromkeys(self.keys,5)}
        return gate(self.t,series,journal,self.z,self.end,0)[:2]
    def test_common_and_near_targets(self):
        n=len(self.keys)
        self.assertEqual(self.check([21]*n,[23]*n),("eligible",-1))
        self.assertEqual(self.check([23]*n,[25]*n),("eligible",1))
        self.assertEqual(self.check([22]*n,[24]*n),("near_targets",None))
        self.assertEqual(self.check([23]*n,[23]*n),("balance_required",None))
    def test_averages_hide_instability(self):
        n=len(self.keys)
        a=[21 if i%2 else 19 for i in range(n)]
        b=[21 if i%2 else 23 for i in range(n)]
        self.assertEqual(self.check(a,b),("balance_required",None))
    def test_adjustment_settles(self):
        n=len(self.keys)
        j=[{"manifold_id":self.m,"phase":"adjustment","timestamp":"1970-01-02T00:00:00+00:00"}]
        self.assertEqual(self.check([21]*n,[23]*n,j),("settling",None))
