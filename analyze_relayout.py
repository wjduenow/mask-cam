"""With a 75 mm ribbon the board is no longer tied to the lens.  What does that buy?

Three questions, answered from the measured surface rather than guessed:

  1. Can the board sit CLEAR of the camera in z, so the camera is serviceable without
     unbolting the board?  (The central column is only so tall.)
  2. If the board moves, does it get MORE interior depth than the current -16.23 floor?
  3. Where does 75 mm of ribbon actually go?
"""
import numpy as np
from measure import standoff_min_rect
import mask_params as P

FRONT_WALL, COVER_T = P.FRONT_WALL, P.COVER_T
BOARD_W, BOARD_H = P.PCB_W + 3.0, P.PCB_L + 3.0        # 33.4 x 41.4 with clearance
NEED_NOW = P.COMP_Z_MAX + P.J1_HANG + 1.0              # JST on the back, +air = 10.49

print(f"board footprint {BOARD_W} x {BOARD_H} mm, needs {NEED_NOW:.2f} mm of interior")
print(f"current: bay z {P.BAY_Z0_UP}..{P.BAY_Z1_UP}, floor {P.FLOOR_Y_UP:.2f}, "
      f"interior {P.INTERIOR_UP:.2f}\n")

print("=== 1. how tall is the usable central column? ===")
hw = BOARD_W / 2
for z in range(14, 104, 4):
    s = standoff_min_rect(-hw, hw, z - 2, z + 2)
    tag = "" if np.isfinite(s) else "  <- off mask"
    print(f"  z={z:3d}: worst standoff over x±{hw:.1f} = "
          + (f"{s:6.2f}  interior {s-FRONT_WALL-COVER_T:6.2f}{tag}"
             if np.isfinite(s) else "   --   OFF MASK"))

print("\n=== 2. best board placement (sliding the 41.4 mm board up the column) ===")
best = []
for z0 in np.arange(18.0, 60.0, 1.0):
    z1 = z0 + BOARD_H
    s = standoff_min_rect(-hw, hw, z0, z1)
    if not np.isfinite(s):
        continue
    best.append((s - FRONT_WALL - COVER_T, z0, z1, s))
best.sort(reverse=True)
print(f"  {'interior':>9}  {'board z span':>16}  {'worst standoff':>14}   clears camera z=52?")
for interior, z0, z1, s in best[:10]:
    clears = "YES" if (z0 > 52 + 6 or z1 < 52 - 6) else "no (overlaps the lens site)"
    print(f"  {interior:9.2f}  {z0:6.1f} .. {z1:6.1f}  {s:14.2f}   {clears}")

print("\n=== 3. can the board EVER clear the lens site at z=52? ===")
for gap in (5.0, 6.0, 8.0):
    z0 = 52 + gap
    z1 = z0 + BOARD_H
    s = standoff_min_rect(-hw, hw, z0, z1)
    print(f"  board above, {gap:.0f} mm clear: z {z0:.1f}..{z1:.1f} -> "
          + (f"standoff {s:.2f}, interior {s-FRONT_WALL-COVER_T:.2f}"
             if np.isfinite(s) else "RUNS OFF THE TOP OF THE MASK"))
    z1b = 52 - gap
    z0b = z1b - BOARD_H
    s2 = standoff_min_rect(-hw, hw, z0b, z1b)
    print(f"  board below, {gap:.0f} mm clear: z {z0b:.1f}..{z1b:.1f} -> "
          + (f"standoff {s2:.2f}, interior {s2-FRONT_WALL-COVER_T:.2f}"
             if np.isfinite(s2) else "RUNS OFF THE BOTTOM"))
