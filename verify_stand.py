"""Does the mask actually sit on the stand, and does the assembly stay up?"""
import math
import numpy as np
import trimesh
import build_stand as S
import mask_params as P

st = trimesh.load("stand.stl", process=True)
mk = trimesh.load("mask_cam.stl", process=True)
fails = []
def check(n, ok, d):
    if not ok: fails.append(n)
    print(f"  {'OK  ' if ok else 'FAIL'}  {n:36s} {d}")

print("=== stand mesh ===")
check("watertight", st.is_watertight, f"{len(st.faces)} faces")
check("single body", st.body_count == 1, f"{st.body_count} bodies")
lo, hi = st.bounds
# Bound against a real bed, not the 1x stand's size.  256 mm is the common 
# Bambu/Prusa-class bed; the stand must lie on it in some orientation.
BED = 256.0
check("fits a 256 mm bed", max(st.extents[0], st.extents[1]) <= BED and st.extents[2] <= BED,
      f"{np.round(st.extents,1).tolist()} mm")

print("\n=== pegs vs the cover's keyholes ===")
check("peg shank passes the slot", S.PEG_SHANK_D < P.KEYHOLE_SHANK_D,
      f"Ø{S.PEG_SHANK_D:.2f} in a Ø{P.KEYHOLE_SHANK_D} slot "
      f"({P.KEYHOLE_SHANK_D-S.PEG_SHANK_D:.2f} mm play)")
check("peg head passes the entry", S.PEG_HEAD_D < P.KEYHOLE_HEAD_D,
      f"Ø{S.PEG_HEAD_D:.2f} through a Ø{P.KEYHOLE_HEAD_D} entry")
check("peg head cannot pull back through the slot",
      S.PEG_HEAD_D > P.KEYHOLE_SHANK_D + 1.0,
      f"head Ø{S.PEG_HEAD_D:.2f} vs slot Ø{P.KEYHOLE_SHANK_D} -> "
      f"{(S.PEG_HEAD_D-P.KEYHOLE_SHANK_D)/2:.2f} mm of capture per side")
peg_stack = S.PEG_SHANK_L + S.PEG_HEAD_T
check("peg fits the pad's cavity depth", peg_stack <= P.HANG_PAD_H - 0.2,
      f"peg {peg_stack:.2f} mm into a {P.HANG_PAD_H} mm pad")
check("spacing matches the cover", sorted(S.PEG_X) == sorted(x for x,_ in P.HANG_XY),
      f"pegs at x={S.PEG_X}, pads at x={[x for x,_ in P.HANG_XY]}")

print("\n=== stability, mask + stand together ===")
t = math.radians(S.TILT)
m_mass = mk.volume * 1.24e-3          # g, PLA
s_mass = st.volume * 1.24e-3
# mask CoM, rotated back by TILT about the base's back edge, measured forward of it
m_off = S._OVERHANG          # measured from the built mask, not 1x constants
s_off = -(S.BASE_D - st.center_mass[1] - S.BASE_D)     # stand CoM forward of its back edge
s_off = st.center_mass[1] + S.BASE_D
combined = (m_mass * m_off + s_mass * s_off) / (m_mass + s_mass)
print(f"  mask {m_mass:.0f} g at {m_off:+.2f} mm forward of the pivot")
print(f"  stand {s_mass:.0f} g at {s_off:+.2f} mm")
check("combined CoM sits over the base",
      0 <= combined <= S.BASE_D, f"{combined:.2f} mm forward, base spans 0..{S.BASE_D:.0f}")
check("tipping margin is generous", S.BASE_D - combined >= 20,
      f"{S.BASE_D - combined:.1f} mm of base ahead of the combined CoM")

print()
if fails:
    raise SystemExit(f"STAND VERIFY FAILED: {', '.join(fails)}")
print("stand verified")
