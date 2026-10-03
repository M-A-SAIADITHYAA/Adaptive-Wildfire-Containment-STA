"""
Standard benchmark scenarios for wildfire containment evaluation.
"""

from .benchmark_scenarios import (
    ScenarioConfig,
    create_valley_flanking_scenario,
    create_wind_shift_scenario,
    create_asset_defense_scenario,
    create_multi_agent_pinch_scenario,
    get_all_scenarios,
)

__all__ = [
    "ScenarioConfig",
    "create_valley_flanking_scenario",
    "create_wind_shift_scenario",
    "create_asset_defense_scenario",
    "create_multi_agent_pinch_scenario",
    "get_all_scenarios",
]
