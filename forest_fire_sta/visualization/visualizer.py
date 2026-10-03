"""
Matplotlib-based visualizer for wildfire spread, firebreak construction, and space-time trajectories.
"""

from typing import List, Optional, Tuple
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for headless execution and saving
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

from ..fire_sim.grid import ForestGrid, CellState
from ..fire_sim.weather import WindVector
from ..containment.agent import SuppressionAgent, ActionType


class ForestFireVisualizer:
    """
    Renders high-resolution maps of terrain, fire arrival contours, and containment plans.
    """

    def __init__(self, grid: ForestGrid):
        self.grid = grid

    def render_map(
        self,
        t_fire: Optional[np.ndarray] = None,
        agents: Optional[List[SuppressionAgent]] = None,
        wind: Optional[WindVector] = None,
        target_cells: Optional[List[Tuple[int, int]]] = None,
        title: str = "Wildfire Containment & Space-Time A* Firebreak Planning",
        save_path: Optional[str] = None,
        show_contours: bool = True,
    ) -> plt.Figure:
        """
        Produce a comprehensive 2D containment map.
        """
        fig, ax = plt.subplots(figsize=(10, 9), dpi=150)

        # 1. Base terrain / elevation hillshade
        elev = self.grid.elevation
        im_elev = ax.imshow(
            elev,
            cmap="Greens",
            origin="lower",
            alpha=0.35,
            extent=[0, self.grid.width, 0, self.grid.height],
        )

        # 2. Display Assets
        asset_mask = self.grid.asset_values > 0
        if np.any(asset_mask):
            y_indices, x_indices = np.where(asset_mask)
            for ax_coord, ay_coord in zip(x_indices, y_indices):
                rect = patches.Rectangle(
                    (ax_coord, ay_coord), 1, 1,
                    linewidth=1, edgecolor="purple", facecolor="mediumpurple", alpha=0.6,
                )
                ax.add_patch(rect)
            ax.plot([], [], color="mediumpurple", marker="s", linestyle="None", label="Asset / Community")

        # 3. Barriers (Rivers / Roads / Rock)
        barrier_mask = self.grid.state == CellState.BARRIER
        if np.any(barrier_mask):
            y_indices, x_indices = np.where(barrier_mask)
            for bx, by in zip(x_indices, y_indices):
                rect = patches.Rectangle(
                    (bx, by), 1, 1,
                    linewidth=0, facecolor="#1E88E5", alpha=0.8,
                )
                ax.add_patch(rect)
            ax.plot([], [], color="#1E88E5", marker="s", linestyle="None", label="Natural Barrier (River)")

        # 4. Fire Arrival Isochrones (T_fire contours)
        if show_contours and t_fire is not None:
            valid_t = np.where(np.isinf(t_fire), np.nan, t_fire)
            if not np.all(np.isnan(valid_t)):
                min_t = np.nanmin(valid_t)
                max_t = np.nanmax(valid_t)
                if max_t > min_t:
                    levels = np.linspace(min_t, min(max_t, 400.0), 9)
                    cs = ax.contour(
                        valid_t,
                        levels=levels,
                        cmap="YlOrRd",
                        origin="lower",
                        linewidths=1.2,
                        extent=[0, self.grid.width, 0, self.grid.height],
                    )
                    ax.clabel(cs, inline=True, fontsize=8, fmt="%1.0fs")

        # 5. Burned and Burning Cells
        burned_mask = self.grid.state == CellState.BURNED
        if np.any(burned_mask):
            y_b, x_b = np.where(burned_mask)
            ax.scatter(x_b + 0.5, y_b + 0.5, c="#424242", s=18, marker="s", label="Burned (Ash)", alpha=0.85)

        burning_mask = self.grid.state == CellState.BURNING
        if np.any(burning_mask):
            y_f, x_f = np.where(burning_mask)
            ax.scatter(x_f + 0.5, y_f + 0.5, c="#FF3D00", s=32, marker="o", edgecolors="#FFEA00", label="Active Flame Front")

        # 6. Constructed Firebreaks
        firebreak_mask = self.grid.state == CellState.FIREBREAK
        if np.any(firebreak_mask):
            y_fb, x_fb = np.where(firebreak_mask)
            ax.scatter(x_fb + 0.5, y_fb + 0.5, c="#00C853", s=36, marker="s", edgecolors="#1B5E20", label="Completed Firebreak")

        # 7. Target Planned Corridor (Unfinished)
        if target_cells:
            tx = [c[0] + 0.5 for c in target_cells]
            ty = [c[1] + 0.5 for c in target_cells]
            ax.plot(tx, ty, "b--", linewidth=1.5, alpha=0.6, label="Planned Containment Line")

        # 8. Agents and Trajectories
        agent_colors = ["#2962FF", "#AA00FF", "#00BFA5", "#FF6D00"]
        if agents:
            for idx, agent in enumerate(agents):
                color = agent_colors[idx % len(agent_colors)]
                # Planned path
                if agent.plan:
                    px = [s.x + 0.5 for s in agent.plan]
                    py = [s.y + 0.5 for s in agent.plan]
                    ax.plot(px, py, color=color, linestyle=":", linewidth=2, label=f"{agent.name} Plan")

                # Current position
                ax.plot(
                    agent.x + 0.5,
                    agent.y + 0.5,
                    marker="^",
                    color=color,
                    markersize=12,
                    markeredgecolor="black",
                    label=f"{agent.name} (Now)",
                )

        # 9. Wind Vector Indicator
        if wind is not None and wind.speed > 0:
            arrow_len = 3.5
            u, v = wind.heading_vector()
            wx_start = self.grid.width - 5
            wy_start = self.grid.height - 5
            ax.annotate(
                f"Wind: {wind.speed} m/s\nDir: {wind.direction_deg:.0f}°",
                xy=(wx_start + u * arrow_len, wy_start + v * arrow_len),
                xytext=(wx_start, wy_start),
                arrowprops=dict(facecolor="black", edgecolor="black", width=1.5, headwidth=7),
                fontsize=9,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8),
            )

        ax.set_title(title, fontsize=12, fontweight="bold", pad=12)
        ax.set_xlabel("X Distance (Grid Cells)")
        ax.set_ylabel("Y Distance (Grid Cells)")
        ax.set_xlim(0, self.grid.width)
        ax.set_ylim(0, self.grid.height)
        ax.set_aspect("equal")
        ax.grid(True, linestyle="--", alpha=0.3)
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0, fontsize=8)

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, bbox_inches="tight")
        return fig
