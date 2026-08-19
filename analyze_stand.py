"""Freestanding: what does a stand actually have to do?

The mask is a wall plaque -- flat back, all its mass bulging FORWARD of that plane.  Sat
upright on a shelf it tips forward.  So measure the real centre of mass and work out how
far a foot must reach, and how far back it must lean.
"""
import numpy as np
from mask_frame import load_mask
import mask_params as P
import trimesh

M = trimesh.load("mask_cam.stl", process=True)
com = M.center_mass
lo, hi = M.bounds
print(f"mask bbox {np.round(M.extents,2).tolist()}   volume {M.volume/1000:.1f} cm3 "
      f"(~{M.volume/1000*1.24:.0f} g PLA)")
print(f"centre of mass  x={com[0]:6.2f}  y={com[1]:6.2f}  z={com[2]:6.2f}")
print(f"  -> CoM sits {-com[1]:.2f} mm FORWARD of the back plane (y=0)")
print(f"  -> and {com[2]:.2f} mm up from the bottom")

print("\n=== sat upright on its back edge, how far forward does it want to fall? ===")
print(f"  tipping axis is the back plane's bottom edge; the CoM overhangs it by "
      f"{-com[1]:.2f} mm")
print(f"  a foot must therefore reach at least {-com[1]:.2f} mm forward, plus margin")

print("\n=== leaning back on a stand: tilt vs how far the foot must reach ===")
print(f"  {'tilt':>6}  {'CoM horiz. offset':>18}  {'foot reach needed':>18}")
for deg in (0, 5, 10, 15, 20, 25):
    t = np.radians(deg)
    # rotate the mask back by `deg` about the bottom edge; CoM horizontal offset from
    # the back plane's contact line
    off = -com[1] * np.cos(t) - com[2] * np.sin(t)
    print(f"  {deg:5.0f}°  {off:18.2f}  {max(0.0, off) + 12:18.2f}"
          + ("   <- CoM behind the pivot: stable" if off <= 0 else ""))

print("\n=== what is the mask's bottom edge actually like? ===")
d = np.load("pod.npz")
xs, zs, YF, solid = d["xs"], d["zs"], d["YF"], d["solid"]
for z in (0.5, 1.5, 3.0, 5.0, 8.0):
    i = int(np.argmin(np.abs(zs - z)))
    row = solid[i]
    if not row.any():
        print(f"  z={z:4.1f}: no material")
        continue
    w = xs[row]
    print(f"  z={z:4.1f}: material from x={w.min():6.1f} to {w.max():6.1f} "
          f"({row.sum()*0.5:.1f} mm of it), front reaches y={np.nanmin(YF[i]):7.2f}")
