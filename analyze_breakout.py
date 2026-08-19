"""Where does the SparkFun-pattern USB-C breakout go, using the jukebox's measured dims?"""
import numpy as np
from measure import standoff_min_rect, rear_depth_max
import mask_params as P

UC_H, UC_D, UC_T = 21.4, 14.5, 4.75      # measured in ../sonos-nest/hardware/jukebox-7
bay_x, bay_z, bay_y = 2*P.BAY_HW_LO, P.BAY_Z1_LO-P.BAY_Z0_LO, P.INTERIOR_LO
print(f"lower bay: {bay_x:.0f} (x) x {bay_z:.0f} (z) x {bay_y:.1f} (y)\n")

print("receptacle must point -z (down at the cable exit), so UC_D lies along z:")
for name, (dx, dz, dy) in {
    "flat, 21.4 across x": (UC_H, UC_D, UC_T),
    "on edge, 21.4 into depth": (UC_T, UC_D, UC_H),
}.items():
    fits = dx <= bay_x and dz <= bay_z and dy <= bay_y
    note = "" if fits else f"  z short by {dz-bay_z:.1f}" if dz > bay_z else f"  y short by {dy-bay_y:.1f}"
    print(f"  {name:28s} {dx:5.2f} x {dz:5.2f} x {dy:5.2f}  {'FITS' if fits else 'NO'}{note}")

print("\n...but the jukebox NESTS the receptacle into the wall.  The bay's lower wall is")
print(f"{P.BAY_WALL} mm thick (z {P.BAY_Z0_LO-P.BAY_WALL:.1f}..{P.BAY_Z0_LO:.1f}), so the mouth can sit at its outer face:")
mouth = P.BAY_Z0_LO - P.BAY_WALL
print(f"  mouth at z={mouth:.1f} -> board rear edge at z={mouth+UC_D:.1f}, bay top is {P.BAY_Z1_LO:.0f}"
      f"  -> {P.BAY_Z1_LO-(mouth+UC_D):+.1f} mm")

print("\n=== the mask's own hollow BELOW the bay -- an alternative home ===")
for z0, z1 in ((8, 22), (10, 22), (6, 20), (12, 24)):
    for hw in (11, 13):
        s = standoff_min_rect(-hw, hw, z0, z1)
        r = max(rear_depth_max(x, (z0+z1)/2, 1.0) for x in (-hw+2, 0, hw-2))
        if not np.isfinite(s):
            continue
        print(f"  x±{hw} z {z0}..{z1}: front stands {s:6.2f} proud, "
              f"rear surface at y={-r:7.2f} -> {r - 3.0:5.2f} mm of open cavity behind the relief")

print("\n=== cover posts vs a breakout lying FLAT (21.4 across x, z from the wall) ===")
b_x0, b_x1 = -UC_H/2, UC_H/2
b_z0, b_z1 = mouth, mouth + UC_D
print(f"  breakout footprint  x {b_x0:.1f}..{b_x1:.1f}   z {b_z0:.1f}..{b_z1:.1f}")
for x, z in P.POST_XY:
    if z > 40: continue
    r = P.POST_OD/2
    hit = not (x+r < b_x0 or x-r > b_x1 or z+r < b_z0 or z-r > b_z1)
    print(f"  post ({x:+.1f},{z:.0f}) spans x {x-r:.2f}..{x+r:.2f} z {z-r:.2f}..{z+r:.2f}"
          f"  -> {'COLLIDES' if hit else 'clear'}")
