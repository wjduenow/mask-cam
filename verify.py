"""Measure the FINISHED mask_cam.stl and check it against what was intended.

check_clearances() in build_mask.py verifies the PLAN -- these numbers say a pocket
should stop 3 mm short of the relief.  This verifies the RESULT: it ray-casts the
exported mesh and measures what the booleans actually produced.  The two agreeing is
what makes the part safe to print.

Checks:
  1  mesh integrity: watertight, one body, unchanged silhouette
  2  the three apertures are genuinely open, at the right size and place
  3  the relief left in front of the bay is >= FRONT_WALL EVERYWHERE, not just at the
     one worst point the plan checked
  4  the bay interior is clear to the depth the board needs
  5  nothing protrudes past the wall plane
"""
import numpy as np
import trimesh

import mask_params as P
from mask_frame import load_mask

# process=True MERGES the duplicate vertices an STL necessarily stores per-triangle.
# Without it every triangle is its own island and the integrity checks below report
# 994720 bodies and "not watertight" for a mesh that is neither.
M = trimesh.load("mask_cam.stl", process=True)
D = load_mask(process=True)
fails = []


def check(name, ok, detail):
    fails.append(name) if not ok else None
    print(f"  {'OK  ' if ok else 'FAIL'}  {name:38s} {detail}")


print("=== 1. mesh integrity ===")
check("watertight", M.is_watertight, f"{len(M.faces)} faces")
check("single body", M.body_count == 1, f"{M.body_count} bodies")
check("winding consistent", M.is_winding_consistent, "")
lo, hi = M.bounds
dlo, dhi = D.bounds
check("bounding box == donor's",
      np.allclose(M.extents, D.extents, atol=1e-3),
      f"{np.round(M.extents,2).tolist()} vs {np.round(D.extents,2).tolist()}")
check("nothing past the wall plane", hi[1] <= 1e-6, f"max y = {hi[1]:.4f}")
# Bound it against the DONOR at the same scale, not against absolute numbers -- the
# design carves material out and adds a little back, so the ratio is what is meaningful
# and it survives any MASK_SCALE.
ratio = M.volume / D.volume
check("volume plausible vs the donor", 0.95 < ratio < 1.10,
      f"{M.volume/1000:.1f} cm³ vs donor {D.volume/1000:.1f} -> ratio {ratio:.3f}")


def cast(cx, cz, mesh=M):
    """Surface crossings along -Y at (cx, cz), REAR first (descending y).

    A ray fired from behind meets the rearmost surface first, so this order is
    rear -> front.  An earlier docstring claimed the opposite and the relief check below
    duly measured the REARMOST solid span instead of the front one -- reporting a 1.28 mm
    "relief" that was really a thin ledge near the cover, while the actual relief at that
    point was 8.12 mm.  Spans are [ys[i+1], ys[i]]; the FRONT one is the last.
    """
    o = np.array([[cx, 20.0, cz]])
    d = np.array([[0.0, -1.0, 0.0]])
    loc, _, _ = mesh.ray.intersects_location(ray_origins=o, ray_directions=d,
                                             multiple_hits=True)
    return np.sort(loc[:, 1])[::-1] if len(loc) else np.array([])


print("\n=== 2. the apertures are open ===")
for name, (cx, cz), dia in (("brow aperture", (P.LENS_X, P.LENS_Z), P.APERTURE_D),
                            ("left pupil", (-P.EYE_X, P.EYE_Z), P.EYE_PUPIL_D),
                            ("right pupil", (P.EYE_X, P.EYE_Z), P.EYE_PUPIL_D)):
    ys = cast(cx, cz)
    donor = cast(cx, cz, D)
    # the donor is solid here (2 crossings); an open bore shows the ray passing right
    # through to the bay, so the FRONT-most crossing must now be much deeper in
    open_now = len(ys) == 0 or (len(donor) and ys.max() - ys.min() > 5.0)
    check(f"{name} bored through",
          len(ys) < len(donor) or len(ys) == 0,
          f"donor had {len(donor)} crossings here, now {len(ys)}")
    # measure the actual hole diameter by scanning across it
    r = dia / 2
    xs_scan = np.arange(cx - r - 1.5, cx + r + 1.5, 0.1)
    openness = []
    for x in xs_scan:
        c = cast(x, cz)
        openness.append(len(c) < len(cast(x, cz, D)) or len(c) == 0)
    idx = np.where(openness)[0]
    meas = (xs_scan[idx[-1]] - xs_scan[idx[0]]) if len(idx) else 0.0
    check(f"{name} diameter", abs(meas - dia) < 0.6,
          f"measured {meas:.2f} mm across, drawn {dia} mm")

print("\n=== 3. relief left in front of the bay (the safety property) ===")
# THE property: at every (x, z) over the bay, how much SOLID material lies forward of the
# bay floor?  Measure it as the total solid length in y < floor, not as "the thickness of
# some span" -- a ray crossing a doubly-curved surface produces several spans plus
# sub-0.1 mm tessellation slivers where it grazes, and picking any single span by index
# measures the wrong one (an earlier version picked the REARMOST and reported a 1.28 mm
# ledge as the relief, when the real relief there was 8.12 mm).
SLIVER = 0.15           # ignore spans thinner than this: tessellation, not geometry


def solid_forward_of(ys, plane):
    """Total solid length at y < plane, from rear-first crossings."""
    total = 0.0
    for i in range(0, len(ys) - 1, 2):
        hi, lo = ys[i], ys[i + 1]          # a solid span [lo, hi]
        if hi <= plane:
            seg = hi - lo
        elif lo < plane:
            seg = plane - lo
        else:
            continue
        if seg > SLIVER:
            total += seg
    return total


worst = (1e9, None)
slivers = 0
for hw, z0, z1, floor in ((P.BAY_HW_UP, P.BAY_Z0_UP, P.BAY_Z1_UP, P.FLOOR_Y_UP),
                          (P.BAY_HW_LO, P.BAY_Z0_LO, P.BAY_Z1_LO, P.FLOOR_Y_LO)):
    for x in np.arange(-hw + 1, hw, 1.5):
        for z in np.arange(z0 + 1, z1, 1.5):
            if np.hypot(x - P.LENS_X, z - P.LENS_Z) < P.APERTURE_D / 2 + 1:
                continue
            if min(np.hypot(x + P.EYE_X, z - P.EYE_Z),
                   np.hypot(x - P.EYE_X, z - P.EYE_Z)) < P.EYE_PUPIL_D / 2 + 1:
                continue
            if (abs(x - P.LENS_X) < P.CAM_POCKET / 2 + 1
                    and abs(z - P.LENS_Z) < P.CAM_POCKET / 2 + 1):
                continue
            ys = cast(x, z)
            if len(ys) < 2:
                continue
            slivers += sum(1 for i in range(len(ys) - 1)
                           if 0.0 < ys[i] - ys[i + 1] <= SLIVER)
            t = solid_forward_of(ys, floor)
            if t < worst[0]:
                worst = (t, (x, z))
check("relief in front of the bay >= FRONT_WALL",
      worst[0] >= P.FRONT_WALL - 0.25,
      f"thinnest {worst[0]:.2f} mm at {np.round(worst[1], 1).tolist()} "
      f"(design min {P.FRONT_WALL}); {slivers} sub-{SLIVER} mm slivers ignored")

cworst = (1e9, None)
for x in np.arange(-P.CAM_POCKET / 2, P.CAM_POCKET / 2 + 0.01, 0.6):
    for z in np.arange(P.LENS_Z - P.CAM_POCKET / 2, P.LENS_Z + P.CAM_POCKET / 2, 0.6):
        if np.hypot(x - P.LENS_X, z - P.LENS_Z) < P.APERTURE_D / 2 + 0.6:
            continue
        ys = cast(x, z)
        if len(ys) < 2:
            continue
        t = solid_forward_of(ys, P.CAM_POCKET_Y)
        if t < cworst[0]:
            cworst = (t, (x, z))
check("camera pocket relief >= CAM_WALL",
      cworst[0] >= P.CAM_WALL - 0.25,
      f"thinnest {cworst[0]:.2f} mm at {np.round(cworst[1], 1).tolist()} "
      f"(design min {P.CAM_WALL})")

print("\n=== 4. the bay is clear for the board ===")
need = P.BOARD_STACK_T + P.BOARD_FRONT_CLR
bad = []
for x in np.arange(-P.PCB_W / 2 + 1, P.PCB_W / 2, 2.0):
    for z in np.arange(P.BOARD_CZ - P.PCB_L / 2 + 1, P.BOARD_CZ + P.PCB_L / 2, 2.0):
        # skip the four bosses, which are meant to be there
        if any(np.hypot(x - sx * P.HOLE_DX / 2, z - P.BOARD_CZ - sz * P.HOLE_DY / 2)
               < P.BOSS_OD / 2 + 0.5 for sx in (-1, 1) for sz in (-1, 1)):
            continue
        ys = cast(x, z)
        # first material rearward of the cover plane, looking forward from the cover
        blocking = ys[(ys < -P.COVER_T) & (ys > P.BOARD_BACK_Y - P.COMP_Z_MAX)]
        if len(blocking):
            bad.append((round(x, 1), round(z, 1), round(float(blocking.max()), 2)))
check("board envelope unobstructed", not bad,
      f"{len(bad)} obstructed sample(s)" + (f", e.g. {bad[:3]}" if bad else ""))

print("\n=== 5. the donor's own surface is untouched outside the bay ===")
# Sample the face well away from anything we cut, and confirm the front surface has not
# moved by so much as a micron.
same = True
# Sample points must FOLLOW MASK_SCALE and must genuinely lie off the bay -- hardcoded
# 1x points put (±20, 95) inside the widened waist at 1.75x, where the surface is
# supposed to differ.
from mask_frame import MASK_SCALE as _S
_PTS = [(-30, 40), (30, 40), (-40, 70), (40, 70), (-45, 55), (45, 55), (-38, 88)]
for x, z in [(px * _S, pz * _S) for px, pz in _PTS]:
    a, b = cast(x, z), cast(x, z, D)
    if len(a) == 0 and len(b) == 0:
        continue          # both miss: an existing hole in the donor (a tooth gap)
    # 1e-3 mm, not 1e-6: manifold's boolean perturbs untouched vertices by ~1e-6,
    # which is a millionth of a millimetre and far below any printer's resolution.
    if len(a) == 0 or len(b) == 0 or abs(a[0] - b[0]) > 1e-3:
        same = False
        print(f"        differs at ({x},{z}): {a[:1]} vs {b[:1]}")
check("front surface identical off-bay", same, f"{len(_PTS)} scaled sample points")

print()
if fails:
    raise SystemExit(f"VERIFY FAILED: {len(fails)} check(s) -- {', '.join(fails)}")
print("all checks passed — mask_cam.stl matches the design")
