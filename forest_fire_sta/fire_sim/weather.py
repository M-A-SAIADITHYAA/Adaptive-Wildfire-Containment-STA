"""
Dynamic weather and wind vector modeling for forest fire spread.
"""

import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Callable


@dataclass
class WindVector:
    """
    Wind velocity vector at a specific time or location.
    
    Attributes:
        speed (float): Wind speed in m/s.
        direction_deg (float): Direction wind is blowing TOWARDS in degrees [0, 360).
                               0 = North (+y in standard math, or north-bound),
                               90 = East (+x), 180 = South, 270 = West.
    """
    speed: float
    direction_deg: float

    @property
    def direction_rad(self) -> float:
        return math.radians(self.direction_deg)

    @property
    def u(self) -> float:
        """East-West velocity component (m/s), positive East (+x)."""
        return self.speed * math.sin(self.direction_rad)

    @property
    def v(self) -> float:
        """North-South velocity component (m/s), positive North (+y)."""
        return self.speed * math.cos(self.direction_rad)

    def heading_vector(self) -> Tuple[float, float]:
        """Normalized unit vector (dx, dy) in direction of wind propagation."""
        if self.speed <= 1e-6:
            return (0.0, 0.0)
        return (math.sin(self.direction_rad), math.cos(self.direction_rad))


class WeatherProfile:
    """
    Dynamic weather schedule providing time-varying wind conditions.
    Supports static wind, planned shifts, rotations, and custom functions.
    """

    def __init__(
        self,
        base_speed: float = 5.0,
        base_direction_deg: float = 45.0,
        schedule: Optional[List[Tuple[float, float, float]]] = None,
        custom_fn: Optional[Callable[[float], WindVector]] = None,
    ):
        """
        Args:
            base_speed: Initial wind speed (m/s).
            base_direction_deg: Initial wind direction (degrees).
            schedule: Optional list of (timestamp, new_speed, new_direction_deg).
                      Wind updates when current time reaches or exceeds timestamp.
            custom_fn: Optional custom callable f(t) -> WindVector.
        """
        self.base_speed = base_speed
        self.base_direction_deg = base_direction_deg % 360.0
        self.schedule = sorted(schedule, key=lambda s: s[0]) if schedule else []
        self.custom_fn = custom_fn

    def get_wind(self, t: float) -> WindVector:
        """Return the active WindVector at time t."""
        if self.custom_fn is not None:
            return self.custom_fn(t)

        cur_speed = self.base_speed
        cur_dir = self.base_direction_deg

        for shift_t, spd, direct in self.schedule:
            if t >= shift_t:
                cur_speed = spd
                cur_dir = direct % 360.0
            else:
                break

        return WindVector(speed=cur_speed, direction_deg=cur_dir)

    def add_shift(self, t: float, speed: float, direction_deg: float):
        """Add a scheduled abrupt wind shift at time t."""
        self.schedule.append((t, speed, direction_deg % 360.0))
        self.schedule.sort(key=lambda s: s[0])
