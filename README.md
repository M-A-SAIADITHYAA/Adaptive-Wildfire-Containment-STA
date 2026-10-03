# Dynamic Forest Firebreak Allocation and Containment Planning Using Space-Time A* Search

An algorithmic framework and simulation engine for wildfire containment planning and dynamic firebreak allocation. This system solves the challenge of dispatching and coordinating heterogeneous firefighting resources (e.g. Bulldozers, Hand Crews) in complex topography under time-varying wind forcing by treating advancing wildfire fronts as dynamic, expanding obstacles in 4D space-time $(x, y, t)$.

---

## Key Features

- **Dynamic Wildfire Propagation Model**:
  - Topographical slope calculation from elevation matrices.
  - Directional Rothermel-inspired Rate of Spread (ROS) incorporating fuel load, moisture, and slope.
  - Time-varying wind fields (constant, gusts, rotations, and sudden wind shifts).
  - Continuous Dijkstra / Wavefront computation of the **Fire Arrival Time Field** $T_{\text{fire}}(x, y)$.

- **Space-Time A* Search (STA*)**:
  - Traversal in space-time $(x, y, t)$ accounting for dynamic safety buffers:
    $$t_{\text{finish}} \le T_{\text{fire}}(x, y) - \Delta \tau_{\text{safety}}$$
  - Admissible spatio-temporal octile distance heuristics.
  - Multi-agent coordination with a space-time **Reservation Table** $\mathcal{R}(x, y, t)$ preventing collisions and redundant clearing.

- **Strategic Perimeter & Anchor Planning**:
  - Connects natural barriers (rivers, ridges, roads, or burned ash) to form closed containment envelopes.
  - Multi-crew task allocation across fire flanks.

- **Dynamic Online Re-planning (Rolling Horizon)**:
  - Real-time line integrity monitoring against updated fire arrival projections.
  - Automatic breach detection and emergency fallback perimeter synthesis when weather changes or fire accelerates.

- **Telemetry, Evaluation & Visualization**:
  - Metrics tracking: burned area (ha), firebreak length, asset value saved (%), minimum crew safety margin (s).
  - High-resolution Matplotlib contour and trajectory maps.
  - Standalone interactive HTML5 Canvas visualizer and local HTTP simulation server.

---

## Mathematical Formulation

### 1. Directional Rate of Spread (ROS)
For spread from burning cell $(x_1, y_1)$ to unburned neighbor $(x_2, y_2)$ at time $t$:
$$R_{12}(t) = R_0 \cdot \Phi_f \cdot \max(0.05, 1.0 + \Phi_w(t) + \Phi_s)$$
where:
- $R_0$: Base rate of spread ($m/s$).
- $\Phi_f = \frac{K_f}{1.0 + 3.0 M}$: Fuel factor based on fuel density $K_f \in [0, 1]$ and moisture $M \in [0, 1]$.
- $\Phi_w(t) = c_w U(t)^b \max(0, \cos(\theta_w(t) - \theta_{12}))$: Wind alignment factor with wind speed $U(t)$ and direction $\theta_w(t)$.
- $\Phi_s = c_s (\max(0, \tan \alpha_{12}))^2$: Slope factor where $\alpha_{12}$ is uphill slope gradient.

### 2. Fire Arrival Time Field $T_{\text{fire}}(x, y)$
Computed via Dijkstra wavefront propagation:
$$T_{\text{fire}}(x_2, y_2) = \min_{(x_1, y_1) \in \mathcal{N}} \left( T_{\text{fire}}(x_1, y_1) + \frac{\text{dist}((x_1, y_1), (x_2, y_2))}{R_{12}(T_{\text{fire}}(x_1, y_1))} \right)$$

### 3. Space-Time Feasibility & Safety Window
For an agent constructing a firebreak at $(x, y)$ over time interval $[t_{\text{start}}, t_{\text{end}}]$:
$$t_{\text{end}} \le T_{\text{fire}}(x, y) - \Delta \tau_{\text{safety}}$$
where $\Delta \tau_{\text{safety}}$ is the safety margin buffer (typically 60s for mechanized units, 80s for hand crews).

---

## Architecture & Project Structure

```
forest_fire_sta/
├── fire_sim/
│   ├── grid.py            # Terrain, elevation, fuel, assets, cell state matrix
│   ├── weather.py         # Dynamic wind vectors, schedules, gusts
│   └── spread_model.py    # ROS calculation, forward Dijkstra T_fire, CA stepper
├── containment/
│   ├── agent.py           # Heterogeneous agents (Bulldozer, HandCrew)
│   ├── space_time_astar.py# 4D Space-Time A* planner and ReservationTable
│   ├── perimeter_planner.py# Containment line generation and corridor allocation
│   └── dynamic_replanner.py# Closed-loop monitor and rolling-horizon replanner
├── metrics/
│   └── evaluator.py       # Burned area, asset protection, safety margin metrics
├── scenarios/
│   └── benchmark_scenarios.py # 4 benchmark scenarios (Valley, Wind Shift, Asset Defense, Pinch)
├── visualization/
│   ├── visualizer.py      # Matplotlib contour plots and map rendering
│   └── interactive_gui.py # Standalone HTML5 canvas GUI and local HTTP dashboard
├── tests/
│   ├── test_grid.py
│   ├── test_spread.py
│   ├── test_space_time_astar.py
│   ├── test_containment.py
│   └── test_replanner.py
├── run_demo.py            # Comprehensive CLI demonstration runner
└── output/                # Generated simulation plots and HTML dashboard
```

---

## Quickstart Guide

### 1. Run Unit Tests
```bash
python3 -m unittest discover -s forest_fire_sta/tests -p "test_*.py" -v
```

### 2. Run All Benchmark Scenarios & Generate Plots
```bash
python3 run_demo.py --scenario all --save-plots
```
Generated maps are saved in the `output/` directory:
- `output/valley_flanking_containment.png`
- `output/sudden_wind_shift_and_dynamic_replanning.png`
- `output/community_and_asset_defense.png`
- `output/multi-agent_coordinated_pinch.png`

### 3. Compare with Unsuppressed Baseline
```bash
python3 run_demo.py --compare-baseline --scenario valley
```
Outputs a comparative evaluation showing burned hectares reduction and safety margins.

### 4. Interactive Simulation Web Dashboard
Launch the built-in local server:
```bash
python3 run_demo.py --serve --port 8080
```
Then open `http://localhost:8080/firebreak_simulator.html` in any modern web browser to interactively control playback, trigger wind shifts, switch scenarios, and monitor real-time telemetry.

Alternatively, double click or open the generated `output/firebreak_simulator.html` directly in your browser.
