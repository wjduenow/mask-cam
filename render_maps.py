"""Big, readable orthographic maps of the mask front, so lens sites can be picked by eye.

Produces face_map.png: the front relief as a shaded height map with a labelled mm grid,
and the same for the region behind it, at a scale where the eyes/mouth are unambiguous.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource

d = np.load("pod.npz")
xs, zs, YF, YB, AVAIL = d["xs"], d["zs"], d["YF"], d["YB"], d["AVAIL"]
solid = d["solid"]

STANDOFF = np.where(solid, -YF, np.nan)

fig, ax = plt.subplots(1, 3, figsize=(26, 12))
ext = [xs[0], xs[-1], zs[0], zs[-1]]

ls = LightSource(azdeg=315, altdeg=45)
shade_in = np.nan_to_num(STANDOFF, nan=float(np.nanmin(STANDOFF)))
rgb = ls.shade(shade_in, cmap=plt.cm.bone, vert_exag=3.0, blend_mode="soft")
rgb[~solid] = 1.0
ax[0].imshow(rgb, origin="lower", extent=ext)
ax[0].set_title("FRONT relief, shaded (the face you see)", fontsize=13)

im = ax[1].imshow(STANDOFF, origin="lower", extent=ext, cmap="turbo")
ax[1].set_title("FRONT stand-off from wall plane (mm)", fontsize=13)
plt.colorbar(im, ax=ax[1], shrink=0.6)

A = np.where(np.isfinite(AVAIL) & (AVAIL > -100), AVAIL, np.nan)
im = ax[2].imshow(A, origin="lower", extent=ext, cmap="turbo", vmin=0, vmax=35)
ax[2].set_title("interior depth AVAILABLE for the bay (mm)\n"
                "= stand-off - 3 mm relief - 4 mm rim inset", fontsize=13)
plt.colorbar(im, ax=ax[2], shrink=0.6)

for a in ax:
    a.set_aspect("equal")
    a.set_xticks(np.arange(-55, 56, 5))
    a.set_yticks(np.arange(0, 111, 5))
    a.grid(True, lw=0.4, alpha=0.45, color="0.4")
    a.tick_params(labelsize=7)
    a.set_xlabel("x (mm)")
    a.set_ylabel("z (mm)")

fig.tight_layout()
fig.savefig("face_map.png", dpi=80)
print("wrote face_map.png")
