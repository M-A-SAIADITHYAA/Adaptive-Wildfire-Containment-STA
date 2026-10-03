"""
Benchmark scenarios for testing Space-Time A* firebreak allocation and dynamic re-planning.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
import numpy as np

from ..fire_sim.grid import ForestGrid, CellState
from ..fire_sim.weather import WeatherProfile, WindVector
from ..fire_sim.spread_model import FireSpreadModel
from ..containment.agent import SuppressionAgent, Bulldozer, HandCrew


@dataclass
class ScenarioConfig:
    name: str
    description: str
    grid: ForestGrid
    weather: WeatherProfile
    spread_model: FireSpreadModel
    agents: List[SuppressionAgent]
    ignition_points: List[Tuple[int, int]]
    target_corridor_cells: List[Tuple[int, int]]
    replan_corridor_provider: Optional[Callable] = None
    expected_duration: float = 300.0


def create_valley_flanking_scenario(width: int = 35, height: int = 35) -> ScenarioConfig:
    """
    Scenario 1: Valley Flanking Containment
    Fire advances through a valley with steady NE wind.
    A single bulldozer constructs an indirect containment line anchored to a western river.
    """
    grid = ForestGrid(width=width, height=height, cell_size=20.0, default_fuel=0.85)

    # Moderate valley elevation: gentle slope <= 0.15 (well within bulldozer capability)
    for y in range(height):
        for x in range(width):
            dist_from_center = abs(x - width // 2)
            grid.elevation[y, x] = 3.0 * dist_from_center

    # Natural barrier: River flowing on the west side
    river_x = 5
    for y in range(height):
        grid.set_barrier(river_x, y)

    # Steady North-East wind (45 deg)
    weather = WeatherProfile(base_speed=5.5, base_direction_deg=45.0)
    spread_model = FireSpreadModel(grid=grid, weather=weather, base_ros=0.45)

    # Ignition near south center
    ignitions = [(15, 8), (16, 8)]
    for ix, iy in ignitions:
        grid.ignite(ix, iy)

    # Bulldozer starts near the river road at y=28
    dozer = Bulldozer(agent_id="dozer_1", start_x=6, start_y=28, speed=1.8, cut_time_per_cell=10.0)

    # Target containment line: across the valley from river (x=6) to eastern slope at y=28
    corridor = [(x, 28) for x in range(6, 26)]

    return ScenarioConfig(
        name="Valley Flanking Containment",
        description="Single bulldozer constructing an indirect firebreak ahead of an advancing valley fire.",
        grid=grid,
        weather=weather,
        spread_model=spread_model,
        agents=[dozer],
        ignition_points=ignitions,
        target_corridor_cells=corridor,
        expected_duration=250.0,
    )


def create_wind_shift_scenario(width: int = 40, height: int = 40) -> ScenarioConfig:
    """
    Scenario 2: Sudden Wind Shift (Dynamic Re-planning Stress Test)
    Wind initially pushes fire East. At t=35s, wind shifts violently North!
    Old planned line is compromised; dynamic STA* triggers emergency replanning.
    """
    grid = ForestGrid(width=width, height=height, cell_size=20.0, default_fuel=0.8)

    # Wind schedule: 0-35s -> blowing East (90 deg), >=35s -> blowing North (0 deg)
    weather = WeatherProfile(
        base_speed=6.0,
        base_direction_deg=90.0,
        schedule=[(35.0, 7.5, 0.0)],
    )
    spread_model = FireSpreadModel(grid=grid, weather=weather, base_ros=0.5)

    # Ignition in southwest
    ignitions = [(10, 10), (11, 10)]
    for ix, iy in ignitions:
        grid.ignite(ix, iy)

    # Bulldozer deployed
    dozer = Bulldozer(agent_id="dozer_fast", start_x=26, start_y=5, speed=1.8, cut_time_per_cell=10.0)

    # Initial target line: East blocking line at x=26, y from 6 to 20
    initial_corridor = [(26, y) for y in range(6, 21)]

    # Dynamic replan provider: When wind shifts north, secondary line must be built at y=28 (blocking northern escape)
    def replan_provider(t: float, t_fire: np.ndarray, agents: List[SuppressionAgent]):
        return [(x, 28) for x in range(8, 28)]

    return ScenarioConfig(
        name="Sudden Wind Shift & Dynamic Replanning",
        description="Wind abruptly rotates 90° from East to North, compromising the primary line and triggering STA* replanning.",
        grid=grid,
        weather=weather,
        spread_model=spread_model,
        agents=[dozer],
        ignition_points=ignitions,
        target_corridor_cells=initial_corridor,
        replan_corridor_provider=replan_provider,
        expected_duration=280.0,
    )


def create_asset_defense_scenario(width: int = 40, height: int = 40) -> ScenarioConfig:
    """
    Scenario 3: Community & Asset Defense
    A vulnerable settlement is situated at the top right.
    Bulldozer and hand crew build a defensive buffer line around the settlement.
    """
    grid = ForestGrid(width=width, height=height, cell_size=20.0, default_fuel=0.75)

    # High-value asset settlement in northeast (x: 28-36, y: 28-36)
    for y in range(28, 37):
        for x in range(28, 37):
            grid.asset_values[y, x] = 200.0  # Settlement value

    # Wind blowing directly towards settlement (45 deg NE)
    weather = WeatherProfile(base_speed=5.0, base_direction_deg=45.0)
    spread_model = FireSpreadModel(grid=grid, weather=weather, base_ros=0.45)

    # Ignition in southwest
    ignitions = [(12, 12)]
    for ix, iy in ignitions:
        grid.ignite(ix, iy)

    # Heavy Bulldozer + Hand Crew stationed at defensive sectors
    dozer = Bulldozer(agent_id="dozer_asset", start_x=25, start_y=25, speed=1.6, cut_time_per_cell=12.0)
    crew = HandCrew(agent_id="hand_crew", start_x=38, start_y=25, speed=1.4, cut_time_per_cell=16.0, safety_buffer=60.0)

    # Defensive L-shaped perimeter around settlement
    defensive_line = [(25, y) for y in range(25, 38)] + [(x, 25) for x in range(26, 38)]

    return ScenarioConfig(
        name="Community & Asset Defense",
        description="Multi-crew defensive barrier construction to insulate a high-value community from an advancing fire.",
        grid=grid,
        weather=weather,
        spread_model=spread_model,
        agents=[dozer, crew],
        ignition_points=ignitions,
        target_corridor_cells=defensive_line,
        expected_duration=300.0,
    )


def create_multi_agent_pinch_scenario(width: int = 45, height: int = 45) -> ScenarioConfig:
    """
    Scenario 4: Multi-Agent Coordinated Pinch
    Two bulldozers advance from opposite flanks towards each other.
    Reservation table ensures collision-free coordination at the center join point.
    """
    grid = ForestGrid(width=width, height=height, cell_size=20.0, default_fuel=0.85)

    # Wind blowing North (0 deg)
    weather = WeatherProfile(base_speed=5.5, base_direction_deg=0.0)
    spread_model = FireSpreadModel(grid=grid, weather=weather, base_ros=0.48)

    # Ignition in south center
    ignitions = [(22, 10), (23, 10)]
    for ix, iy in ignitions:
        grid.ignite(ix, iy)

    # Bulldozer West and Bulldozer East converging along transverse line at y=31
    dozer_w = Bulldozer(agent_id="dozer_west", name="Bulldozer West", start_x=8, start_y=31, speed=1.8, cut_time_per_cell=10.0)
    dozer_e = Bulldozer(agent_id="dozer_east", name="Bulldozer East", start_x=37, start_y=31, speed=1.8, cut_time_per_cell=10.0)

    # Transverse cut line at y=31 from x=8 to x=37
    transverse_line = [(x, 31) for x in range(8, 38)]

    return ScenarioConfig(
        name="Multi-Agent Coordinated Pinch",
        description="Two bulldozers converging from opposite flanks, deconflicted via space-time reservation table.",
        grid=grid,
        weather=weather,
        spread_model=spread_model,
        agents=[dozer_w, dozer_e],
        ignition_points=ignitions,
        target_corridor_cells=transverse_line,
        expected_duration=260.0,
    )


def get_all_scenarios() -> Dict[str, Callable[[], ScenarioConfig]]:
    """Return dictionary of available benchmark scenario factory functions."""
    return {
        "valley": create_valley_flanking_scenario,
        "wind_shift": create_wind_shift_scenario,
        "asset_defense": create_asset_defense_scenario,
        "multi_agent": create_multi_agent_pinch_scenario,
    }
