"""The bay as it now exists: every post, every boss, and the USB-C mount.

Written because for months none of them were in the mesh at all and nothing looked.  This
is the picture that would have shown it at a glance.
"""
import matplotlib
import numpy as np
import trimesh

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource

import mask_params as P

M = trimesh.load("mask_cam.stl", process=True)
S = 0.3
xs = np.arange(-38, 38, S)
zs = np.arange(12, 100, S)
XX, ZZ = np.meshgrid(xs, zs)
o = np.column_stack([XX.ravel(), np.full(XX.size, 60.0), ZZ.ravel()])
d = np.tile([0, -1.0, 0], (len(o), 1))
loc, idx, _ = M.ray.intersects_location(ray_origins=o, ray_directions=d,
                                        multiple_hits=False)
Y = np.full(len(o), np.nan); Y[idx] = loc[:, 1]
Y = Y.reshape(XX.shape)

fig, ax = plt.subplots(figsize=(9.5, 10))
ls = LightSource(azdeg=315, altdeg=45)
rgb = ls.shade(np.nan_to_num(Y, nan=-60.0), cmap=plt.get_cmap("bone"),
               vert_exag=3, blend_mode="soft", vmin=-52, vmax=-2.5)
rgb[np.isnan(Y)] = 1.0
ax.imshow(rgb, origin="lower", extent=(xs[0], xs[-1], zs[0], zs[-1]))


def ring(x, z, d_, **kw):
    t = np.linspace(0, 2 * np.pi, 64)
    ax.plot(x + d_ / 2 * np.cos(t), z + d_ / 2 * np.sin(t), **kw)


for x, z in P.POST_XY:
    ring(x, z, P.POST_OD, color="crimson", lw=1.4)
for x, z in P.POST_XY_BATT:
    if z < 100:
        ring(x, z, P.POST_OD_BATT, color="crimson", lw=1.4)
for sx in (-1, 1):
    for sz in (-1, 1):
        ring(P.BOARD_CX + sx * P.HOLE_DX / 2, P.BOARD_CZ + sz * P.HOLE_DY / 2,
             P.BOSS_OD, color="tab:orange", lw=1.4)
for s in (-1, 1):
    ring(s * P.EYE_X, P.EYE_Z, P.EYE_PUPIL_D, color="tab:blue", lw=1.2, ls="--")

ax.add_patch(plt.Rectangle((min(P.PWR_FACE_X, P.PWR_X_SLOT), P.PWR_SHELF_Z),
                           P.PWR_SLOT_T, P.PWR_W,
                           fill=False, ec="tab:green", lw=1.6))
ax.add_patch(plt.Rectangle((min(P.PWR_PORT_XA, P.PWR_PORT_XB), P.PWR_PORT_Z0),
                           P.PWR_PORT_T, P.PWR_SHELF_Z - P.PWR_PORT_Z0,
                           fill=False, ec="tab:green", lw=1.0, ls=":"))
# the SD card -- the thing that moved everything else
ax.add_patch(plt.Rectangle((min(P.SD_X, P.SD_SIDE * P.PCB_W / 2), P.SD_Z0),
                           P.SD_OUT, P.SD_Z1 - P.SD_Z0,
                           fill=False, ec="tab:red", lw=1.6))
ax.annotate("SD card, 7.6 mm proud\nof the board's edge",
            (P.SD_X + 3, (P.SD_Z0 + P.SD_Z1) / 2), xytext=(-36, 30), fontsize=8,
            color="tab:red", arrowprops=dict(arrowstyle="->", color="tab:red"))
ax.add_patch(plt.Rectangle((-P.PCB_W / 2, P.BOARD_CZ - P.PCB_L / 2), P.PCB_W, P.PCB_L,
                           fill=False, ec="tab:orange", lw=1.0, ls=":"))

ax.annotate("cover posts (9, red)", (21, 36), xytext=(26, 16), fontsize=8,
            color="crimson", arrowprops=dict(arrowstyle="->", color="crimson"))
ax.annotate("board bosses (4)", (12, 36), xytext=(-4, 14), fontsize=8,
            color="tab:orange", arrowprops=dict(arrowstyle="->", color="tab:orange"))
ax.annotate("DWEII module, on edge\nin its slot; plug enters\nfrom below (dotted)",
            (P.PWR_X_SLOT, P.PWR_SHELF_Z + 12), xytext=(26, 40),
            fontsize=8, color="tab:green",
            arrowprops=dict(arrowstyle="->", color="tab:green"))
ax.annotate("eye pupils — posts now\nclear them by 10.4 mm", (-P.EYE_X, P.EYE_Z),
            xytext=(-37, 84), fontsize=8, color="tab:blue",
            arrowprops=dict(arrowstyle="->", color="tab:blue"))
ax.set_title("the board bay, looking in from behind — everything that was missing",
             fontsize=11)
ax.set_xlabel("x (mm)"); ax.set_ylabel("z (mm)"); ax.set_aspect("equal")
fig.tight_layout()
fig.savefig("bay.png", dpi=110)
print("wrote bay.png")
