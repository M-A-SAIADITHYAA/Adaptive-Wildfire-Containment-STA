"""
Metrics evaluator for dynamic forest fire containment and crew safety.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np

from ..fire_sim.grid import ForestGrid, CellState
from ..containment.agent import SuppressionAgent, ActionType


@dataclass
class ContainmentMetrics:
    """Quantitative performance report for a wildfire containment mission."""
    status: str                        # "CONTAINED", "BREACHED", or "IN_PROGRESS"
    duration: float                    # Total simulation time in seconds
    burned_cells: int                  # Number of burned cells
    burned_area_ha: float              # Burned area in hectares
    active_burning_cells: int          # Remaining active burning cells
    firebreaks_constructed: int        # Number of completed firebreak cells
    total_asset_value: float           # Total economic/ecological asset value on map
    assets_lost_value: float           # Value of assets burned
    asset_protection_pct: float        # Percentage of total assets preserved
    min_safety_margin_s: float         # Minimum recorded safety buffer (seconds)
    mean_safety_margin_s: float        # Mean recorded safety buffer (seconds)
    replanning_count: int              # Number of online replanning events triggered
    crew_fatalities_or_overruns: int   # Number of crew hazardous overruns (margin <= 0)


class ContainmentEvaluator:
    """
    Evaluates fire containment operations, asset preservation, and crew safety margins.
    """

    @staticmethod
    def evaluate(
        grid: ForestGrid,
        agents: List[SuppressionAgent],
        initial_t_fire: np.ndarray,
        duration: float,
        replanning_count: int = 0,
    ) -> ContainmentMetrics:
        """Compute full performance metrics from current simulation state."""
        burned_cells = int(np.count_nonzero(grid.state == CellState.BURNED))
        active_burning = int(np.count_nonzero(grid.state == CellState.BURNING))
        firebreaks = int(np.count_nonzero(grid.state == CellState.FIREBREAK))

        cell_area_m2 = grid.cell_size ** 2
        burned_area_ha = (burned_cells * cell_area_m2) / 10000.0

        total_assets = float(np.sum(grid.asset_values))
        burned_mask = (grid.state == CellState.BURNED) | (grid.state == CellState.BURNING)
        lost_assets = float(np.sum(grid.asset_values[burned_mask]))

        if total_assets > 0:
            protection_pct = max(0.0, 100.0 * (1.0 - (lost_assets / total_assets)))
        else:
            protection_pct = 100.0

        # Safety margins analysis
        safety_margins: List[float] = []
        overruns = 0

        for agent in agents:
            for step in agent.plan:
                if step.action == ActionType.CUT_FIREBREAK:
                    fire_arr = initial_t_fire[step.y, step.x]
                    if not np.isinf(fire_arr):
                        margin = fire_arr - step.end_time
                        safety_margins.append(margin)
                        if margin <= 0.0:
                            overruns += 1

        min_margin = min(safety_margins) if safety_margins else 999.0
        mean_margin = float(np.mean(safety_margins)) if safety_margins else 999.0

        # Status determination
        if overruns > 0:
            status = "BREACHED"
        elif active_burning == 0 and burned_cells > 0:
            status = "CONTAINED"
        else:
            status = "IN_PROGRESS"

        return ContainmentMetrics(
            status=status,
            duration=duration,
            burned_cells=burned_cells,
            burned_area_ha=burned_area_ha,
            active_burning_cells=active_burning,
            firebreaks_constructed=firebreaks,
            total_asset_value=total_assets,
            assets_lost_value=lost_assets,
            asset_protection_pct=protection_pct,
            min_safety_margin_s=min_margin,
            mean_safety_margin_s=mean_margin,
            replanning_count=replanning_count,
            crew_fatalities_or_overruns=overruns,
        )
