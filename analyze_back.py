"""Map the mask's BACK surface: how much material is there, and is there a cavity?

The first pass showed exactly 2 ray crossings everywhere -> the plaque is SOLID between
a front surface and a back surface (no existing hollow).  This pass measures both
surfaces on a grid so we can see:

  * which Y face is the front (the one that bulges toward the viewer)
  * the local material thickness at every (x, z)
  * how deep a pocket we could sink into the back before breaking through the front

Outputs a PNG heatmap trio + a text summary.
"""
import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

m = trimesh.load("Sri_Lankan_Mask_2.3mf", force="mesh", process=False)
lo, hi = m.bounds

# grid over the plaque's X/Z (width/height) footprint
STEP = 1.0
xs = np.arange(lo[0] + 0.5, hi[0], STEP)
zs = np.arange(lo[2] + 0.5, hi[2], STEP)
XX, ZZ = np.meshgrid(xs, zs)
pts = np.column_stack([XX.ravel(), np.full(XX.size, lo[1] - 10.0), ZZ.ravel()])
dirs = np.tile([0.0, 1.0, 0.0], (len(pts), 1))

print(f"casting {len(pts)} rays ...")
locs, idx_ray, _ = m.ray.intersects_location(
    ray_origins=pts, ray_directions=dirs, multiple_hits=True)
print(f"{len(locs)} hits")

y_first = np.full(len(pts), np.nan)   # smallest Y crossing  (surface nearest -Y)
y_last = np.full(len(pts), np.nan)    # largest  Y crossing  (surface nearest +Y)
n_cross = np.zeros(len(pts), dtype=int)
order = np.argsort(idx_ray, kind="stable")
ri = idx_ray[order]
yv = locs[order, 1]
for r in np.unique(ri):
    sel = yv[ri == r]
    y_first[r] = sel.min()
    y_last[r] = sel.max()
    n_cross[r] = len(sel)

shape = XX.shape
Yf = y_first.reshape(shape)
Yl = y_last.reshape(shape)
NC = n_cross.reshape(shape)
T = Yl - Yf

hit = ~np.isnan(Yf)
print(f"\nrays that hit material: {hit.sum()} / {hit.size}")
print(f"crossing counts present: {sorted(set(n_cross[hit.ravel()].tolist()))}")
print(f"Y range of -Y surface : {np.nanmin(Yf):.2f} .. {np.nanmax(Yf):.2f}")
print(f"Y range of +Y surface : {np.nanmin(Yl):.2f} .. {np.nanmax(Yl):.2f}")
print(f"thickness  min/med/max: {np.nanmin(T):.2f} / {np.nanmedian(T):.2f} / {np.nanmax(T):.2f}")

fig, ax = plt.subplots(1, 4, figsize=(22, 7))
for a, data, title in [
    (ax[0], Yf, "-Y surface height (y)"),
    (ax[1], Yl, "+Y surface height (y)"),
    (ax[2], T, "material thickness (mm)"),
    (ax[3], NC.astype(float), "ray crossings"),
]:
    im = a.imshow(data, origin="lower",
                  extent=[xs[0], xs[-1], zs[0], zs[-1]], cmap="viridis")
    a.set_title(title)
    plt.colorbar(im, ax=a, shrink=0.75)
fig.tight_layout()
fig.savefig("back_analysis.png", dpi=90)
print("wrote back_analysis.png")

np.savez("mask_depth.npz", xs=xs, zs=zs, Yf=Yf, Yl=Yl, NC=NC)
