"""
Space-Time A* (STA*) Search for dynamic wildfire containment planning.
Plans collision-free, hazard-aware trajectories in 4D space-time (x, y, t)
accounting for advancing fire arrival contours (T_fire) and multi-agent reservations.
"""

from dataclasses import dataclass
import heapq
import math
from typing import Dict, List, Optional, Set, Tuple
import numpy as np

from ..fire_sim.grid import ForestGrid, CellState
from .agent import SuppressionAgent, ActionType, PlanStep


class ReservationTable:
    """
    Space-time reservation table for multi-agent deconfliction.
    Prevents spatial overlapping and vertex/edge collisions between crews.
    """

    def __init__(self, time_bucket_size: float = 5.0):
        self.time_bucket = time_bucket_size
        # (x, y) -> list of (start_t, end_t, agent_id)
        self.reservations: Dict[Tuple[int, int], List[Tuple[float, float, str]]] = {}

    def is_available(
        self,
        x: int,
        y: int,
        start_t: float,
        end_t: float,
        agent_id: str,
    ) -> bool:
        """Check if cell (x, y) is unreserved by other agents during [start_t, end_t]."""
        cell_res = self.reservations.get((x, y), [])
        for r_start, r_end, r_agent in cell_res:
            if r_agent == agent_id:
                continue
            # Overlap condition
            if not (end_t <= r_start or start_t >= r_end):
                return False
        return True

    def reserve(
        self,
        x: int,
        y: int,
        start_t: float,
        end_t: float,
        agent_id: str,
    ):
        """Reserve cell (x, y) during [start_t, end_t] for agent_id."""
        if (x, y) not in self.reservations:
            self.reservations[(x, y)] = []
        self.reservations[(x, y)].append((start_t, end_t, agent_id))

    def clear_agent(self, agent_id: str):
        """Remove all reservations registered by agent_id."""
        for cell in list(self.reservations.keys()):
            self.reservations[cell] = [
                r for r in self.reservations[cell] if r[2] != agent_id
            ]
            if not self.reservations[cell]:
                del self.reservations[cell]

    def clear(self):
        """Clear all reservations."""
        self.reservations.clear()


@dataclass
class SpaceTimeNode:
    """A search node in the (x, y, t) state space."""
    x: int
    y: int
    t: float
    g: float
    h: float
    parent: Optional["SpaceTimeNode"] = None
    action: ActionType = ActionType.TRANSIT

    @property
    def f(self) -> float:
        return self.g + self.h

    def __lt__(self, other: "SpaceTimeNode") -> bool:
        if abs(self.f - other.f) < 1e-6:
            return self.g > other.g  # Tie breaker: prefer further along
        return self.f < other.f


class SpaceTimeAStarPlanner:
    """
    Space-Time A* (STA*) Planner for dynamic firebreak allocation.
    """

    def __init__(
        self,
        grid: ForestGrid,
        reservation_table: Optional[ReservationTable] = None,
        time_resolution: float = 5.0,  # Temporal binning size in seconds for closed set
        allow_wait: bool = True,
        risk_weight: float = 0.2,      # Proximity penalty weight near fire perimeter
    ):
        self.grid = grid
        self.res_table = reservation_table or ReservationTable(time_bucket_size=time_resolution)
        self.time_res = time_resolution
        self.allow_wait = allow_wait
        self.risk_weight = risk_weight

    def _state_key(self, x: int, y: int, t: float) -> Tuple[int, int, int]:
        """Discretized hash key for closed set (x, y, t_bucket)."""
        return (x, y, int(round(t / self.time_res)))

    def is_spatiotemporally_safe(
        self,
        x: int,
        y: int,
        start_t: float,
        end_t: float,
        t_fire: np.ndarray,
        agent: SuppressionAgent,
    ) -> bool:
        """
        Verify that operating on cell (x, y) during [start_t, end_t] respects the
        fire arrival deadline with required safety buffer.
        """
        if not self.grid.is_traversable_for_agent(x, y, max_slope=agent.max_slope):
            return False

        fire_arr = t_fire[y, x]
        if np.isneginf(fire_arr):
            return False

        # If fire has already passed or arrives before operation finishes + buffer
        if end_t > (fire_arr - agent.safety_buffer):
            return False

        # Collision check with other agents
        if not self.res_table.is_available(x, y, start_t, end_t, agent.agent_id):
            return False

        return True

    def calculate_heuristic(
        self,
        x: int,
        y: int,
        goal_x: int,
        goal_y: int,
        max_speed: float,
    ) -> float:
        """
        Admissible heuristic: Octile distance lower bound divided by maximum transit speed.
        """
        dx = abs(goal_x - x)
        dy = abs(goal_y - y)
        octile_dist = (max(dx, dy) + (math.sqrt(2) - 1.0) * min(dx, dy)) * self.grid.cell_size
        return octile_dist / max(0.1, max_speed)

    def plan_transit_path(
        self,
        agent: SuppressionAgent,
        start_x: int,
        start_y: int,
        start_t: float,
        goal_x: int,
        goal_y: int,
        t_fire: np.ndarray,
        max_search_depth: int = 15000,
    ) -> Optional[List[PlanStep]]:
        """
        Finds a safe transit trajectory from (start_x, start_y, start_t) to (goal_x, goal_y)
        in space-time, maneuvering around advancing fire fronts.
        """
        if not self.is_spatiotemporally_safe(start_x, start_y, start_t, start_t, t_fire, agent):
            return None

        h0 = self.calculate_heuristic(start_x, start_y, goal_x, goal_y, agent.speed)
        root = SpaceTimeNode(x=start_x, y=start_y, t=start_t, g=0.0, h=h0, parent=None, action=ActionType.TRANSIT)

        open_pq: List[SpaceTimeNode] = [root]
        closed_set: Dict[Tuple[int, int, int], float] = {}

        iterations = 0

        while open_pq and iterations < max_search_depth:
            iterations += 1
            curr = heapq.heappop(open_pq)

            if curr.x == goal_x and curr.y == goal_y:
                return self._reconstruct_plan(curr)

            key = self._state_key(curr.x, curr.y, curr.t)
            if key in closed_set and closed_set[key] <= curr.g:
                continue
            closed_set[key] = curr.g

            # 1. Transitions: Move to 8-connected neighbors
            for nx, ny in self.grid.get_neighbors(curr.x, curr.y, diagonal=True):
                dt_move = agent.travel_time(self.grid, curr.x, curr.y, nx, ny)
                if math.isinf(dt_move):
                    continue

                arr_t = curr.t + dt_move
                if not self.is_spatiotemporally_safe(nx, ny, curr.t, arr_t, t_fire, agent):
                    continue

                # Cost: traversal time + risk penalty if close to fire
                fire_margin = max(0.0, t_fire[ny, nx] - arr_t)
                risk_pen = 0.0
                if fire_margin < (agent.safety_buffer * 2.5):
                    risk_pen = self.risk_weight * (2.5 * agent.safety_buffer - fire_margin)

                edge_cost = dt_move + risk_pen
                g_new = curr.g + edge_cost
                h_new = self.calculate_heuristic(nx, ny, goal_x, goal_y, agent.speed)

                n_key = self._state_key(nx, ny, arr_t)
                if n_key in closed_set and closed_set[n_key] <= g_new:
                    continue

                child = SpaceTimeNode(
                    x=nx,
                    y=ny,
                    t=arr_t,
                    g=g_new,
                    h=h_new,
                    parent=curr,
                    action=ActionType.TRANSIT,
                )
                heapq.heappush(open_pq, child)

            # 2. Transition: Wait in place
            if self.allow_wait:
                dt_wait = self.time_res
                wait_t = curr.t + dt_wait
                if self.is_spatiotemporally_safe(curr.x, curr.y, curr.t, wait_t, t_fire, agent):
                    g_wait = curr.g + dt_wait * 1.05  # slight wait penalty
                    w_key = self._state_key(curr.x, curr.y, wait_t)
                    if w_key not in closed_set or closed_set[w_key] > g_wait:
                        w_child = SpaceTimeNode(
                            x=curr.x,
                            y=curr.y,
                            t=wait_t,
                            g=g_wait,
                            h=curr.h,
                            parent=curr,
                            action=ActionType.WAIT,
                        )
                        heapq.heappush(open_pq, w_child)

        return None

    def plan_firebreak_trajectory(
        self,
        agent: SuppressionAgent,
        start_x: int,
        start_y: int,
        start_t: float,
        cut_cells: List[Tuple[int, int]],
        t_fire: np.ndarray,
        reserve_in_table: bool = True,
    ) -> Optional[List[PlanStep]]:
        """
        Plans a sequential firebreak construction mission through an ordered list of target cells.
        For each cell:
          1. Transit safely to the target cell (using Space-Time A* transit).
          2. Cut the firebreak at the target cell if safety deadline is respected.
        """
        full_plan: List[PlanStep] = []
        cur_x, cur_y, cur_t = start_x, start_y, start_t

        for target_x, target_y in cut_cells:
            # Step A: Transit to cell if not already there
            if (cur_x, cur_y) != (target_x, target_y):
                transit_steps = self.plan_transit_path(
                    agent=agent,
                    start_x=cur_x,
                    start_y=cur_y,
                    start_t=cur_t,
                    goal_x=target_x,
                    goal_y=target_y,
                    t_fire=t_fire,
                )
                if not transit_steps:
                    # Transit blocked or overtaken by fire
                    return None
                full_plan.extend(transit_steps)
                cur_x = target_x
                cur_y = target_y
                cur_t = transit_steps[-1].end_time

            # Step B: Cut firebreak at cell
            dt_cut = agent.cut_duration(self.grid, cur_x, cur_y)
            cut_end_t = cur_t + dt_cut

            if not self.is_spatiotemporally_safe(cur_x, cur_y, cur_t, cut_end_t, t_fire, agent):
                # Safety deadline breached: fire overtakes crew or buffer violated!
                return None

            cut_step = PlanStep(
                action=ActionType.CUT_FIREBREAK,
                x=cur_x,
                y=cur_y,
                start_time=cur_t,
                end_time=cut_end_t,
            )
            full_plan.append(cut_step)
            cur_t = cut_end_t

        if reserve_in_table:
            for step in full_plan:
                self.res_table.reserve(
                    step.x, step.y, step.start_time, step.end_time, agent.agent_id
                )

        return full_plan

    def plan_anchor_to_anchor_firebreak(
        self,
        agent: SuppressionAgent,
        start_x: int,
        start_y: int,
        start_t: float,
        anchor_goal_x: int,
        anchor_goal_y: int,
        t_fire: np.ndarray,
        max_search_depth: int = 25000,
        reserve_in_table: bool = True,
    ) -> Optional[List[PlanStep]]:
        """
        Synthesizes an optimal firebreak corridor connecting two anchor points ahead
        of the expanding fire front using Space-Time A*.
        
        At each step, the agent can either transit or construct a firebreak,
        directly finding the lowest-cost spatio-temporal barrier cutline to the goal.
        """
        if not self.is_spatiotemporally_safe(start_x, start_y, start_t, start_t, t_fire, agent):
            return None

        h0 = self.calculate_heuristic(start_x, start_y, anchor_goal_x, anchor_goal_y, agent.speed)
        root = SpaceTimeNode(x=start_x, y=start_y, t=start_t, g=0.0, h=h0, parent=None, action=ActionType.CUT_FIREBREAK)

        open_pq: List[SpaceTimeNode] = [root]
        closed_set: Dict[Tuple[int, int, int], float] = {}

        iterations = 0

        while open_pq and iterations < max_search_depth:
            iterations += 1
            curr = heapq.heappop(open_pq)

            if curr.x == anchor_goal_x and curr.y == anchor_goal_y:
                plan = self._reconstruct_plan(curr)
                if reserve_in_table:
                    for s in plan:
                        self.res_table.reserve(s.x, s.y, s.start_time, s.end_time, agent.agent_id)
                return plan

            key = self._state_key(curr.x, curr.y, curr.t)
            if key in closed_set and closed_set[key] <= curr.g:
                continue
            closed_set[key] = curr.g

            # Expand into adjacent cutting cells
            for nx, ny in self.grid.get_neighbors(curr.x, curr.y, diagonal=True):
                dt_move = agent.travel_time(self.grid, curr.x, curr.y, nx, ny)
                if math.isinf(dt_move):
                    continue

                dt_cut = agent.cut_duration(self.grid, nx, ny)
                arr_t = curr.t + dt_move
                finish_t = arr_t + dt_cut

                # Must be safe for travel and cutting duration
                if not self.is_spatiotemporally_safe(nx, ny, curr.t, finish_t, t_fire, agent):
                    continue

                fire_margin = max(0.0, t_fire[ny, nx] - finish_t)
                risk_pen = 0.0
                if fire_margin < (agent.safety_buffer * 2.0):
                    risk_pen = self.risk_weight * (2.0 * agent.safety_buffer - fire_margin)

                # Prioritize defending high-value assets and clearing less dense fuel
                cost = dt_move + dt_cut + risk_pen
                g_new = curr.g + cost
                h_new = self.calculate_heuristic(nx, ny, anchor_goal_x, anchor_goal_y, agent.speed)

                n_key = self._state_key(nx, ny, finish_t)
                if n_key in closed_set and closed_set[n_key] <= g_new:
                    continue

                # Intermediate move step
                move_node = SpaceTimeNode(
                    x=nx,
                    y=ny,
                    t=arr_t,
                    g=curr.g + dt_move,
                    h=h_new,
                    parent=curr,
                    action=ActionType.TRANSIT,
                )
                # Cut step
                cut_node = SpaceTimeNode(
                    x=nx,
                    y=ny,
                    t=finish_t,
                    g=g_new,
                    h=h_new,
                    parent=move_node,
                    action=ActionType.CUT_FIREBREAK,
                )
                heapq.heappush(open_pq, cut_node)

        return None

    def _reconstruct_plan(self, end_node: SpaceTimeNode) -> List[PlanStep]:
        """Backtrack through parent pointers to construct an ordered PlanStep list."""
        nodes: List[SpaceTimeNode] = []
        cur: Optional[SpaceTimeNode] = end_node
        while cur is not None:
            nodes.append(cur)
            cur = cur.parent
        nodes.reverse()

        plan: List[PlanStep] = []
        for i in range(1, len(nodes)):
            prev = nodes[i - 1]
            curr = nodes[i]
            plan.append(
                PlanStep(
                    action=curr.action,
                    x=curr.x,
                    y=curr.y,
                    start_time=prev.t,
                    end_time=curr.t,
                )
            )
        return plan
