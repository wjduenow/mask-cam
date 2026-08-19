"""Show the camera clamp and the battery shim where they actually go.

Both panels are the view you get looking INTO the bay from behind, which is the view you
have with the cover off and the mask face-down on the bench.
"""
import matplotlib
import numpy as np
import trimesh

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource

import mask_params as P

MASK = trimesh.load("mask_cam.stl", process=True)


def depth(x0, x1, z0, z1, step):
    xs = np.arange(x0, x1, step); zs = np.arange(z0, z1, step)
    XX, ZZ = np.meshgrid(xs, zs)
    o = np.column_stack([XX.ravel(), np.full(XX.size, 40.0), ZZ.ravel()])
    d = np.tile([0, -1.0, 0], (len(o), 1))
    loc, idx, _ = MASK.ray.intersects_location(ray_origins=o, ray_directions=d,
                                               multiple_hits=False)
    Y = np.full(len(o), np.nan); Y[idx] = loc[:, 1]
    return xs, zs, Y.reshape(XX.shape)


def shade(ax, xs, zs, Y, vmin, vmax):
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(np.nan_to_num(Y, nan=vmin), cmap=plt.get_cmap("bone"),
                   vert_exag=2, blend_mode="soft", vmin=vmin, vmax=vmax)
    rgb[np.isnan(Y)] = 1.0
    ax.imshow(rgb, origin="lower", extent=(xs[0], xs[-1], zs[0], zs[-1]))


def outline(ax, mesh, to_mask, **kw):
    """True silhouette of a part in the mask's x-z plane.

    Union of its projected triangles -- not a hull, because the whole point of both parts
    is the holes in them, and a hull would fill those in.
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    v = to_mask(mesh.vertices)[:, [0, 2]]
    tris = [Polygon(v[f]) for f in mesh.faces]
    poly = unary_union([t for t in tris if t.is_valid and t.area > 1e-9]).buffer(0)
    geoms = getattr(poly, "geoms", [poly])
    for g in geoms:
        for ring in [g.exterior, *g.interiors]:
            ax.plot(*np.array(ring.coords).T, **kw)


fig, axes = plt.subplots(1, 2, figsize=(13, 7))

# ── camera clamp ──────────────────────────────────────────────────────────────
ax = axes[0]
xs, zs, Y = depth(-14, 14, 74, 104, 0.12)
shade(ax, xs, zs, Y, P.CAM_POCKET_Y, P.FLOOR_Y_MID)
clamp = trimesh.load("camera_clamp.stl", process=True)
cz = (P.CAM_SEAT_Z0 + P.CAM_SEAT_Z1_OPEN) / 2
outline(ax, clamp, lambda v: np.column_stack(
    [v[:, 0], P.CAM_SEAT_Y + (P.CAM_CLAMP_T - v[:, 2]), -v[:, 1] + cz]),
    color="crimson", lw=1.3)
ax.axhline(P.CAM_SEAT_Z1_OPEN, color="tab:blue", lw=1.2, ls="--")
ax.annotate("z=97: the battery zone's floor cuts the seat off here\n"
            "(the old clamp was 21.5 mm long and needed z=102)",
            (-13.4, 97.6), fontsize=8, color="tab:blue")
ax.annotate("the one reachable pilot", (0, 83), xytext=(-13.4, 77.5), fontsize=8,
            color="crimson", arrowprops=dict(arrowstyle="->", color="crimson"))
ax.annotate("ribbon slot", (0, 86.6), xytext=(6.5, 78.5), fontsize=8, color="crimson",
            arrowprops=dict(arrowstyle="->", color="crimson"))
ax.set_title("camera clamp in the seat that is actually printed", fontsize=10)
ax.set_xlabel("x (mm)"); ax.set_ylabel("z (mm)"); ax.set_aspect("equal")

# ── battery shim ──────────────────────────────────────────────────────────────
ax = axes[1]
xs, zs, Y = depth(-36, 36, 94, 162, 0.35)
shade(ax, xs, zs, Y, -52, -2.5)
shim = trimesh.load("battery_shim.stl", process=True)
sz = (P.BATT_SHIM_Z0 + P.BATT_SHIM_Z1) / 2
outline(ax, shim, lambda v: np.column_stack(
    [v[:, 0], -P.COVER_T - v[:, 2], v[:, 1] + sz]),
    color="crimson", lw=1.1)
ax.add_patch(plt.Rectangle((-P.CELL_W / 2, P.CELL_CZ - P.CELL_H / 2), P.CELL_W, P.CELL_H,
                           fill=False, ec="tab:blue", lw=1.4, ls="--"))
ax.annotate(f"the 55 × 55 cell", (0, P.CELL_CZ - P.CELL_H / 2 - 2.5), fontsize=8,
            color="tab:blue", ha="center")
ax.annotate(f"shim fills {P.BATT_SHIM_T:.2f} mm\nbetween cell and cover",
            (0, 158), fontsize=8, color="crimson", ha="center")
ax.set_title("battery shim over the cell (dark = the crown's own hollow)", fontsize=10)
ax.set_xlabel("x (mm)"); ax.set_ylabel("z (mm)"); ax.set_aspect("equal")

fig.tight_layout()
fig.savefig("smalls.png", dpi=110)
print("wrote smalls.png")
