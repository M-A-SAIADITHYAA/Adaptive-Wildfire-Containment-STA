"""
Dynamic online re-planning engine for closed-loop wildfire containment.
Monitors line integrity against evolving fire arrival times and triggers real-time
Space-Time A* re-routing when environmental shifts or breaches occur.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
import numpy as np

from ..fire_sim.grid import ForestGrid, CellState
from ..fire_sim.spread_model import FireSpreadModel
from ..fire_sim.weather import WeatherProfile
from .agent import SuppressionAgent, PlanStep, ActionType
from .space_time_astar import SpaceTimeAStarPlanner
from .perimeter_planner import PerimeterPlanner, ContainmentPlan


@dataclass
class ReplanningEvent:
    """Record of an online dynamic replanning intervention."""
    time: float
    trigger: str
    compromised_cells: List[Tuple[int, int]]
    agent_states: Dict[str, Tuple[int, int]]
    success: bool
    description: str


class DynamicReplanner:
    """
    Closed-loop simulation controller and dynamic replanner.
    """

    def __init__(
        self,
        grid: ForestGrid,
        spread_model: FireSpreadModel,
        agents: List[SuppressionAgent],
        perimeter_planner: Optional[PerimeterPlanner] = None,
        check_interval: float = 15.0,  # Integrity verification frequency (seconds)
    ):
        self.grid = grid
        self.spread_model = spread_model
        self.agents = agents
        self.sta_planner = SpaceTimeAStarPlanner(grid=grid)
        self.perimeter_planner = perimeter_planner or PerimeterPlanner(
            grid=grid, spread_model=spread_model, planner=self.sta_planner
        )
        self.check_interval = check_interval

        self.current_time = 0.0
        self.events: List[ReplanningEvent] = []
        self.t_fire_cache: Optional[np.ndarray] = None
        self.last_check_time = 0.0

    def check_plan_integrity(
        self,
        t_fire: np.ndarray,
    ) -> Dict[str, List[Tuple[int, int]]]:
        """
        Validates all future planned actions against updated fire arrival times.
        Returns dict of agent_id -> list of compromised (x, y) cells.
        """
        compromised: Dict[str, List[Tuple[int, int]]] = {}
        for agent in self.agents:
            bad_cells = []
            for step in agent.plan[agent.plan_index:]:
                fire_arr = t_fire[step.y, step.x]
                if step.end_time > (fire_arr - agent.safety_buffer):
                    bad_cells.append((step.x, step.y))
            if bad_cells:
                compromised[agent.agent_id] = bad_cells
        return compromised

    def execute_simulation(
        self,
        total_duration: float = 600.0,
        dt: float = 2.0,
        initial_plan: Optional[ContainmentPlan] = None,
        on_step_callback: Optional[Callable[[float, ForestGrid, List[SuppressionAgent]], None]] = None,
        replan_corridor_provider: Optional[Callable[[float, np.ndarray, List[SuppressionAgent]], List[Tuple[int, int]]]] = None,
    ) -> Dict:
        """
        Run the closed-loop simulation forward in time.
        Executes agents, steps fire spread, monitors safety margins, and triggers
        dynamic STA* re-planning whenever line integrity is compromised.
        """
        self.current_time = 0.0
        self.events.clear()
        self.last_check_time = 0.0

        # Initial T_fire projection
        self.t_fire_cache = self.spread_model.compute_fire_arrival_times(start_time=0.0)

        # Simulation history
        history_timeline = []

        while self.current_time < total_duration:
            # 1. Advance fire spread by dt
            self.spread_model.step_simulation(dt=dt, current_time=self.current_time)

            # 2. Advance agents along their plans
            for agent in self.agents:
                agent.step(dt=dt, current_sim_time=self.current_time, grid=self.grid)

            # 3. Periodically re-evaluate line integrity
            if (self.current_time - self.last_check_time) >= self.check_interval:
                self.last_check_time = self.current_time
                self.t_fire_cache = self.spread_model.compute_fire_arrival_times(
                    start_time=self.current_time
                )

                compromised = self.check_plan_integrity(self.t_fire_cache)
                if compromised:
                    all_bad = []
                    for c_list in compromised.values():
                        all_bad.extend(c_list)

                    trigger_msg = f"Fire front accelerated or shifted; {len(all_bad)} future firebreak cells compromised!"
                    agent_pos = {a.agent_id: (a.x, a.y) for a in self.agents}

                    # Trigger dynamic re-planning!
                    replan_success = self._trigger_replanning(
                        compromised=compromised,
                        replan_corridor_provider=replan_corridor_provider,
                    )

                    self.events.append(
                        ReplanningEvent(
                            time=self.current_time,
                            trigger=trigger_msg,
                            compromised_cells=all_bad,
                            agent_states=agent_pos,
                            success=replan_success,
                            description="Emergency fallback line synthesized via Space-Time A*",
                        )
                    )

            if on_step_callback is not None:
                on_step_callback(self.current_time, self.grid, self.agents)

            # Check if active fire has self-extinguished or been fully contained
            num_burning = np.count_nonzero(self.grid.state == CellState.BURNING)
            if num_burning == 0 and self.current_time > 30.0:
                # Fire is out
                break

            self.current_time += dt

        return {
            "duration": self.current_time,
            "replanning_events": self.events,
            "final_burned_cells": int(np.count_nonzero(self.grid.state == CellState.BURNED)),
            "final_firebreaks": int(np.count_nonzero(self.grid.state == CellState.FIREBREAK)),
            "active_burning": int(np.count_nonzero(self.grid.state == CellState.BURNING)),
        }

    def _trigger_replanning(
        self,
        compromised: Dict[str, List[Tuple[int, int]]],
        replan_corridor_provider: Optional[Callable] = None,
    ) -> bool:
        """
        Clears compromised future steps and invokes Space-Time A* from current agent states.
        """
        self.sta_planner.res_table.clear()
        
        # Provide fallback corridor or compute new isochrone contour further out
        if replan_corridor_provider is not None:
            new_target_cells = replan_corridor_provider(
                self.current_time, self.t_fire_cache, self.agents
            )
        else:
            # Default fallback: find containment corridor with extended buffer
            lead_time = self.current_time + 120.0
            anchors = self.perimeter_planner.find_natural_anchors()
            if len(anchors) >= 2:
                a1, a2 = anchors[0], anchors[1]
            else:
                a1 = (0, self.grid.height // 2)
                a2 = (self.grid.width - 1, self.grid.height // 2)

            new_target_cells = self.perimeter_planner.generate_isochrone_containment_line(
                t_fire=self.t_fire_cache,
                target_lead_time=lead_time,
                anchor_a=a1,
                anchor_b=a2,
            )

        if not new_target_cells:
            return False

        # Plan new firebreak allocations for agents from their current locations
        replan_result = self.perimeter_planner.plan_multi_agent_containment(
            agents=self.agents,
            target_cells=new_target_cells,
            t_fire=self.t_fire_cache,
            start_time=self.current_time,
        )

        return replan_result.is_feasible
