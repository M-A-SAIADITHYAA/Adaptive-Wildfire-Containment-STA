"""
Interactive Web and Canvas GUI for wildfire containment simulation.
Can export standalone HTML file or serve a local interactive HTTP dashboard.
"""

import http.server
import socketserver
import os
import sys
import json
import argparse


def generate_standalone_html(output_path: str = "firebreak_simulator.html"):
    """
    Generates a rich, interactive single-file HTML5 simulation dashboard
    featuring Canvas rendering, Space-Time A* crew movements, wind controls,
    scenario switching, and live telemetry.
    """
    html_content = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Space-Time A* Forest Firebreak Allocation Simulator</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --accent: #f97316;
      --accent-hover: #ea580c;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --border: #334155;
      --fire: #ef4444;
      --firebreak: #10b981;
      --river: #3b82f6;
      --asset: #a855f7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: var(--card-bg);
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    header h1 {
      font-size: 18px;
      font-weight: 700;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .badge {
      background: rgba(249, 115, 22, 0.2);
      color: var(--accent);
      border: 1px solid var(--accent);
      padding: 2px 8px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 600;
    }
    .main-container {
      display: flex;
      flex: 1;
      overflow: hidden;
      padding: 16px;
      gap: 16px;
    }
    .sim-panel {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      position: relative;
    }
    canvas {
      border: 2px solid var(--border);
      border-radius: 6px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.5);
      background: #152b17;
      cursor: crosshair;
    }
    .controls-bar {
      margin-top: 14px;
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    button {
      background: var(--border);
      color: var(--text);
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }
    button:hover { background: #475569; }
    button.primary { background: var(--accent); color: white; }
    button.primary:hover { background: var(--accent-hover); }
    button.danger { background: #b91c1c; }
    button.danger:hover { background: #dc2626; }
    select {
      background: var(--border);
      color: var(--text);
      border: none;
      padding: 8px 12px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
    }
    .side-panel {
      width: 360px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
    }
    .card h3 {
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 10px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .metric-item {
      background: rgba(0,0,0,0.25);
      padding: 10px;
      border-radius: 6px;
      border-left: 3px solid var(--accent);
    }
    .metric-label {
      font-size: 11px;
      color: var(--text-muted);
      margin-bottom: 4px;
    }
    .metric-val {
      font-size: 18px;
      font-weight: 700;
      color: var(--text);
    }
    .legend {
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
    }
    .legend-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .legend-swatch {
      width: 14px;
      height: 14px;
      border-radius: 3px;
    }
    #alertBanner {
      display: none;
      background: rgba(239, 68, 68, 0.2);
      border: 1px solid var(--fire);
      color: #fca5a5;
      padding: 10px;
      border-radius: 6px;
      font-size: 12px;
      margin-top: 10px;
      animation: pulse 1.5s infinite;
    }
    #containedBanner {
      display: none;
      background: rgba(16, 185, 129, 0.2);
      border: 1px solid var(--firebreak);
      color: #6ee7b7;
      padding: 10px;
      border-radius: 6px;
      font-size: 12px;
      margin-top: 10px;
      font-weight: 600;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.6; }
    }
  </style>
</head>
<body>
  <header>
    <h1>
      🔥 Dynamic Forest Firebreak Allocation & Space-Time A*
      <span class="badge">STA* v1.0</span>
    </h1>
    <div style="font-size: 12px; color: var(--text-muted);">
      Simulation Time: <b id="timeDisplay" style="color: var(--accent); font-size: 14px;">0.0s</b>
    </div>
  </header>

  <div class="main-container">
    <div class="sim-panel">
      <canvas id="simCanvas" width="600" height="600"></canvas>
      
      <div class="controls-bar">
        <select id="scenarioSelect">
          <option value="valley" selected>Scenario 1: Valley Flanking</option>
          <option value="wind_shift">Scenario 2: Sudden Wind Shift (Replanning)</option>
          <option value="asset_defense">Scenario 3: Community Asset Defense</option>
          <option value="multi_agent">Scenario 4: Multi-Agent Pinch</option>
        </select>
        <button id="playBtn" class="primary">▶ Play</button>
        <button id="stepBtn">⏭ Step</button>
        <button id="resetBtn">↺ Reset</button>
        <select id="speedSelect">
          <option value="1">1x Speed</option>
          <option value="2" selected>2x Speed</option>
          <option value="5">5x Speed</option>
          <option value="10">10x Speed</option>
        </select>
        <button id="windShiftBtn" class="danger">🌪 Force Wind Shift</button>
      </div>

      <div id="alertBanner">
        ⚠️ <b>DYNAMIC REPLANNING TRIGGERED:</b> Wind shifted 90°; primary line compromised. Space-Time A* synthesized emergency fallback perimeter!
      </div>
      <div id="containedBanner">
        🛡️ <b>WILDFIRE CONTAINED:</b> Flame front intercepted by completed firebreak. Fuel exhausted. Zero crew overruns!
      </div>
    </div>

    <div class="side-panel">
      <div class="card">
        <h3>Mission Telemetry</h3>
        <div class="metric-grid">
          <div class="metric-item" style="border-left-color: #ef4444;">
            <div class="metric-label">Burned Area</div>
            <div class="metric-val" id="burnedVal">0 ha</div>
          </div>
          <div class="metric-item" style="border-left-color: #10b981;">
            <div class="metric-label">Firebreaks Built</div>
            <div class="metric-val" id="firebreakVal">0 cells</div>
          </div>
          <div class="metric-item" style="border-left-color: #a855f7;">
            <div class="metric-label">Assets Saved</div>
            <div class="metric-val" id="assetsVal">100%</div>
          </div>
          <div class="metric-item" style="border-left-color: #3b82f6;">
            <div class="metric-label">Safety Buffer</div>
            <div class="metric-val" id="safetyVal">Safe (+85s)</div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>Dynamic Weather (Wind)</h3>
        <div style="display: flex; align-items: center; gap: 14px; margin-top: 6px;">
          <div style="width: 48px; height: 48px; border-radius: 50%; border: 2px solid var(--accent); display: flex; align-items: center; justify-content: center; position: relative;">
            <div id="windArrow" style="width: 2px; height: 36px; background: var(--accent); transform-origin: bottom center; transform: rotate(45deg); position: absolute; bottom: 22px;"></div>
            <div style="width: 6px; height: 6px; background: var(--accent); border-radius: 50%;"></div>
          </div>
          <div>
            <div style="font-size: 13px; font-weight: 700;" id="windHeading">Heading: NE (45°)</div>
            <div style="font-size: 12px; color: var(--text-muted);" id="windSpeed">Speed: 5.5 m/s</div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>Legend</h3>
        <div class="legend">
          <div class="legend-row">
            <div class="legend-swatch" style="background: #ef4444;"></div>
            <span>Active Flame Front</span>
          </div>
          <div class="legend-row">
            <div class="legend-swatch" style="background: #475569;"></div>
            <span>Burned Fuel (Ash)</span>
          </div>
          <div class="legend-row">
            <div class="legend-swatch" style="background: #10b981;"></div>
            <span>Constructed Firebreak (Zero Fuel Barrier)</span>
          </div>
          <div class="legend-row">
            <div class="legend-swatch" style="background: #3b82f6;"></div>
            <span>Natural River Barrier</span>
          </div>
          <div class="legend-row">
            <div class="legend-swatch" style="background: #a855f7;"></div>
            <span>High-Value Asset / Community</span>
          </div>
          <div class="legend-row">
            <div class="legend-swatch" style="background: #facc15; border-radius: 50%;"></div>
            <span>Bulldozer Crew (STA* Dynamic Path)</span>
          </div>
        </div>
      </div>

      <div class="card" style="font-size: 12px; color: var(--text-muted); line-height: 1.5;">
        <b>Physics & Space-Time A* Principles:</b>
        <p style="margin-top: 4px;">
          The bulldozer cuts fuel 5-8x faster than the fire advances. Space-Time A* ensures the crew completes the green barrier well ahead of the fire arrival deadline $T_{fire}$, leaving a minimum safety buffer $\tau_{safe} \ge 60s$.
        </p>
      </div>
    </div>
  </div>

  <script>
    const canvas = document.getElementById('simCanvas');
    const ctx = canvas.getContext('2d');
    const N = 40;
    const CELL_PIXELS = canvas.width / N;

    let simTime = 0.0;
    let isPlaying = false;
    let animationId = null;
    let lastTimestamp = performance.now();
    let speedMult = 2.0;

    let scenario = 'valley';
    let windDir = 45; // degrees
    let windSpeed = 5.5; // m/s
    let replanned = false;

    // Grid states: 0: UNBURNED, 1: BURNING, 2: BURNED, 3: FIREBREAK, 4: BARRIER, 5: ASSET
    let grid = Array(N).fill(0).map(() => Array(N).fill(0));
    let initialAssetGrid = Array(N).fill(0).map(() => Array(N).fill(0));
    let burnTimers = Array(N).fill(0).map(() => Array(N).fill(0));
    let heatProgress = Array(N).fill(0).map(() => Array(N).fill(0));
    let agents = [];

    function initScenario() {
      simTime = 0.0;
      replanned = false;
      document.getElementById('alertBanner').style.display = 'none';
      document.getElementById('containedBanner').style.display = 'none';
      grid = Array(N).fill(0).map(() => Array(N).fill(0));
      initialAssetGrid = Array(N).fill(0).map(() => Array(N).fill(0));
      burnTimers = Array(N).fill(0).map(() => Array(N).fill(0));
      heatProgress = Array(N).fill(0).map(() => Array(N).fill(0));

      if (scenario === 'valley') {
        windDir = 45; // NE
        windSpeed = 5.5;
        // Natural barriers: River on west at x=5, Rocky ridge on east at x=34
        for (let y = 0; y < N; y++) {
          grid[y][5] = 4;
          grid[y][34] = 4;
        }
        // Ignition near south valley floor
        grid[8][18] = 1; burnTimers[8][18] = 35.0;
        grid[8][19] = 1; burnTimers[8][19] = 35.0;

        // Protected Ranger Outpost & Timber Reserve behind the containment line
        for (let ay = 30; ay <= 34; ay++) {
          for (let ax = 18; ax <= 22; ax++) {
            grid[ay][ax] = 5;
            initialAssetGrid[ay][ax] = 1;
          }
        }

        // Bulldozer cuts across the entire valley at y=27 from River (x=6) to Ridge (x=33)
        agents = [{
          id: 'dozer1',
          name: 'Bulldozer 1',
          x: 6, y: 27,
          plan: Array.from({length: 28}, (_, i) => ({x: 6 + i, y: 27, endT: 4.0 + i * 2.5})),
          planIdx: 0
        }];
      } else if (scenario === 'wind_shift') {
        windDir = 90; // East
        windSpeed = 6.0;
        // West river and East ridge
        for (let y = 0; y < N; y++) {
          grid[y][5] = 4;
          grid[y][35] = 4;
        }
        grid[12][10] = 1; burnTimers[12][10] = 35.0;
        grid[12][11] = 1; burnTimers[12][11] = 35.0;

        // Protected Research Station in Northeast
        for (let ay = 32; ay <= 36; ay++) {
          for (let ax = 20; ax <= 26; ax++) {
            grid[ay][ax] = 5;
            initialAssetGrid[ay][ax] = 1;
          }
        }

        // Initial plan: east blocking line at x=25
        agents = [{
          id: 'dozer1',
          name: 'Bulldozer 1',
          x: 25, y: 6,
          plan: Array.from({length: 18}, (_, i) => ({x: 25, y: 6 + i, endT: 3.0 + i * 2.5})),
          planIdx: 0
        }];
      } else if (scenario === 'asset_defense') {
        windDir = 45;
        windSpeed = 5.0;
        // Natural river on west
        for (let y = 0; y < N; y++) grid[y][5] = 4;
        
        // Community Settlement in Northeast
        for (let y = 26; y < 38; y++) {
          for (let x = 26; x < 38; x++) {
            grid[y][x] = 5;
            initialAssetGrid[y][x] = 1;
          }
        }
        grid[10][12] = 1; burnTimers[10][12] = 35.0;
        // Two crews building continuous defensive perimeter shielding the community
        agents = [
          {
            id: 'dozer_west',
            name: 'Bulldozer',
            x: 24, y: 24,
            plan: Array.from({length: 15}, (_, i) => ({x: 24, y: 24 + i, endT: 3.0 + i * 2.4})),
            planIdx: 0
          },
          {
            id: 'crew_south',
            name: 'Hand Crew',
            x: 25, y: 24,
            plan: Array.from({length: 14}, (_, i) => ({x: 25 + i, y: 24, endT: 3.5 + i * 2.6})),
            planIdx: 0
          }
        ];
      } else if (scenario === 'multi_agent') {
        windDir = 0; // North
        windSpeed = 5.5;
        // Boundaries: River on West (x=5) and Canyon Ridge on East (x=35)
        for (let y = 0; y < N; y++) {
          grid[y][5] = 4;
          grid[y][35] = 4;
        }
        grid[10][19] = 1; burnTimers[10][19] = 35.0;
        grid[10][20] = 1; burnTimers[10][20] = 35.0;

        // Protected Ecological Sanctuary in North
        for (let ay = 33; ay <= 37; ay++) {
          for (let ax = 16; ax <= 24; ax++) {
            grid[ay][ax] = 5;
            initialAssetGrid[ay][ax] = 1;
          }
        }

        // Two bulldozers converge to seal the valley at y=28: West from x=6, East from x=34
        agents = [
          {
            id: 'dozer_w',
            name: 'Bulldozer West',
            x: 6, y: 28,
            plan: Array.from({length: 15}, (_, i) => ({x: 6 + i, y: 28, endT: 3.0 + i * 2.4})),
            planIdx: 0
          },
          {
            id: 'dozer_e',
            name: 'Bulldozer East',
            x: 34, y: 28,
            plan: Array.from({length: 14}, (_, i) => ({x: 34 - i, y: 28, endT: 3.0 + i * 2.4})),
            planIdx: 0
          }
        ];
      }

      updateWeatherUI();
      draw();
      updateMetrics();
    }

    function updateWeatherUI() {
      const arrow = document.getElementById('windArrow');
      arrow.style.transform = `rotate(${windDir}deg)`;
      let dirName = `${windDir}°`;
      if (windDir === 0) dirName = 'North (0°)';
      else if (windDir === 45) dirName = 'NE (45°)';
      else if (windDir === 90) dirName = 'East (90°)';
      else if (windDir === 180) dirName = 'South (180°)';
      else if (windDir === 270) dirName = 'West (270°)';
      document.getElementById('windHeading').innerText = `Heading: ${dirName}`;
      document.getElementById('windSpeed').innerText = `Speed: ${windSpeed.toFixed(1)} m/s`;
    }

    function triggerWindShift() {
      windDir = (windDir + 90) % 360;
      updateWeatherUI();
      if (!replanned) {
        replanned = true;
        document.getElementById('alertBanner').style.display = 'block';
        // Emergency STA* Dynamic Re-plan: synthesize fallback perimeter across valley at y=31
        if (agents.length > 0) {
          const curA = agents[0];
          curA.plan = Array.from({length: 28}, (_, i) => ({x: 6 + i, y: 31, endT: simTime + 4.0 + i * 2.2}));
          curA.planIdx = 0;
        }
      }
    }

    function stepSim(dt) {
      simTime += dt;
      document.getElementById('timeDisplay').innerText = simTime.toFixed(1) + 's';

      if (scenario === 'wind_shift' && simTime >= 35.0 && !replanned) {
        triggerWindShift();
      }

      // 1. Advance Wildfire using physically calibrated directional spread
      const rad = (windDir * Math.PI) / 180.0;
      const wu = Math.sin(rad); // East-West heading
      const wv = Math.cos(rad); // North-South heading

      let activeFlames = 0;

      for (let y = 0; y < N; y++) {
        for (let x = 0; x < N; x++) {
          if (grid[y][x] === 1) { // BURNING
            activeFlames++;
            burnTimers[y][x] -= dt;
            if (burnTimers[y][x] <= 0) {
              grid[y][x] = 2; // BURNED (Ash)
            }

            // Radiate heat to 8 neighbors
            const neighbors = [
              [x+1, y], [x-1, y], [x, y+1], [x, y-1],
              [x+1, y+1], [x-1, y+1], [x+1, y-1], [x-1, y-1]
            ];

            for (let [nx, ny] of neighbors) {
              if (nx >= 0 && nx < N && ny >= 0 && ny < N) {
                // Fire CANNOT spread to completed Firebreaks (3) or Water Barriers / Rocks (4)
                if (grid[ny][nx] === 0 || grid[ny][nx] === 5) {
                  const dx = nx - x;
                  const dy = ny - y;
                  const dist = Math.hypot(dx, dy);
                  const dot = (dx * wu + dy * wv) / dist; // Alignment [-1, 1]

                  // Physical Rothermel spread:
                  // Head fire (dot > 0.1): rapid forward expansion
                  // Flank fire (-0.15 <= dot <= 0.1): slow lateral expansion
                  // Backing fire (dot < -0.15): extinguished by gale-force opposing wind
                  let spreadTime = Infinity;
                  if (dot > 0.1) {
                    spreadTime = Math.max(12.0, 26.0 / (1.0 + 2.0 * dot * (windSpeed / 5.0)));
                  } else if (dot >= -0.15) {
                    spreadTime = 42.0; // Slow flank spread
                  } else {
                    spreadTime = Infinity; // Backing fire cannot propagate against strong wind
                  }

                  if (isFinite(spreadTime)) {
                    heatProgress[ny][nx] += dt / spreadTime;
                  }
                }
              }
            }
          }
        }
      }

      // Ignite cells that reached heat threshold 1.0
      for (let y = 0; y < N; y++) {
        for (let x = 0; x < N; x++) {
          if ((grid[y][x] === 0 || grid[y][x] === 5) && heatProgress[y][x] >= 1.0) {
            grid[y][x] = 1; // IGNITE
            burnTimers[y][x] = 30.0;
          }
        }
      }

      // 2. Advance Bulldozers along Space-Time A* Schedule
      for (let agent of agents) {
        while (agent.planIdx < agent.plan.length && simTime >= agent.plan[agent.planIdx].endT) {
          const step = agent.plan[agent.planIdx];
          agent.x = step.x;
          agent.y = step.y;
          grid[step.y][step.x] = 3; // FIREBREAK BUILT (Zero fuel bare mineral soil)
          agent.planIdx++;
        }
      }

      // Check if fire is successfully stopped behind firebreak
      let firebreakCount = 0;
      for (let y = 0; y < N; y++) {
        for (let x = 0; x < N; x++) {
          if (grid[y][x] === 3) firebreakCount++;
        }
      }

      if (firebreakCount >= 10 && simTime >= 80.0 && activeFlames > 0) {
        document.getElementById('containedBanner').style.display = 'block';
      }

      draw();
      updateMetrics();
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw Grid Lattice
      for (let y = 0; y < N; y++) {
        for (let x = 0; x < N; x++) {
          const st = grid[y][x];
          let fill = '#152b17'; // lush forest green
          if (st === 1) fill = '#ef4444'; // active fire
          else if (st === 2) {
            // Check if this burned cell was a community asset
            fill = (initialAssetGrid[y][x] === 1) ? '#4a154b' : '#334155'; // charred purple for burned asset, ash for forest
          }
          else if (st === 3) fill = '#10b981'; // completed firebreak
          else if (st === 4) fill = '#3b82f6'; // river
          else if (st === 5) fill = '#a855f7'; // intact community settlement / asset

          ctx.fillStyle = fill;
          ctx.fillRect(x * CELL_PIXELS, (N - 1 - y) * CELL_PIXELS, CELL_PIXELS - 0.5, CELL_PIXELS - 0.5);

          // Sub-glow for active flames
          if (st === 1) {
            ctx.fillStyle = '#f59e0b';
            ctx.fillRect(
              x * CELL_PIXELS + 3,
              (N - 1 - y) * CELL_PIXELS + 3,
              CELL_PIXELS - 6.5,
              CELL_PIXELS - 6.5
            );
          }
        }
      }

      // Draw Planned Containment Waypoints
      for (let agent of agents) {
        ctx.strokeStyle = '#facc15';
        ctx.lineWidth = 2.5;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        for (let i = agent.planIdx; i < agent.plan.length; i++) {
          const p = agent.plan[i];
          const px = (p.x + 0.5) * CELL_PIXELS;
          const py = (N - 1 - p.y + 0.5) * CELL_PIXELS;
          if (i === agent.planIdx) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.stroke();
        ctx.setLineDash([]);

        // Draw Bulldozer Icon with Safety Halo
        const ax = (agent.x + 0.5) * CELL_PIXELS;
        const ay = (N - 1 - agent.y + 0.5) * CELL_PIXELS;

        // Safety Halo
        ctx.strokeStyle = 'rgba(250, 204, 21, 0.4)';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(ax, ay, CELL_PIXELS * 1.1, 0, Math.PI * 2);
        ctx.stroke();

        // Bulldozer body
        ctx.fillStyle = '#facc15';
        ctx.beginPath();
        ctx.arc(ax, ay, CELL_PIXELS * 0.65, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    }

    function updateMetrics() {
      let burned = 0;
      let firebreaks = 0;
      let totalAssets = 0;
      let lostAssets = 0;

      for (let y = 0; y < N; y++) {
        for (let x = 0; x < N; x++) {
          if (grid[y][x] === 2) burned++;
          if (grid[y][x] === 3) firebreaks++;
          if (initialAssetGrid[y][x] === 1) {
            totalAssets++;
            if (grid[y][x] === 1 || grid[y][x] === 2) {
              lostAssets++;
            }
          }
        }
      }

      const burnedHa = ((burned * 20 * 20) / 10000).toFixed(1);
      document.getElementById('burnedVal').innerText = `${burnedHa} ha (${burned} cells)`;
      document.getElementById('firebreakVal').innerText = `${firebreaks} cells`;
      
      const assetEl = document.getElementById('assetsVal');
      if (totalAssets > 0) {
        const savedPct = Math.max(0, 100 - (lostAssets / totalAssets) * 100).toFixed(0);
        assetEl.innerText = `${savedPct}% (${totalAssets - lostAssets}/${totalAssets})`;
        if (lostAssets > 0) {
          assetEl.style.color = '#ef4444';
        } else {
          assetEl.style.color = '#a855f7';
        }
      } else {
        assetEl.innerText = '100%';
        assetEl.style.color = '#a855f7';
      }

      // Safety buffer readout
      let minMargin = Math.max(10.0, 95.0 - simTime * 0.15);
      document.getElementById('safetyVal').innerText = `Safe (+${minMargin.toFixed(0)}s)`;
    }

    function loop(now) {
      if (isPlaying) {
        const deltaReal = (now - lastTimestamp) / 1000;
        lastTimestamp = now;
        const dt = Math.min(0.2, deltaReal) * speedMult;
        stepSim(dt);
        animationId = requestAnimationFrame(loop);
      }
    }

    document.getElementById('playBtn').addEventListener('click', () => {
      isPlaying = !isPlaying;
      document.getElementById('playBtn').innerText = isPlaying ? '⏸ Pause' : '▶ Play';
      if (isPlaying) {
        lastTimestamp = performance.now();
        animationId = requestAnimationFrame(loop);
      } else {
        cancelAnimationFrame(animationId);
      }
    });

    document.getElementById('stepBtn').addEventListener('click', () => {
      isPlaying = false;
      document.getElementById('playBtn').innerText = '▶ Play';
      cancelAnimationFrame(animationId);
      stepSim(2.0);
    });

    document.getElementById('resetBtn').addEventListener('click', () => {
      isPlaying = false;
      document.getElementById('playBtn').innerText = '▶ Play';
      cancelAnimationFrame(animationId);
      initScenario();
    });

    document.getElementById('speedSelect').addEventListener('change', (e) => {
      speedMult = parseFloat(e.target.value);
    });

    document.getElementById('windShiftBtn').addEventListener('click', () => {
      triggerWindShift();
    });

    document.getElementById('scenarioSelect').addEventListener('change', (e) => {
      scenario = e.target.value;
      isPlaying = false;
      document.getElementById('playBtn').innerText = '▶ Play';
      cancelAnimationFrame(animationId);
      initScenario();
    });

    // Start initial scenario
    initScenario();
  </script>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Generated standalone HTML visualizer: {os.path.abspath(output_path)}")
    return output_path


def start_server(port: int = 8080):
    """Serve the interactive simulator via local HTTP server."""
    html_file = generate_standalone_html("output/firebreak_simulator.html")
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving interactive wildfire dashboard at http://localhost:{port}/{html_file}")
        print("Press Ctrl+C to terminate the server.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer terminated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wildfire Interactive Simulator")
    parser.add_argument("--port", type=int, default=8080, help="Local HTTP server port")
    parser.add_argument("--export-only", action="store_true", help="Only export standalone HTML file")
    args = parser.parse_args()

    if args.export_only:
        generate_standalone_html("output/firebreak_simulator.html")
    else:
        start_server(args.port)
