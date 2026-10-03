"""
Strategic containment perimeter planning, anchor selection, and multi-agent corridor allocation.
"""

from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Tuple
import numpy as np

from ..fire_sim.grid import ForestGrid, CellState
from ..fire_sim.spread_model import FireSpreadModel
from .agent import SuppressionAgent, PlanStep
from .space_time_astar import SpaceTimeAStarPlanner, ReservationTable


@dataclass
class ContainmentPlan:
    """Consolidated containment operation plan across all suppression resources."""
    agent_plans: Dict[str, List[PlanStep]]
    containment_cells: List[Tuple[int, int]]
    anchor_points: List[Tuple[int, int]]
    planned_horizon: float
    is_feasible: bool
    metadata: dict


class PerimeterPlanner:
    """
    Computes strategic containment corridors and assigns space-time tasks to suppression crews.
    """

    def __init__(
        self,
        grid: ForestGrid,
        spread_model: FireSpreadModel,
        planner: Optional[SpaceTimeAStarPlanner] = None,
    ):
        self.grid = grid
        self.spread_model = spread_model
        self.planner = planner or SpaceTimeAStarPlanner(grid=grid)

    def find_natural_anchors(
        self,
        search_radius: int = 20,
    ) -> List[Tuple[int, int]]:
        """
        Identify natural anchor points (water, rock, roads, or boundary cells).
        """
        anchors = []
        for y in range(self.grid.height):
            for x in range(self.grid.width):
                if self.grid.state[y, x] in (CellState.BARRIER, CellState.BURNED):
                    anchors.append((x, y))
                elif x == 0 or x == self.grid.width - 1 or y == 0 or y == self.grid.height - 1:
                    anchors.append((x, y))
        return anchors

    def generate_isochrone_containment_line(
        self,
        t_fire: np.ndarray,
        target_lead_time: float,
        anchor_a: Tuple[int, int],
        anchor_b: Tuple[int, int],
        tolerance: float = 60.0,
    ) -> List[Tuple[int, int]]:
        """
        Extracts a spatial corridor along the fire arrival isochrone (contour)
        T_fire(x, y) approx target_lead_time, anchored between anchor_a and anchor_b.
        """
        # Find cells where |t_fire - target_lead_time| <= tolerance
        mask = np.abs(t_fire - target_lead_time) <= tolerance
        candidate_cells = list(zip(*np.where(mask)))  # list of (y, x)

        if not candidate_cells:
            # Fallback: simple line between anchors
            return self._interpolate_line(anchor_a, anchor_b)

        # Convert to (x, y)
        candidates_xy = [(x, y) for (y, x) in candidate_cells]

        # Order cells from anchor_a to anchor_b via greedy nearest neighbor
        ordered_path: List[Tuple[int, int]] = [anchor_a]
        unvisited = set(candidates_xy)
        if anchor_a in unvisited:
            unvisited.remove(anchor_a)

        curr = anchor_a
        while unvisited:
            # Find nearest neighbor in unvisited that progresses toward anchor_b
            best_next = None
            best_cost = float("inf")
            for cand in unvisited:
                d_curr = math.hypot(cand[0] - curr[0], cand[1] - curr[1])
                d_goal = math.hypot(anchor_b[0] - cand[0], anchor_b[1] - cand[1])
                cost = d_curr + 0.5 * d_goal
                if cost < best_cost:
                    best_cost = cost
                    best_next = cand

            if best_next is None or best_cost > 30.0:  # Gap too large
                break

            ordered_path.append(best_next)
            unvisited.remove(best_next)
            curr = best_next

            if math.hypot(curr[0] - anchor_b[0], curr[1] - anchor_b[1]) <= 1.5:
                break

        ordered_path.append(anchor_b)
        return ordered_path

    def _interpolate_line(self, p1: Tuple[int, int], p2: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Bresenham line interpolation between two points."""
        x0, y0 = p1
        x1, y1 = p2
        points = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            points.append((x0, y0))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
        return points

    def plan_multi_agent_containment(
        self,
        agents: List[SuppressionAgent],
        target_cells: List[Tuple[int, int]],
        t_fire: np.ndarray,
        start_time: float = 0.0,
    ) -> ContainmentPlan:
        """
        Coordinates multiple suppression agents to construct the target firebreak.
        Partitions target corridor and executes Sequential Space-Time A* with reservation table.
        """
        self.planner.res_table.clear()
        agent_plans: Dict[str, List[PlanStep]] = {}
        all_feasible = True

        if len(agents) == 1:
            # Single agent handles entire corridor
            plan = self.planner.plan_firebreak_trajectory(
                agent=agents[0],
                start_x=agents[0].x,
                start_y=agents[0].y,
                start_t=start_time,
                cut_cells=target_cells,
                t_fire=t_fire,
                reserve_in_table=True,
            )
            if plan is not None:
                agent_plans[agents[0].agent_id] = plan
                agents[0].assign_plan(plan)
            else:
                all_feasible = False
                agent_plans[agents[0].agent_id] = []
        else:
            # Multi-agent allocation:
            # Divide target cells by proximity and speed
            n = len(agents)
            chunk_size = math.ceil(len(target_cells) / n)
            
            # Prioritize agents based on distance to chunks
            for i, agent in enumerate(agents):
                # Agent 0 gets first half (e.g. from anchor A inwards)
                # Agent 1 gets second half (e.g. from anchor B inwards, reversed)
                if i % 2 == 1:
                    assigned_chunk = list(reversed(target_cells[i * chunk_size : (i + 1) * chunk_size]))
                else:
                    assigned_chunk = target_cells[i * chunk_size : (i + 1) * chunk_size]

                if not assigned_chunk:
                    continue

                plan = self.planner.plan_firebreak_trajectory(
                    agent=agent,
                    start_x=agent.x,
                    start_y=agent.y,
                    start_t=start_time,
                    cut_cells=assigned_chunk,
                    t_fire=t_fire,
                    reserve_in_table=True,
                )

                if plan is not None:
                    agent_plans[agent.agent_id] = plan
                    agent.assign_plan(plan)
                else:
                    all_feasible = False
                    agent_plans[agent.agent_id] = []

        max_horizon = 0.0
        for p in agent_plans.values():
            if p:
                max_horizon = max(max_horizon, p[-1].end_time)

        return ContainmentPlan(
            agent_plans=agent_plans,
            containment_cells=target_cells,
            anchor_points=[target_cells[0], target_cells[-1]] if target_cells else [],
            planned_horizon=max_horizon,
            is_feasible=all_feasible,
            metadata={"num_agents": len(agents), "total_cells": len(target_cells)},
        )
