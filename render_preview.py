"""render_preview.png -- the drawing that proves the conversion is right.

Six panels:
  1  FRONT of the converted mask, shaded -- the only thing a viewer ever sees.  The brow
     aperture and the two pupils have to look deliberate here or the design has failed.
  2  BACK, shaded -- the bay, its two floors, the board bosses, the camera seat.
  3  VERTICAL SECTION on the mirror line -- THE drawing.  It shows the one idea: the bay
     carved into the mask's own thickness, with the relief left in front of it.
  4  SECTION through the camera, showing the lens' line of sight out of the brow.
  5  SECTION through the eyes.
  6  The numbers.

Views 1 and 2 are ray-cast depth shades rather than GL renders: no display needed, and
they measure the actual surface instead of trusting a rasteriser.
"""
import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from matplotlib.patches import Rectangle

import mask_params as P

M = trimesh.load("mask_cam.stl", process=False)
STEP = 0.45


def depth_shade(mesh, direction=+1):
    """Orthographic shaded view along Y.  direction +1 looks from -Y (the front)."""
    lo, hi = mesh.bounds
    xs = np.arange(lo[0], hi[0], STEP)
    zs = np.arange(lo[2], hi[2], STEP)
    XX, ZZ = np.meshgrid(xs, zs)
    y0 = (lo[1] - 10.0) if direction > 0 else (hi[1] + 10.0)
    origins = np.column_stack([XX.ravel(), np.full(XX.size, y0), ZZ.ravel()])
    dirs = np.tile([0.0, float(direction), 0.0], (len(origins), 1))
    loc, idx, _ = mesh.ray.intersects_location(ray_origins=origins,
                                               ray_directions=dirs,
                                               multiple_hits=False)
    depth = np.full(len(origins), np.nan)
    depth[idx] = loc[:, 1] * direction
    return xs, zs, depth.reshape(XX.shape)


def draw_shade(ax, xs, zs, D, title):
    ls = LightSource(azdeg=315, altdeg=42)
    fill = float(np.nanmin(D)) if np.isfinite(D).any() else 0.0
    rgb = ls.shade(np.nan_to_num(D, nan=fill), cmap=plt.get_cmap("bone"),
                   vert_exag=2.6, blend_mode="soft")
    rgb[np.isnan(D)] = 1.0
    ax.imshow(rgb, origin="lower", extent=(xs[0], xs[-1], zs[0], zs[-1]))
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)
    ax.set_xticks(np.arange(-50, 51, 10))
    ax.set_yticks(np.arange(0, 106, 10))
    ax.grid(True, lw=0.3, alpha=0.35, color="0.5")
    ax.tick_params(labelsize=6)


def section(ax, normal, origin, title, horiz=False):
    """Plot a planar section of the converted mask."""
    sec = M.section(plane_origin=origin, plane_normal=normal)
    if sec is None:
        ax.text(0.5, 0.5, "no section", ha="center", transform=ax.transAxes)
        return
    for ent in sec.entities:
        pts = sec.vertices[ent.points]
        if horiz:          # cutting z = const -> plot (x, y)
            u, v = pts[:, 0], pts[:, 1]
        else:              # cutting x = const -> plot (y, z)
            u, v = pts[:, 1], pts[:, 2]
        ax.plot(u, v, "-", color="#1f3b63", lw=1.0)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)
    ax.grid(True, lw=0.3, alpha=0.4)
    ax.tick_params(labelsize=6)


fig = plt.figure(figsize=(19, 13))
fig.suptitle("Gini Raksha mask — ESP32-S3-CAM conversion.   "
             f"{P.MASK_W:.1f} × {P.MASK_D:.1f} × {P.MASK_H:.1f} mm, "
             "donor silhouette unchanged", fontsize=13, weight="bold")

ax = fig.add_subplot(2, 3, 1)
xs, zs, D = depth_shade(M, +1)
draw_shade(ax, xs, zs, D, "1 — FRONT: what anyone ever sees")
ax.add_patch(plt.Circle((P.LENS_X, P.LENS_Z), P.APERTURE_D / 2,
                        fill=False, color="crimson", lw=1.6))
ax.annotate("lens", (P.LENS_X + 5, P.LENS_Z + 4), color="crimson", fontsize=8)
for s in (-1, 1):
    ax.add_patch(plt.Circle((s * P.EYE_X, P.EYE_Z), P.EYE_PUPIL_D / 2,
                            fill=False, color="darkorange", lw=1.2, ls=":"))

ax = fig.add_subplot(2, 3, 2)
xs, zs, D = depth_shade(M, -1)
draw_shade(ax, xs, zs, D, "2 — BACK: the bay, before the cover goes on")

ax = fig.add_subplot(2, 3, 3)
section(ax, [1, 0, 0], [0, 0, 0], "3 — SECTION on the mirror line (y across, z up)")
ax.set_xlabel("y  (0 = wall plane, negative = out toward the viewer)", fontsize=7)
ax.set_ylabel("z", fontsize=7)
for y, lab, col in ((P.FLOOR_Y_UP, "bay floor (upper)", "tab:blue"),
                    (P.FLOOR_Y_LO, "bay floor (lower)", "tab:cyan"),
                    (P.CAM_POCKET_Y, "camera pocket", "crimson"),
                    (-P.COVER_T, "cover inner face", "tab:green"),
                    (0.0, "WALL", "k")):
    ax.axvline(y, color=col, lw=0.8, ls="--", alpha=0.8)
    ax.annotate(lab, (y, 100), rotation=90, fontsize=6, color=col,
                ha="right", va="top")
ax.add_patch(Rectangle((P.BOARD_BACK_Y - P.COMP_Z_MAX, P.BOARD_CZ - P.PCB_L / 2),
                       P.BOARD_STACK_T, P.PCB_L, fill=True, alpha=0.25,
                       color="tab:green"))
ax.annotate("ESP32-S3-CAM\n(pins snipped)", (P.BOARD_BACK_Y - 3, P.BOARD_CZ),
            fontsize=7, color="darkgreen", ha="center")

ax = fig.add_subplot(2, 3, 4)
section(ax, [0, 0, 1], [0, 0, P.LENS_Z],
        f"4 — SECTION at z={P.LENS_Z:.0f}: the camera's line of sight", horiz=True)
ax.set_xlabel("x", fontsize=7)
ax.set_ylabel("y", fontsize=7)
for s in (-1, 1):
    ax.plot([0, s * 40 * np.tan(np.radians(35))], [P.CAM_POCKET_Y, P.CAM_POCKET_Y - 40],
            color="crimson", lw=0.9, ls=":")
ax.annotate("70° cone (worst case)", (0, P.CAM_POCKET_Y - 30), fontsize=7,
            color="crimson", ha="center")

ax = fig.add_subplot(2, 3, 5)
section(ax, [0, 0, 1], [0, 0, P.EYE_Z],
        f"5 — SECTION at z={P.EYE_Z:.1f}: the eye pupils", horiz=True)
ax.set_xlabel("x", fontsize=7)
ax.set_ylabel("y", fontsize=7)

ax = fig.add_subplot(2, 3, 6)
ax.axis("off")
fov_lo = 2 * np.degrees(np.arctan((P.APERTURE_D / 2) / P.LENS_SETBACK_MAX))
fov_hi = 2 * np.degrees(np.arctan((P.APERTURE_D / 2) / P.LENS_SETBACK_MIN))
ax.text(0.0, 1.0, "\n".join([
    "THE NUMBERS",
    "",
    P.summary(),
    "",
    f"  aperture   Ø{P.APERTURE_D} at (x=0, z={P.LENS_Z:.0f}), the brow",
    f"             {fov_lo:.0f}°..{fov_hi:.0f}° depending on your module's barrel",
    f"  pupils     Ø{P.EYE_PUPIL_D} at x=±{P.EYE_X:.2f}, z={P.EYE_Z:.2f} "
    f"({P.EYE_DOME_R - P.EYE_PUPIL_D/2:.2f} mm of eyeball rim left)",
    "",
    "  PARTS",
    "    mask_cam.stl      the mask                      ~79 g",
    "    cover.stl         closes the bay, hangs it      ~9 g",
    "    camera_clamp.stl  holds the module               <1 g",
    "    camera_shims.stl  0.5 / 1.0 / 2.0 depth shims    <1 g",
    "    eye_plugs.stl     two, print in black            <1 g",
    "",
    "  SCREWS   4 × M3×8 flat self-tapping   (cover)",
    "           4 × M3×6 flat self-tapping   (board)",
    "           2 × M2.5×6 self-tapping      (camera clamp)",
    "           2 × #6 or M4 pan head        (in the wall, for the keyholes)",
    "",
    "  THE ONE IRREVERSIBLE STEP",
    "    flush-cut the board's two 8-pin header rows.  14.5 → 10.5 mm,",
    "    and without it nothing fits.",
]), fontsize=8.5, family="monospace", va="top", transform=ax.transAxes)

fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig("render_preview.png", dpi=95)
print("wrote render_preview.png")
