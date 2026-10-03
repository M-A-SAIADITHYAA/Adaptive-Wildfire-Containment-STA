"""
Tests for Space-Time A* Search and Reservation Table.
"""

import unittest
import numpy as np

from forest_fire_sta.fire_sim.grid import ForestGrid
from forest_fire_sta.fire_sim.weather import WeatherProfile
from forest_fire_sta.fire_sim.spread_model import FireSpreadModel
from forest_fire_sta.containment.agent import Bulldozer, ActionType
from forest_fire_sta.containment.space_time_astar import SpaceTimeAStarPlanner, ReservationTable


class TestSpaceTimeAStar(unittest.TestCase):
    def setUp(self):
        self.grid = ForestGrid(width=30, height=30, cell_size=20.0, default_fuel=0.8)
        self.weather = WeatherProfile(base_speed=5.0, base_direction_deg=0.0)  # North wind
        self.spread = FireSpreadModel(grid=self.grid, weather=self.weather, base_ros=0.5)

        # Ignite at (15, 10)
        self.grid.ignite(15, 10)
        self.t_fire = self.spread.compute_fire_arrival_times(start_time=0.0, max_horizon=600.0)

        self.res_table = ReservationTable(time_bucket_size=5.0)
        self.planner = SpaceTimeAStarPlanner(grid=self.grid, reservation_table=self.res_table)
        self.dozer = Bulldozer(agent_id="dozer_test", start_x=5, start_y=22, speed=1.5, cut_time_per_cell=15.0)

    def test_reservation_table(self):
        self.assertTrue(self.res_table.is_available(10, 10, 0.0, 30.0, "agent_1"))
        self.res_table.reserve(10, 10, 10.0, 25.0, "agent_1")

        # Same agent can re-check
        self.assertTrue(self.res_table.is_available(10, 10, 10.0, 25.0, "agent_1"))

        # Other agent is blocked during overlap
        self.assertFalse(self.res_table.is_available(10, 10, 15.0, 20.0, "agent_2"))
        self.assertFalse(self.res_table.is_available(10, 10, 5.0, 12.0, "agent_2"))

        # Non-overlapping window is available
        self.assertTrue(self.res_table.is_available(10, 10, 0.0, 9.0, "agent_2"))
        self.assertTrue(self.res_table.is_available(10, 10, 26.0, 50.0, "agent_2"))

    def test_transit_planning(self):
        plan = self.planner.plan_transit_path(
            agent=self.dozer,
            start_x=5,
            start_y=22,
            start_t=0.0,
            goal_x=12,
            goal_y=22,
            t_fire=self.t_fire,
        )
        self.assertIsNotNone(plan)
        self.assertGreater(len(plan), 0)
        self.assertEqual(plan[-1].x, 12)
        self.assertEqual(plan[-1].y, 22)

    def test_firebreak_trajectory(self):
        cut_targets = [(5, 22), (6, 22), (7, 22)]
        plan = self.planner.plan_firebreak_trajectory(
            agent=self.dozer,
            start_x=5,
            start_y=22,
            start_t=0.0,
            cut_cells=cut_targets,
            t_fire=self.t_fire,
        )
        self.assertIsNotNone(plan)
        cuts = [s for s in plan if s.action == ActionType.CUT_FIREBREAK]
        self.assertEqual(len(cuts), 3)


if __name__ == "__main__":
    unittest.main()
