"""
Tests for FireSpreadModel and fire arrival calculations.
"""

import unittest
import numpy as np

from forest_fire_sta.fire_sim.grid import ForestGrid, CellState
from forest_fire_sta.fire_sim.weather import WeatherProfile, WindVector
from forest_fire_sta.fire_sim.spread_model import FireSpreadModel


class TestFireSpreadModel(unittest.TestCase):
    def setUp(self):
        self.grid = ForestGrid(width=25, height=25, cell_size=20.0, default_fuel=0.8)
        self.weather = WeatherProfile(base_speed=5.0, base_direction_deg=90.0)  # East wind
        self.spread_model = FireSpreadModel(grid=self.grid, weather=self.weather, base_ros=0.5)

    def test_ros_wind_alignment(self):
        # East neighbor (in wind direction) should have higher ROS than West neighbor (against wind)
        ros_east = self.spread_model.calculate_ros(10, 10, 11, 10, t=0.0)
        ros_west = self.spread_model.calculate_ros(10, 10, 9, 10, t=0.0)
        self.assertGreater(ros_east, ros_west)

    def test_firebreak_stops_ros(self):
        self.grid.build_firebreak(12, 10)
        ros = self.spread_model.calculate_ros(11, 10, 12, 10, t=0.0)
        self.assertEqual(ros, 0.0)

    def test_fire_arrival_times(self):
        self.grid.ignite(5, 5)
        t_fire = self.spread_model.compute_fire_arrival_times(start_time=0.0, max_horizon=600.0)

        # Ignition cell should be at t=0
        self.assertEqual(t_fire[5, 5], 0.0)

        # Cells in downwind direction (East, +x) should ignite earlier than upwind (West, -x)
        self.assertLess(t_fire[5, 8], t_fire[5, 2])
        self.assertFalse(np.isinf(t_fire[5, 7]))


if __name__ == "__main__":
    unittest.main()
