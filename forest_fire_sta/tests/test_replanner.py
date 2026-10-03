"""
Tests for Dynamic Replanner and breach recovery.
"""

import unittest
import numpy as np

from forest_fire_sta.fire_sim.grid import ForestGrid
from forest_fire_sta.fire_sim.weather import WeatherProfile
from forest_fire_sta.fire_sim.spread_model import FireSpreadModel
from forest_fire_sta.containment.agent import Bulldozer, ActionType, PlanStep
from forest_fire_sta.containment.dynamic_replanner import DynamicReplanner


class TestDynamicReplanner(unittest.TestCase):
    def setUp(self):
        self.grid = ForestGrid(width=30, height=30, cell_size=20.0)
        self.weather = WeatherProfile(base_speed=6.0, base_direction_deg=90.0)
        self.spread = FireSpreadModel(grid=self.grid, weather=self.weather, base_ros=0.5)
        self.grid.ignite(10, 10)

        self.dozer = Bulldozer(agent_id="d1", start_x=12, start_y=10, safety_buffer=50.0)
        self.replanner = DynamicReplanner(
            grid=self.grid,
            spread_model=self.spread,
            agents=[self.dozer],
            check_interval=10.0,
        )

    def test_integrity_check_detects_compromise(self):
        # Create an artificial plan where bulldozer plans to cut right in front of fire late
        t_fire = np.full((30, 30), 20.0)  # Fire arrives everywhere at 20s
        self.dozer.plan = [
            PlanStep(action=ActionType.CUT_FIREBREAK, x=15, y=10, start_time=10.0, end_time=25.0)
        ]
        self.dozer.plan_index = 0

        compromised = self.replanner.check_plan_integrity(t_fire)
        self.assertIn("d1", compromised)
        self.assertEqual(compromised["d1"], [(15, 10)])


if __name__ == "__main__":
    unittest.main()
