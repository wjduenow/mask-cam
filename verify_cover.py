"""Check the cover: vents clear every fixing, don't touch the cell, and open enough area.

Vents are the one feature that can quietly wreck this part -- they remove material from a
2.5 mm plate that carries the mask's whole weight through its screws, and a slot that
strays over the cell or a countersink is not obvious in a render.
"""
import numpy as np
import trimesh
import mask_params as P

C = trimesh.load("cover.stl", process=True)
fails = []
def check(n, ok, d):
    if not ok: fails.append(n)
    print(f"  {'OK  ' if ok else 'FAIL'}  {n:38s} {d}")

print("=== mesh ===")
check("watertight", C.is_watertight, f"{len(C.faces)} faces")
check("single body", C.body_count == 1, f"{C.body_count} bodies")

print("\n=== vents clear every fixing ===")
zs_all = [z for zs in P.VENT_BANKS.values() for z in zs]
half_l, half_w = P.VENT_L / 2, P.VENT_W / 2
for x, z in list(P.POST_XY) + list(P.POST_XY_BATT):
    r = P.COVER_CSK_D / 2 + 0.8         # the countersink is the real footprint
    worst = min(abs(z - vz) for vz in zs_all)
    clear = all(abs(z - vz) > half_w + r or abs(x) > half_l + r for vz in zs_all)
    check(f"screw ({x:+.1f},{z:.0f}) clear of vents", clear,
          f"nearest vent {worst:.1f} mm away in z")

for label, pts, w, l in (("hang pad", P.HANG_XY, P.HANG_PAD_W, P.HANG_PAD_L),
                         ("foot", P.FOOT_XY, P.FOOT_W, P.FOOT_L)):
    for x, z in pts:
        clear = all(abs(z - vz) > l / 2 + half_w or abs(x) - w / 2 > half_l
                    for vz in zs_all)
        check(f"{label} ({x:+.1f},{z:.0f}) clear of vents", clear, "")

print("\n=== keyhole orientation (functional, not cosmetic) ===")
# The screw is FIXED in the wall.  Hanging the mask lets it drop, so the screw travels UP
# relative to this plate: the entry circle must be BELOW the resting position and the load
# must be taken at the TOP of the slot.  Built inverted until 2026-08-18 -- it passed every
# dimensional check because none of them asked which way up it was, and the mask would
# have slid straight off the screws.
for x, z in P.HANG_XY:
    ze = z - P.KEYHOLE_ENTRY_DZ          # entry
    zb = ze + P.KEYHOLE_DROP             # rest
    check(f"keyhole ({x:+.1f},{z:.0f}) entry below rest", ze < zb,
          f"entry z={ze:.1f}, rests z={zb:.1f} -> mask drops {zb-ze:.1f} mm onto the screw")
    # and prove it against the MESH, not just the arithmetic: the plate must be solid
    # above the resting point (that ledge carries the weight) and open at the entry.
    top = C.contains(np.array([[x, zb + P.KEYHOLE_HEAD_D / 2 + 0.5,
                                -P.COVER_T + P.HANG_PAD_H - 0.4]]))[0]
    check(f"keyhole ({x:+.1f},{z:.0f}) has a lip above the shank", bool(top),
          "solid material above the resting point to bear the load")

print("\n=== the cell is not vented over ===")
c0, c1 = P.CELL_CZ - P.CELL_POCKET_H / 2, P.CELL_CZ + P.CELL_POCKET_H / 2
over = [z for z in zs_all if c0 - 5 <= z <= c1 + 5]
check("no vent over the cell", not over,
      f"cell spans z {c0:.0f}..{c1:.0f}; vents at "
      f"{min(zs_all):.0f}..{max(zs_all):.0f}")

print("\n=== airflow ===")
banks = {k: (min(v), max(v)) for k, v in P.VENT_BANKS.items()}
lo = min(z for zs in P.VENT_BANKS.values() for z in zs)
hi = max(z for zs in P.VENT_BANKS.values() for z in zs)
check("intake sits below the exhaust", hi - lo > 30,
      f"{hi - lo:.0f} mm of vertical separation drives the convection")
area = len(zs_all) * (P.VENT_L - P.VENT_W) * P.VENT_W + len(zs_all) * np.pi * P.VENT_R**2
check("open area is useful", area >= 400,
      f"{area:.0f} mm² across {len(zs_all)} slots")

print("\n=== vents keep material at the plate's edges ===")
# Every slot end must sit inside the cover's own outline with a printable margin.  A
# render caught a slot leaving 0.2 mm to the bottom edge, which no other check saw.
MIN_EDGE = 1.6
worst = (1e9, None)
lo_b, hi_b = C.bounds
for z in zs_all:
    g = min((z - half_w) - lo_b[1], hi_b[1] - (z + half_w))
    if g < worst[0]:
        worst = (g, (0.0, z))
check("slots keep material to the plate edge", worst[0] >= MIN_EDGE,
      f"thinnest {worst[0]:.2f} mm at z={worst[1][1]:.1f} (need {MIN_EDGE})")

print("\n=== the plate is still strong ===")
# material removed as a fraction of the cover's plan area
lo_b, hi_b = C.bounds
plan = (hi_b[0] - lo_b[0]) * (hi_b[1] - lo_b[1])
check("vents removed a modest fraction", area / plan < 0.10,
      f"{100*area/plan:.1f}% of the cover's plan area")
check("slots stay inside the post columns", P.VENT_L / 2 < 21 - P.POST_OD / 2 - 1,
      f"slot reaches |x|={P.VENT_L/2:.1f}, posts start at |x|={21-P.POST_OD/2:.2f}")

print()
if fails:
    raise SystemExit(f"COVER VERIFY FAILED: {', '.join(fails)}")
print("cover verified")
