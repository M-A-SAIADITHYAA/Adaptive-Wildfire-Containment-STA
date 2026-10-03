"""
Suppression resource definitions (Bulldozers, Hand Crews) and operational constraints.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import math

from ..fire_sim.grid import ForestGrid, CellState


class ActionType(Enum):
    TRANSIT = "TRANSIT"
    CUT_FIREBREAK = "CUT_FIREBREAK"
    WAIT = "WAIT"


@dataclass
class PlanStep:
    """A scheduled space-time action for a suppression resource."""
    action: ActionType
    x: int
    y: int
    start_time: float
    end_time: float
    metadata: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class SuppressionAgent:
    """
    Abstract suppression resource capable of moving across terrain and constructing firebreaks.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        start_x: int,
        start_y: int,
        speed: float = 1.5,                # Base transit speed in m/s
        cut_time_per_cell: float = 30.0,   # Seconds to cut/clear one cell of fuel
        max_slope: float = 0.45,           # Maximum traversable slope gradient
        safety_buffer: float = 60.0,       # Minimum required buffer ahead of fire arrival (s)
    ):
        self.agent_id = agent_id
        self.name = name
        self.start_x = start_x
        self.start_y = start_y
        self.x = start_x
        self.y = start_y
        self.current_time = 0.0

        self.speed = speed
        self.cut_time_per_cell = cut_time_per_cell
        self.max_slope = max_slope
        self.safety_buffer = safety_buffer

        self.plan: List[PlanStep] = []
        self.plan_index = 0
        self.completed_firebreaks: List[Tuple[int, int]] = []
        self.history: List[Tuple[float, int, int, str]] = [(0.0, start_x, start_y, "START")]

    def reset(self, start_x: Optional[int] = None, start_y: Optional[int] = None):
        """Reset agent state to initial or given coordinates."""
        if start_x is not None:
            self.start_x = start_x
        if start_y is not None:
            self.start_y = start_y
        self.x = self.start_x
        self.y = self.start_y
        self.current_time = 0.0
        self.plan.clear()
        self.plan_index = 0
        self.completed_firebreaks.clear()
        self.history = [(0.0, self.x, self.y, "START")]

    def travel_time(
        self,
        grid: ForestGrid,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
    ) -> float:
        """
        Compute traversal time (seconds) between adjacent cells accounting for distance and slope.
        Returns infinity if terrain exceeds max slope.
        """
        slope = abs(grid.slope_between(from_x, from_y, to_x, to_y))
        if slope > self.max_slope:
            return float("inf")

        diag = (from_x != to_x) and (from_y != to_y)
        dist = (math.sqrt(2) if diag else 1.0) * grid.cell_size

        # Slope impedance factor (uphill/rough terrain reduces transit speed)
        effective_speed = max(0.2, self.speed * (1.0 - 0.7 * slope))
        return dist / effective_speed

    def cut_duration(self, grid: ForestGrid, x: int, y: int) -> float:
        """
        Time required to clear fuel at cell (x, y). Dense fuel requires longer.
        """
        fuel = float(grid.fuel_density[y, x])
        if fuel <= 0.05:
            return 5.0  # Minimal clearing needed
        return self.cut_time_per_cell * (0.5 + 0.8 * fuel)

    def assign_plan(self, plan: List[PlanStep]):
        """Assign a new planned schedule of space-time actions."""
        self.plan = plan
        self.plan_index = 0

    def step(self, dt: float, current_sim_time: float, grid: ForestGrid) -> Optional[PlanStep]:
        """
        Advance agent along its assigned plan for the current simulation window.
        Constructs firebreak when cutting action completes.
        """
        self.current_time = current_sim_time
        last_completed: Optional[PlanStep] = None

        while self.plan_index < len(self.plan) and current_sim_time >= self.plan[self.plan_index].end_time:
            step = self.plan[self.plan_index]
            self.x = step.x
            self.y = step.y
            if step.action == ActionType.CUT_FIREBREAK:
                grid.build_firebreak(step.x, step.y)
                if (step.x, step.y) not in self.completed_firebreaks:
                    self.completed_firebreaks.append((step.x, step.y))

            self.history.append((step.end_time, step.x, step.y, step.action.value))
            last_completed = step
            self.plan_index += 1

        return last_completed


class Bulldozer(SuppressionAgent):
    """
    Heavy mechanical suppression unit:
    Rapid firebreak construction, moderate speed, restricted by steep slopes.
    """
    def __init__(
        self,
        agent_id: str,
        start_x: int,
        start_y: int,
        name: str = "Bulldozer Crew",
        speed: float = 1.4,
        cut_time_per_cell: float = 20.0,
        max_slope: float = 0.38,
        safety_buffer: float = 60.0,
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            start_x=start_x,
            start_y=start_y,
            speed=speed,
            cut_time_per_cell=cut_time_per_cell,
            max_slope=max_slope,
            safety_buffer=safety_buffer,
        )


class HandCrew(SuppressionAgent):
    """
    Type-1 Wildland Fire Hand Crew:
    Highly maneuverable on steep mountainous slopes, but slower manual cutting rate.
    """
    def __init__(
        self,
        agent_id: str,
        start_x: int,
        start_y: int,
        name: str = "Hand Crew",
        speed: float = 1.2,
        cut_time_per_cell: float = 45.0,
        max_slope: float = 0.65,
        safety_buffer: float = 80.0,
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            start_x=start_x,
            start_y=start_y,
            speed=speed,
            cut_time_per_cell=cut_time_per_cell,
            max_slope=max_slope,
            safety_buffer=safety_buffer,
        )
