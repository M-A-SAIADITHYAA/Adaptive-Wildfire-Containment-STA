"""
Tests for containment perimeter generation and multi-agent coordination.
"""

import unittest
import numpy as np

from forest_fire_sta.fire_sim.grid import ForestGrid
from forest_fire_sta.fire_sim.weather import WeatherProfile
from forest_fire_sta.fire_sim.spread_model import FireSpreadModel
from forest_fire_sta.containment.agent import Bulldozer
from forest_fire_sta.containment.perimeter_planner import PerimeterPlanner


class TestContainment(unittest.TestCase):
    def setUp(self):
        self.grid = ForestGrid(width=30, height=30, cell_size=20.0)
        self.weather = WeatherProfile(base_speed=5.0, base_direction_deg=45.0)
        self.spread = FireSpreadModel(grid=self.grid, weather=self.weather, base_ros=0.45)
        self.grid.ignite(10, 10)
        self.t_fire = self.spread.compute_fire_arrival_times(start_time=0.0, max_horizon=600.0)
        self.perimeter_planner = PerimeterPlanner(grid=self.grid, spread_model=self.spread)

    def test_line_interpolation(self):
        pts = self.perimeter_planner._interpolate_line((0, 0), (3, 3))
        self.assertEqual(pts[0], (0, 0))
        self.assertEqual(pts[-1], (3, 3))
        self.assertEqual(len(pts), 4)

    def test_multi_agent_containment_planning(self):
        d1 = Bulldozer(agent_id="d1", start_x=5, start_y=25, cut_time_per_cell=10.0)
        d2 = Bulldozer(agent_id="d2", start_x=25, start_y=25, cut_time_per_cell=10.0)
        line = [(x, 25) for x in range(5, 26)]

        plan = self.perimeter_planner.plan_multi_agent_containment(
            agents=[d1, d2],
            target_cells=line,
            t_fire=self.t_fire,
            start_time=0.0,
        )
        self.assertTrue(plan.is_feasible)
        self.assertIn("d1", plan.agent_plans)
        self.assertIn("d2", plan.agent_plans)
        self.assertGreater(len(plan.agent_plans["d1"]), 0)
        self.assertGreater(len(plan.agent_plans["d2"]), 0)


if __name__ == "__main__":
    unittest.main()
