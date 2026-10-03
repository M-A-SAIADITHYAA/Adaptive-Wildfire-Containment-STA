"""
Tests for ForestGrid and CellState.
"""

import unittest
import numpy as np

from forest_fire_sta.fire_sim.grid import ForestGrid, CellState


class TestForestGrid(unittest.TestCase):
    def setUp(self):
        self.grid = ForestGrid(width=20, height=20, cell_size=25.0)

    def test_initialization(self):
        self.assertEqual(self.grid.width, 20)
        self.assertEqual(self.grid.height, 20)
        self.assertTrue(np.all(self.grid.state == CellState.UNBURNED))
        self.assertTrue(np.all(self.grid.fuel_density > 0.5))

    def test_bounds(self):
        self.assertTrue(self.grid.in_bounds(0, 0))
        self.assertTrue(self.grid.in_bounds(19, 19))
        self.assertFalse(self.grid.in_bounds(-1, 0))
        self.assertFalse(self.grid.in_bounds(20, 10))

    def test_ignite_and_burn(self):
        self.assertTrue(self.grid.is_burnable(5, 5))
        success = self.grid.ignite(5, 5)
        self.assertTrue(success)
        self.assertEqual(self.grid.state[5, 5], CellState.BURNING)
        # Cannot re-ignite actively burning cell
        self.assertFalse(self.grid.ignite(5, 5))

    def test_firebreak_construction(self):
        self.grid.build_firebreak(7, 7)
        self.assertEqual(self.grid.state[7, 7], CellState.FIREBREAK)
        self.assertEqual(self.grid.fuel_density[7, 7], 0.0)
        self.assertFalse(self.grid.is_burnable(7, 7))

    def test_slope_calculation(self):
        self.grid.elevation[5, 5] = 0.0
        self.grid.elevation[5, 6] = 25.0  # 25m rise over 25m run -> slope = 1.0
        slope = self.grid.slope_between(5, 5, 6, 5)
        self.assertAlmostEqual(slope, 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
