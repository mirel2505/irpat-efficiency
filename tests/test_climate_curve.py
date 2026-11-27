import unittest
from custom_components.irpat_efficiency.climate_curve import diagnose_curve, comfort_direction


class CurveTests(unittest.TestCase):
    def rows(self, xs, ys):
        return [dict(day=str(i), outdoor_c=x, common_error_c=y, comparable=True,
                     coverage=1, max_residual_c=0.1) for i,(x,y) in enumerate(zip(xs,ys))]

    def check(self, xs, ys, capability="weather_compensation"):
        return diagnose_curve(self.rows(xs,ys), capability=capability, mode="heating")

    def test_steeper(self):
        self.assertEqual(self.check([-5,-2,0,2,5],[-1,-.4,0,.4,1])["direction"], "steeper")

    def test_flatter(self):
        self.assertEqual(self.check([-5,-2,0,2,5],[1,.4,0,-.4,-1])["direction"], "flatter")

    def test_offset(self):
        self.assertEqual(self.check([0,1,2],[.8,.9,1])["direction"], "lower")
        self.assertEqual(self.check([0,1,2],[-.8,-.9,-1])["direction"], "raise")

    def test_fixed_supply(self):
        self.assertEqual(self.check([0,1,2],[1,1,1],"fixed_supply")["status"], "review_fixed_supply")
        self.assertEqual(self.check([0,2,5],[1,1,1],"fixed_supply")["status"], "weather_changed")

    def test_review_required(self):
        rows = self.rows([0,1,2],[1,1,1])
        rows[0]["comparable"] = False
        self.assertEqual(diagnose_curve(rows, capability="weather_compensation", mode="heating")["status"], "insufficient_data")
        rows[0].update(comparable=True,max_residual_c=.8)
        self.assertEqual(diagnose_curve(rows, capability="weather_compensation", mode="heating")["status"], "insufficient_data")

    def test_duplicate(self):
        rows = self.rows([0,1,2],[1,1,1])
        rows[1]["day"] = rows[0]["day"]
        self.assertEqual(diagnose_curve(rows, capability="weather_compensation", mode="heating")["status"], "duplicate_day")

    def test_monitor(self):
        self.assertEqual(self.check([0,1,2],[1,1,1],"monitor_only")["status"], "monitor_only")
        self.assertEqual(diagnose_curve([], capability="weather_compensation", mode="cooling")["status"], "monitor_only")

    def test_near_targets(self):
        self.assertEqual(self.check([0,1,2],[.1,-.2,.2])["status"], "near_targets")

    def test_comfort(self):
        self.assertEqual(comfort_direction(1, mode="heating", capability="weather_compensation"), "raise_supply")
        self.assertEqual(comfort_direction(-1, mode="heating", capability="fixed_supply"), "lower_supply")
        self.assertEqual(comfort_direction(1, mode="cooling", capability="fixed_supply"), "raise_supply")
        self.assertEqual(comfort_direction(-1, mode="cooling", capability="fixed_supply"), "condensation_review_required")
        self.assertEqual(comfort_direction(1, mode="heating", capability="monitor_only"), "monitor_only")
