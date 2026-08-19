"""Show the cover's OUTER face -- the one that meets the wall -- so the vents can be seen."""
import numpy as np, trimesh, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import mask_params as P

C = trimesh.load("cover.stl", process=True)
lo, hi = C.bounds
STEP = 0.35
xs = np.arange(lo[0], hi[0], STEP); ys = np.arange(lo[1], hi[1], STEP)
XX, YY = np.meshgrid(xs, ys)
o = np.column_stack([XX.ravel(), YY.ravel(), np.full(XX.size, hi[2] + 10)])
d = np.tile([0, 0, -1.0], (len(o), 1))
loc, idx, _ = C.ray.intersects_location(ray_origins=o, ray_directions=d, multiple_hits=False)
D = np.full(len(o), np.nan); D[idx] = loc[:, 2]
D = D.reshape(XX.shape)

fig, ax = plt.subplots(figsize=(9, 14))
ls = LightSource(azdeg=315, altdeg=45)
rgb = ls.shade(np.nan_to_num(D, nan=float(np.nanmin(D))), cmap=plt.get_cmap("bone"),
               vert_exag=6, blend_mode="soft")
rgb[np.isnan(D)] = 1.0
ax.imshow(rgb, origin="lower", extent=(xs[0], xs[-1], ys[0], ys[-1]))
for label, zs in P.VENT_BANKS.items():
    ax.annotate(label, (P.VENT_L / 2 + 3, float(np.mean(zs))), fontsize=9,
                color="crimson", va="center")
c0, c1 = P.CELL_CZ - P.CELL_POCKET_H/2, P.CELL_CZ + P.CELL_POCKET_H/2
ax.axhspan(c0, c1, color="tab:blue", alpha=0.12)
ax.annotate("cell — deliberately unvented", (0, (c0+c1)/2), fontsize=9,
            color="tab:blue", ha="center")
ax.set_aspect("equal"); ax.set_xlabel("x (mm)"); ax.set_ylabel("z (mm)")
ax.set_title("cover, OUTER face (meets the wall) — 9 vents, 595 mm²", fontsize=11)
ax.grid(True, lw=0.3, alpha=0.4)
fig.tight_layout(); fig.savefig("cover_vents.png", dpi=95)
print("wrote cover_vents.png")
