"""
Terrain grid and fuel representation for forest fire simulation.
"""

from enum import IntEnum
from typing import List, Tuple, Optional
import numpy as np


class CellState(IntEnum):
    """Lattice cell operational states."""
    UNBURNED = 0
    BURNING = 1
    BURNED = 2
    FIREBREAK = 3
    BARRIER = 4  # Water bodies, rock outcrops, paved roads


class ForestGrid:
    """
    2D Topographical and Fuel Grid representing a forested landscape.
    
    Attributes:
        width (int): Grid width (number of columns / X-dimension).
        height (int): Grid height (number of rows / Y-dimension).
        cell_size (float): Physical dimension of each cell edge in meters.
        elevation (np.ndarray): 2D array of elevations in meters (H x W).
        fuel_density (np.ndarray): Fuel flammability load factor in [0.0, 1.0].
        fuel_moisture (np.ndarray): Fuel moisture content in [0.0, 1.0].
        asset_values (np.ndarray): Economic/ecological value at risk >= 0.
        state (np.ndarray): Grid of CellState values.
        burn_duration (float): Time steps a burning cell remains actively burning.
        burn_timer (np.ndarray): Remaining burn time for currently burning cells.
    """

    def __init__(
        self,
        width: int,
        height: int,
        cell_size: float = 25.0,
        default_fuel: float = 0.8,
        default_moisture: float = 0.15,
        burn_duration: float = 45.0,
    ):
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.burn_duration = burn_duration

        self.elevation = np.zeros((height, width), dtype=np.float32)
        self.fuel_density = np.full((height, width), default_fuel, dtype=np.float32)
        self.fuel_moisture = np.full((height, width), default_moisture, dtype=np.float32)
        self.asset_values = np.zeros((height, width), dtype=np.float32)
        self.state = np.full((height, width), CellState.UNBURNED, dtype=np.int32)
        self.burn_timer = np.zeros((height, width), dtype=np.float32)

    def in_bounds(self, x: int, y: int) -> bool:
        """Check if coordinates (x, y) lie within the grid boundaries."""
        return 0 <= x < self.width and 0 <= y < self.height

    def is_burnable(self, x: int, y: int) -> bool:
        """Return True if cell can catch fire."""
        if not self.in_bounds(x, y):
            return False
        return (
            self.state[y, x] == CellState.UNBURNED
            and self.fuel_density[y, x] > 0.05
        )

    def is_traversable_for_agent(self, x: int, y: int, max_slope: float = 0.6) -> bool:
        """
        Check if an agent can physically occupy the cell based on terrain and barriers.
        Does not check active fire (safety checks are performed by STA*).
        """
        if not self.in_bounds(x, y):
            return False
        if self.state[y, x] == CellState.BARRIER:
            return False
        # Calculate local slope gradient
        slope = self.local_slope(x, y)
        return slope <= max_slope

    def local_slope(self, x: int, y: int) -> float:
        """Calculate maximum gradient (tan theta) around (x, y)."""
        max_grad = 0.0
        z0 = self.elevation[y, x]
        for nx, ny in self.get_neighbors(x, y, diagonal=False):
            dist = self.cell_size
            dz = abs(self.elevation[ny, nx] - z0)
            grad = dz / dist
            if grad > max_grad:
                max_grad = grad
        return max_grad

    def slope_between(self, x1: int, y1: int, x2: int, y2: int) -> float:
        """
        Calculates the directional slope (tan theta) from (x1, y1) to (x2, y2).
        Positive when moving uphill, negative when moving downhill.
        """
        dist = np.hypot((x2 - x1) * self.cell_size, (y2 - y1) * self.cell_size)
        if dist == 0:
            return 0.0
        dz = float(self.elevation[y2, x2] - self.elevation[y1, x1])
        return dz / dist

    def get_neighbors(
        self, x: int, y: int, diagonal: bool = True
    ) -> List[Tuple[int, int]]:
        """Get valid neighboring coordinates (4- or 8-connected)."""
        offsets = (
            [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
            if diagonal
            else [(-1, 0), (1, 0), (0, -1), (0, 1)]
        )
        neighbors = []
        for dx, dy in offsets:
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                neighbors.append((nx, ny))
        return neighbors

    def ignite(self, x: int, y: int) -> bool:
        """Ignite a cell at (x, y) if burnable."""
        if self.is_burnable(x, y):
            self.state[y, x] = CellState.BURNING
            self.burn_timer[y, x] = self.burn_duration
            return True
        return False

    def build_firebreak(self, x: int, y: int) -> bool:
        """
        Construct a firebreak at (x, y), clearing fuels and rendering it non-burnable.
        """
        if self.in_bounds(x, y) and self.state[y, x] != CellState.BURNING:
            self.state[y, x] = CellState.FIREBREAK
            self.fuel_density[y, x] = 0.0
            return True
        return False

    def set_barrier(self, x: int, y: int):
        """Designate a cell as an impassable natural barrier (e.g., river, road)."""
        if self.in_bounds(x, y):
            self.state[y, x] = CellState.BARRIER
            self.fuel_density[y, x] = 0.0

    def add_barrier_line(self, p1: Tuple[int, int], p2: Tuple[int, int]):
        """Bresenham's line algorithm to draw natural barrier lines (e.g. river/road)."""
        x0, y0 = p1
        x1, y1 = p2
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            self.set_barrier(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def clone(self) -> "ForestGrid":
        """Produce an independent deep copy of the current grid state."""
        new_grid = ForestGrid(
            self.width,
            self.height,
            self.cell_size,
            burn_duration=self.burn_duration,
        )
        new_grid.elevation = self.elevation.copy()
        new_grid.fuel_density = self.fuel_density.copy()
        new_grid.fuel_moisture = self.fuel_moisture.copy()
        new_grid.asset_values = self.asset_values.copy()
        new_grid.state = self.state.copy()
        new_grid.burn_timer = self.burn_timer.copy()
        return new_grid
