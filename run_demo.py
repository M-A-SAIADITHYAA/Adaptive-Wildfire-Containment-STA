#!/usr/bin/env python3
"""
CLI Demonstration Driver for Dynamic Forest Firebreak Allocation with Space-Time A*.
Runs benchmark scenarios, performs baseline comparisons, and exports visual telemetry.
"""

import argparse
import os
import sys
import time
import numpy as np

from forest_fire_sta.scenarios.benchmark_scenarios import (
    get_all_scenarios,
    ScenarioConfig,
)
from forest_fire_sta.containment.perimeter_planner import PerimeterPlanner
from forest_fire_sta.containment.dynamic_replanner import DynamicReplanner
from forest_fire_sta.metrics.evaluator import ContainmentEvaluator
from forest_fire_sta.visualization.visualizer import ForestFireVisualizer
from forest_fire_sta.visualization.interactive_gui import generate_standalone_html, start_server


def print_banner():
    banner = r"""
 =========================================================================================
   DYNAMIC FOREST FIREBREAK ALLOCATION & CONTAINMENT PLANNING (SPACE-TIME A* SEARCH)
 =========================================================================================
"""
    print(banner)


def run_scenario(
    scenario_cfg: ScenarioConfig,
    save_plots: bool = False,
    output_dir: str = "output",
) -> dict:
    """Execute a single scenario under Space-Time A* and evaluate results."""
    print(f"\n[*] Running Scenario: {scenario_cfg.name}")
    print(f"    Description: {scenario_cfg.description}")
    print(f"    Grid Dimensions: {scenario_cfg.grid.width}x{scenario_cfg.grid.height} ({scenario_cfg.grid.cell_size}m cell size)")
    print(f"    Assigned Agents: {[a.name for a in scenario_cfg.agents]}")

    start_clock = time.time()

    # 1. Project initial Fire Arrival Times (T_fire)
    t_fire_initial = scenario_cfg.spread_model.compute_fire_arrival_times(start_time=0.0)

    # 2. Plan initial firebreak corridor using Space-Time A*
    planner = PerimeterPlanner(grid=scenario_cfg.grid, spread_model=scenario_cfg.spread_model)
    plan = planner.plan_multi_agent_containment(
        agents=scenario_cfg.agents,
        target_cells=scenario_cfg.target_corridor_cells,
        t_fire=t_fire_initial,
        start_time=0.0,
    )

    print(f"    Initial STA* Plan Feasible: {plan.is_feasible} (Horizon: {plan.planned_horizon:.1f}s)")

    # 3. Closed-loop Dynamic Simulation & Re-planning
    replanner = DynamicReplanner(
        grid=scenario_cfg.grid,
        spread_model=scenario_cfg.spread_model,
        agents=scenario_cfg.agents,
        perimeter_planner=planner,
        check_interval=10.0,
    )

    sim_res = replanner.execute_simulation(
        total_duration=scenario_cfg.expected_duration,
        dt=1.5,
        replan_corridor_provider=scenario_cfg.replan_corridor_provider,
    )

    # 4. Evaluate metrics
    metrics = ContainmentEvaluator.evaluate(
        grid=scenario_cfg.grid,
        agents=scenario_cfg.agents,
        initial_t_fire=t_fire_initial,
        duration=sim_res["duration"],
        replanning_count=len(sim_res["replanning_events"]),
    )

    elapsed_wall = time.time() - start_clock

    # 5. Output Plots
    if save_plots:
        os.makedirs(output_dir, exist_ok=True)
        safe_name = scenario_cfg.name.lower().replace(" ", "_").replace("&", "and")
        fig_path = os.path.join(output_dir, f"{safe_name}.png")
        vis = ForestFireVisualizer(scenario_cfg.grid)
        wind_curr = scenario_cfg.weather.get_wind(sim_res["duration"])
        vis.render_map(
            t_fire=t_fire_initial,
            agents=scenario_cfg.agents,
            wind=wind_curr,
            target_cells=scenario_cfg.target_corridor_cells,
            title=f"{scenario_cfg.name} - Status: {metrics.status}",
            save_path=fig_path,
        )
        print(f"    [+] Saved map plot to: {fig_path}")

    return {
        "scenario": scenario_cfg.name,
        "metrics": metrics,
        "replanning_events": sim_res["replanning_events"],
        "compute_time": elapsed_wall,
    }


def compare_with_unsuppressed_baseline(scenario_factory) -> None:
    """Compare STA* containment against an unsuppressed fire baseline."""
    # 1. Baseline: Unsuppressed fire
    cfg_base = scenario_factory()
    print(f"\n--- Comparative Baseline Analysis: {cfg_base.name} ---")
    replanner_base = DynamicReplanner(
        grid=cfg_base.grid,
        spread_model=cfg_base.spread_model,
        agents=[],  # No suppression resources
    )
    sim_base = replanner_base.execute_simulation(total_duration=cfg_base.expected_duration, dt=1.5)
    t_fire_base = cfg_base.spread_model.compute_fire_arrival_times(0.0)
    m_base = ContainmentEvaluator.evaluate(cfg_base.grid, [], t_fire_base, sim_base["duration"])

    # 2. Managed: With Space-Time A*
    cfg_sta = scenario_factory()
    res_sta = run_scenario(cfg_sta, save_plots=False)
    m_sta = res_sta["metrics"]

    # Display comparison table
    print("\n" + "=" * 78)
    print(f"{'Metric':<32} | {'Unsuppressed Baseline':<20} | {'Space-Time A*':<18}")
    print("-" * 78)
    print(f"{'Containment Status':<32} | {m_base.status:<20} | {m_sta.status:<18}")
    print(f"{'Burned Area (Hectares)':<32} | {m_base.burned_area_ha:<20.2f} | {m_sta.burned_area_ha:<18.2f}")
    print(f"{'Burned Cells':<32} | {m_base.burned_cells:<20} | {m_sta.burned_cells:<18}")
    print(f"{'Firebreak Cells Built':<32} | {m_base.firebreaks_constructed:<20} | {m_sta.firebreaks_constructed:<18}")
    print(f"{'Asset Protection (%)':<32} | {m_base.asset_protection_pct:<20.1f} | {m_sta.asset_protection_pct:<18.1f}")
    print(f"{'Min Crew Safety Margin (s)':<32} | {'N/A':<20} | {m_sta.min_safety_margin_s:<18.1f}")
    print(f"{'Replanning Triggers':<32} | {0:<20} | {m_sta.replanning_count:<18}")
    print("=" * 78)

    reduction = ((m_base.burned_area_ha - m_sta.burned_area_ha) / max(0.01, m_base.burned_area_ha)) * 100.0
    print(f"[>] Result: Space-Time A* reduced burned area by {reduction:.1f}% while ensuring crew safety margin.")


def print_summary_table(results: list):
    """Print consolidated metrics table across all benchmark runs."""
    print("\n" + "=" * 94)
    print(f"{'Scenario':<34} | {'Status':<10} | {'Burned (ha)':<11} | {'Firebreaks':<10} | {'Assets (%)':<10} | {'Margin (s)':<10}")
    print("-" * 94)
    for r in results:
        m = r["metrics"]
        print(f"{r['scenario']:<34} | {m.status:<10} | {m.burned_area_ha:<11.1f} | {m.firebreaks_constructed:<10} | {m.asset_protection_pct:<10.1f} | {m.min_safety_margin_s:<10.1f}")
    print("=" * 94)


def main():
    parser = argparse.ArgumentParser(
        description="Dynamic Forest Firebreak Allocation with Space-Time A* Search"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="all",
        choices=["valley", "wind_shift", "asset_defense", "multi_agent", "all"],
        help="Benchmark scenario to run",
    )
    parser.add_argument(
        "--save-plots",
        action="store_true",
        help="Export high-resolution PNG plots to output directory",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Output directory for generated plots and reports",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Run comparative analysis against unsuppressed fire baseline",
    )
    parser.add_argument(
        "--export-html",
        action="store_true",
        help="Export standalone interactive HTML5 visualizer",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Launch interactive web simulation dashboard on local HTTP server",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for local HTTP server",
    )

    args = parser.parse_args()
    print_banner()

    if args.export_html:
        generate_standalone_html(os.path.join(args.output_dir, "firebreak_simulator.html") if args.output_dir else "firebreak_simulator.html")
        return

    if args.serve:
        start_server(args.port)
        return

    all_scenarios = get_all_scenarios()

    if args.compare_baseline:
        scen_key = "valley" if args.scenario == "all" else args.scenario
        compare_with_unsuppressed_baseline(all_scenarios[scen_key])
        return

    selected_keys = list(all_scenarios.keys()) if args.scenario == "all" else [args.scenario]
    results = []

    for key in selected_keys:
        cfg = all_scenarios[key]()
        res = run_scenario(cfg, save_plots=args.save_plots, output_dir=args.output_dir)
        results.append(res)

    print_summary_table(results)

    # Always generate the HTML simulator file for immediate user exploration
    os.makedirs(args.output_dir, exist_ok=True)
    html_out = os.path.join(args.output_dir, "firebreak_simulator.html")
    generate_standalone_html(html_out)
    print(f"\n[+] Interactive simulation dashboard generated at: {html_out}")
    print("    Open this file in any web browser to interactively control wind, scenarios, and crews!")


if __name__ == "__main__":
    main()
