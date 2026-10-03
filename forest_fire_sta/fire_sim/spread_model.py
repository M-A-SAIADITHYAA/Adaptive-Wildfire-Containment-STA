"""
Physical wildfire spread modeling and Fire Arrival Time (T_fire) computation.
Incorporates Rothermel-inspired Rate of Spread (ROS) accounting for fuel load,
moisture, topographical slope, and dynamic wind forcing.
"""

import heapq
import math
from typing import Dict, List, Tuple, Optional
import numpy as np

from .grid import ForestGrid, CellState
from .weather import WeatherProfile, WindVector


class FireSpreadModel:
    """
    Wildfire propagation engine.
    Calculates rate of spread (m/min or m/s) and computes dynamic fire arrival times.
    """

    def __init__(
        self,
        grid: ForestGrid,
        weather: WeatherProfile,
        base_ros: float = 0.5,     # Base spread rate in m/s (zero wind, flat terrain)
        c_wind: float = 0.3,       # Wind coefficient
        wind_exp: float = 1.2,      # Wind speed exponent
        c_slope: float = 5.275,     # Rothermel slope multiplier
    ):
        self.grid = grid
        self.weather = weather
        self.base_ros = base_ros
        self.c_wind = c_wind
        self.wind_exp = wind_exp
        self.c_slope = c_slope

    def calculate_ros(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        t: float,
    ) -> float:
        """
        Calculate directional Rate of Spread (ROS) from (from_x, from_y) to (to_x, to_y) at time t.
        Returns ROS in meters per second. If target is non-burnable, returns 0.0.
        """
        # Target must be burnable
        if not self.grid.is_burnable(to_x, to_y):
            return 0.0

        fuel_k = float(self.grid.fuel_density[to_y, to_x])
        moist_m = float(self.grid.fuel_moisture[to_y, to_x])
        if fuel_k <= 0.05:
            return 0.0

        # Fuel factor: high moisture dampens flame speed
        phi_fuel = fuel_k / (1.0 + 3.0 * moist_m)

        # Vector from source to target
        dx = (to_x - from_x)
        dy = (to_y - from_y)
        angle_rad = math.atan2(dx, dy)  # 0 = North (+y), pi/2 = East (+x)

        # Wind factor
        wind = self.weather.get_wind(t)
        if wind.speed > 1e-4:
            # Angle difference between wind direction and spread vector
            delta_angle = (wind.direction_rad - angle_rad + math.pi) % (2 * math.pi) - math.pi
            cos_align = math.cos(delta_angle)
            if cos_align > 0:
                phi_wind = self.c_wind * (wind.speed ** self.wind_exp) * cos_align
            else:
                phi_wind = -0.2 * abs(cos_align)  # Slight backing fire resistance
        else:
            phi_wind = 0.0

        # Topographical slope factor
        slope = self.grid.slope_between(from_x, from_y, to_x, to_y)
        if slope > 0:
            phi_slope = self.c_slope * (slope ** 2)
        else:
            phi_slope = -0.3 * abs(slope)  # Fire travels slower downhill

        # Combined multiplier
        ros_mult = max(0.05, 1.0 + phi_wind + phi_slope)
        ros = self.base_ros * phi_fuel * ros_mult
        return max(0.0, ros)

    def compute_fire_arrival_times(
        self,
        start_time: float = 0.0,
        max_horizon: float = 3600.0,
    ) -> np.ndarray:
        """
        Computes the Fire Arrival Time Field T_fire(x, y) for all cells using
        a fast continuous wavefront/Dijkstra method.
        
        Returns:
            np.ndarray: 2D array of shape (height, width) with arrival time (seconds),
                        or np.inf if unreached within horizon.
        """
        t_fire = np.full((self.grid.height, self.grid.width), np.inf, dtype=np.float64)
        pq: List[Tuple[float, int, int]] = []

        # Initialize queue with currently active burning cells
        for y in range(self.grid.height):
            for x in range(self.grid.width):
                st = self.grid.state[y, x]
                if st == CellState.BURNING:
                    t_fire[y, x] = start_time
                    heapq.heappush(pq, (start_time, x, y))
                elif st == CellState.BURNED:
                    t_fire[y, x] = start_time  # Already burned

        visited = set()

        while pq:
            curr_t, cx, cy = heapq.heappop(pq)

            if curr_t > t_fire[cy, cx] + 1e-6:
                continue
            if (cx, cy) in visited:
                continue
            visited.add((cx, cy))

            if curr_t >= start_time + max_horizon:
                continue

            for nx, ny in self.grid.get_neighbors(cx, cy, diagonal=True):
                if (nx, ny) in visited:
                    continue
                if not self.grid.is_burnable(nx, ny):
                    continue

                ros = self.calculate_ros(cx, cy, nx, ny, curr_t)
                if ros <= 1e-4:
                    continue

                # Distance between cell centers in meters
                diag = (cx != nx) and (cy != ny)
                dist = (math.sqrt(2) if diag else 1.0) * self.grid.cell_size

                delta_t = dist / ros
                arr_t = curr_t + delta_t

                if arr_t < t_fire[ny, nx]:
                    t_fire[ny, nx] = arr_t
                    heapq.heappush(pq, (arr_t, nx, ny))

        return t_fire

    def step_simulation(self, dt: float, current_time: float) -> List[Tuple[int, int]]:
        """
        Advance actual grid fire simulation by dt seconds.
        Returns list of newly ignited cells (x, y).
        """
        newly_ignited: List[Tuple[int, int]] = []
        burning_cells = [
            (x, y)
            for y in range(self.grid.height)
            for x in range(self.grid.width)
            if self.grid.state[y, x] == CellState.BURNING
        ]

        # Decay burning cells
        for x, y in burning_cells:
            self.grid.burn_timer[y, x] -= dt
            if self.grid.burn_timer[y, x] <= 0:
                self.grid.state[y, x] = CellState.BURNED

        # Propagate from active burning cells
        for bx, by in burning_cells:
            for nx, ny in self.grid.get_neighbors(bx, by, diagonal=True):
                if self.grid.is_burnable(nx, ny):
                    ros = self.calculate_ros(bx, by, nx, ny, current_time)
                    if ros <= 1e-4:
                        continue
                    diag = (bx != nx) and (by != ny)
                    dist = (math.sqrt(2) if diag else 1.0) * self.grid.cell_size
                    spread_time = dist / ros

                    # Probability of ignition over step dt
                    # P = 1 - exp(-dt / spread_time)
                    prob = 1.0 - math.exp(-dt / max(1e-3, spread_time))
                    if np.random.rand() < prob:
                        if self.grid.ignite(nx, ny):
                            newly_ignited.append((nx, ny))

        return newly_ignited
