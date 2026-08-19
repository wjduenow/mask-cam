"""mask_cam.stl -- the Gini Raksha mask, converted to carry an ESP32-S3-CAM.

What happens to the donor, in order:

  ADD   a two-zone rounded-rectangular bay tube on the mirror line, rising from inside
        the mask's material back to the rim plane; four cover posts; four board bosses.
        Everything added is INTERSECTED with the mask's own silhouette first, so no
        added feature can poke out and become visible from the front.

  CUT   the bay pocket (two floors), the cover rebate, the brow aperture and the camera
        pocket behind it, both eye pupils, every pilot hole, and the cable slot.

check_clearances() re-measures the mask's front surface from the sampled grid and
refuses to build if any pocket would come within less than its allowed wall of breaking
through the relief.  It is not decoration -- it caught two floors and a camera pocket
that a coarser hand-made table had said were fine.
"""
import numpy as np
import trimesh

import mask_params as P
from geom import (rrect_prism, extrude_y, cyl_y, union, difference,
                  intersection, silhouette_polygon, report)
from mask_frame import load_mask
from measure import standoff_min_rect, standoff_min_disc, rear_depth_max, root_y

EPS = 0.01
BACK = 3.0          # how far past the wall plane adders/cutters run, so no coplanar faces


# ───────────────────────────────────────────────────────────────── verification
def check_clearances():
    rows, ok = [], True

    def wall_check(name, standoff, cut_to, need):
        nonlocal ok
        have = standoff - cut_to
        good = have >= need - 1e-6
        ok &= good
        rows.append(f"  {'OK ' if good else 'FAIL'}  {name:33s} front {standoff:6.2f} "
                    f"proud, cut to {cut_to:6.2f} -> {have:5.2f} mm wall "
                    f"(need {need:.2f})")

    def fact(name, text):
        rows.append(f"  --    {name:33s} {text}")

    def must(name, cond, text):
        nonlocal ok
        ok &= cond
        rows.append(f"  {'OK ' if cond else 'FAIL'}  {name:33s} {text}")

    wall_check("bay floor UPPER -> relief",
               standoff_min_rect(-P.BAY_HW_UP, P.BAY_HW_UP, P.BAY_Z0_UP, P.BAY_Z1_UP),
               -P.FLOOR_Y_UP, P.FRONT_WALL)
    wall_check("bay floor LOWER -> relief",
               standoff_min_rect(-P.BAY_HW_LO, P.BAY_HW_LO, P.BAY_Z0_LO, P.BAY_Z1_LO),
               -P.FLOOR_Y_LO, P.FRONT_WALL)
    wall_check("camera pocket -> relief",
               standoff_min_rect(P.LENS_X - P.CAM_POCKET / 2, P.LENS_X + P.CAM_POCKET / 2,
                                 P.LENS_Z - P.CAM_POCKET / 2, P.LENS_Z + P.CAM_POCKET / 2),
               -P.CAM_POCKET_Y, P.CAM_WALL)
    wall_check("camera clamp seat -> relief",
               standoff_min_rect(-P.CAM_SEAT_HW, P.CAM_SEAT_HW,
                                 P.CAM_SEAT_Z0, P.CAM_SEAT_Z1_OPEN),
               -P.CAM_SEAT_Y, P.FRONT_WALL)
    must("the clamp seat stays inside its own zone",
         P.CAM_SEAT_Z1_OPEN <= P.BAY_Z1_MID,
         f"seat ends at z={P.CAM_SEAT_Z1_OPEN:.1f}, the waist ends at "
         f"z={P.BAY_Z1_MID:.1f} -- past that the seat is a sealed void 20 mm inside "
         f"the mask, and so is anything cut into it")
    must("cell pocket fits the battery zone",
         P.CELL_POCKET_W <= 2 * P.BAY_HW_BATT
         and P.CELL_POCKET_H <= P.BAY_Z1_BATT - P.BAY_Z0_BATT
         and P.CELL_T + 1.0 <= P.INTERIOR_BATT,
         f"{P.CELL_POCKET_W:.0f} x {P.CELL_POCKET_H:.0f} x {P.CELL_T + 1:.0f} in a zone "
         f"{2*P.BAY_HW_BATT:.0f} x {P.BAY_Z1_BATT-P.BAY_Z0_BATT:.0f} x {P.INTERIOR_BATT:.2f}")
    must("camera clear of the board (serviceable)",
         P.LENS_Z > P.BOARD_CZ + P.PCB_L_OVERALL / 2 + 4,
         f"lens z={P.LENS_Z:.0f}, board ends at "
         f"z={P.BOARD_CZ + P.PCB_L_OVERALL/2:.0f}")
    wall_check("brow aperture bore -> relief",
               standoff_min_disc(P.LENS_X, P.LENS_Z, P.APERTURE_D / 2),
               -P.CAM_POCKET_Y, P.CAM_WALL)
    for pz in P.CAM_MOUNT_Z:
        wall_check(f"clamp pilot z={pz:.0f} -> relief",
                   standoff_min_disc(P.LENS_X, pz, 1.5),
                   -P.CAM_SEAT_Y + P.CAM_MOUNT_DEPTH, 1.5)
        must(f"clamp pilot z={pz:.0f} is reachable",
             P.CAM_SEAT_Z0 < pz < P.CAM_SEAT_Z1_OPEN
             and not (P.LENS_Z - P.CAM_POCKET/2 < pz < P.LENS_Z + P.CAM_POCKET/2),
             f"a pilot outside the open seat, or inside the pocket, is one you cannot "
             f"put a screwdriver on")

    must("camera seat clears the board bosses",
         P.CAM_SEAT_HW + 0.5 <= P.HOLE_DX / 2 - P.BOSS_OD / 2,
         f"seat reaches |x|={P.CAM_SEAT_HW:.1f}, bosses start at "
         f"|x|={P.HOLE_DX/2 - P.BOSS_OD/2:.1f}")
    must("room for the camera module",
         P.CAM_SEAT_Y - P.CAM_POCKET_Y >= P.CAM_MODULE_MEASURED,
         f"pocket offers {P.CAM_SEAT_Y - P.CAM_POCKET_Y:.2f} mm, measured module is "
         f"{P.CAM_MODULE_MEASURED:.2f} mm")
    must("clamp finishes flush with the bay floor",
         P.CAM_CLAMP_T <= P.CAM_SEAT_DEPTH,
         f"clamp {P.CAM_CLAMP_T} mm in a {P.CAM_SEAT_DEPTH} mm seat")

    need = P.BOARD_STACK_T + P.BOARD_FRONT_CLR
    must("board stack in the upper bay", P.INTERIOR_UP >= need,
         f"interior {P.INTERIOR_UP:5.2f} mm vs board+air {need:5.2f} -> "
         f"{P.INTERIOR_UP - need:+5.2f} spare")
    must("board width in the upper bay", 2 * P.BAY_HW_UP >= P.PCB_W + 1.6,
         f"opening {2*P.BAY_HW_UP:.1f} mm vs PCB {P.PCB_W} -> "
         f"{(2*P.BAY_HW_UP - P.PCB_W)/2:.2f} mm per side")
    # use the OVERALL length (incl. the USB-C shell) so the cavity clears the connector
    must("board height inside the bay",
         P.BOARD_CZ - P.PCB_L_OVERALL / 2 >= P.BAY_Z0_UP + 1 and
         P.BOARD_CZ + P.PCB_L_OVERALL / 2 <= P.BAY_Z1_UP - 1,
         f"board+USB-C spans z {P.BOARD_CZ-P.PCB_L_OVERALL/2:.1f}.."
         f"{P.BOARD_CZ+P.PCB_L_OVERALL/2:.1f} "
         f"in a bay of {P.BAY_Z0_UP:.0f}..{P.BAY_Z1_UP:.0f}")

    must("boss tops meet the PCB's seating face",
         abs(P.BOSS_H - (P.BOARD_SEAT_Y - P.FLOOR_Y_UP)) < 1e-9,
         f"boss top y={P.BOARD_SEAT_Y:6.2f} = PCB front face; back face is "
         f"{P.BOARD_BACK_Y:6.2f}, {P.PCB_T} mm behind it")
    must("board screw gets enough bite",
         P.BOARD_SCREW_LEN - P.PCB_T <= P.BOSS_H,
         f"M3×{P.BOARD_SCREW_LEN:.0f} through {P.PCB_T} mm of PCB leaves "
         f"{P.BOARD_SCREW_LEN - P.PCB_T:.2f} mm in a {P.BOSS_H:.2f} mm boss")

    must("power module fits the waist behind the camera",
         P.PWR_W + 2 * P.PWR_CLR <= 2 * P.BAY_HW_MID
         and P.PWR_H + 2 * P.PWR_CLR <= P.BAY_Z1_MID - P.BAY_Z0_MID
         and P.PWR_T <= -P.COVER_T - P.CAM_SEAT_Y,
         f"{P.PWR_W} x {P.PWR_H} x {P.PWR_T} in a waist "
         f"{2*P.BAY_HW_MID:.0f} x {P.BAY_Z1_MID-P.BAY_Z0_MID:.0f} with "
         f"{-P.COVER_T - P.CAM_SEAT_Y:.1f} mm behind the camera clamp")

    rear = P.BOARD_BACK_Y + P.REAR_PROTRUSION
    must("board rear parts -> cover", rear <= -P.COVER_T - 0.5,
         f"board reaches y={rear:6.2f}, cover inner face {-P.COVER_T:6.2f} -> "
         f"{-P.COVER_T - rear:5.2f} mm")
    worst = P.BOARD_BACK_Y + P.J2_HANG
    fact("...and if J2 were populated too",
         f"would reach y={worst:6.2f} -> {-P.COVER_T - worst:5.2f} mm "
         f"({'still clears' if worst <= -P.COVER_T else 'FOULS THE COVER'})")
    must("ribbon plenum under the board", P.BOARD_FRONT_CLR >= 2.0,
         f"{P.BOARD_FRONT_CLR:.1f} mm x {P.PCB_W} x {P.PCB_L} for the 75 mm FPC to fold "
         f"(~57 mm of excess)")

    fov_lo = 2 * np.degrees(np.arctan((P.APERTURE_D / 2) / P.LENS_SETBACK_MAX))
    fov_hi = 2 * np.degrees(np.arctan((P.APERTURE_D / 2) / P.LENS_SETBACK_MIN))
    fact("brow aperture / field of view",
         f"Ø{P.APERTURE_D} at z={P.LENS_Z:.0f}, lens {P.LENS_SETBACK_MAX:.1f} mm back "
         f"if flat-faced, {P.LENS_SETBACK_MIN:.1f} if barrelled "
         f"-> {fov_lo:.0f}°..{fov_hi:.0f}° cone")

    if P.EYE_PUPILS:
        rim = P.EYE_DOME_R - P.EYE_PUPIL_D / 2
        must("eyeball rim around the pupil", rim >= 0.8,
             f"{rim:.2f} mm of eyeball left (need >= 0.80 to print)")

    for x, z, od in ([(x, z, P.POST_OD) for x, z in P.POST_XY]
                     + [(x, z, P.POST_OD_BATT) for x, z in P.POST_XY_BATT]):
        hw, _, _, _, nm = P.zone_of(z)
        must(f"cover post ({x:+.1f},{z:.0f}) inside the {nm} zone",
             abs(x) + od / 2 <= hw,
             f"|x|+r = {abs(x)+od/2:.2f} vs half-width {hw:.1f}")
    for x, z in P.POST_XY_BATT:
        must(f"batt post ({x:+.1f},{z:.0f}) clear of the cell",
             abs(x) - P.POST_OD_BATT / 2 >= P.CELL_POCKET_W / 2,
             f"post inner edge {abs(x)-P.POST_OD_BATT/2:.2f} vs cell pocket "
             f"{P.CELL_POCKET_W/2:.1f}")

    # 2-D clearance, not just z: at 1.5x the board zone is wide enough to run the post
    # columns BESIDE the board rather than above and below it, which a z-only test
    # rejected out of hand.
    bz0, bz1 = P.BOARD_CZ - P.PCB_L_OVERALL / 2, P.BOARD_CZ + P.PCB_L_OVERALL / 2
    bx0, bx1 = P.BOARD_CX - P.PCB_W / 2, P.BOARD_CX + P.PCB_W / 2
    for x, z in list(P.POST_XY) + list(P.POST_XY_BATT):
        r = P.POST_OD / 2 + 1.0
        clear = (x + r < bx0 or x - r > bx1 or z + r < bz0 or z - r > bz1)
        must(f"cover post ({x:+.1f},{z:.0f}) clear of board", clear,
             f"post x {x-r:.1f}..{x+r:.1f} z {z-r:.1f}..{z+r:.1f} vs board "
             f"x {bx0:.1f}..{bx1:.1f} z {bz0:.1f}..{bz1:.1f}")

    # Every pillar must reach material.  The donor's rear surface is a dish, so a pillar
    # based on the bay-floor PLANE floats over most of the bay; each one is therefore
    # extended forward to its own local limit and that extension is verified here.
    pillars = ([(x, z, P.POST_OD / 2, "post") for x, z in P.POST_XY]
               + [(P.BOARD_CX + sx * P.HOLE_DX / 2, P.BOARD_CZ + sz * P.HOLE_DY / 2,
                   P.BOSS_OD / 2, "boss")
                  for sx in (-1, 1) for sz in (-1, 1)])
    for x, z, r, kind in pillars:
        base = root_y(x, z, r, P.FRONT_WALL)
        rear = rear_depth_max(x, z, r)
        must(f"{kind} ({x:+.1f},{z:.0f}) reaches material",
             -base >= rear - 1e-6,
             f"rooted at y={base:6.2f}, donor's rear surface at y={-rear:6.2f}"
             + (f", {(-base)-rear:.2f} mm proud" if -base > rear else ""))

    print("\n".join(rows))
    if not ok:
        raise SystemExit("\nclearance check FAILED -- fix mask_params.py, do not print")
    print()


# ───────────────────────────────────────────────────────────────── added solids
def build_additions(sil_poly):
    w = P.BAY_WALL
    # One tube segment per zone, each overlapping its neighbours in z so the steps
    # between them close into a single solid rather than four stacked boxes.
    tube = union([
        rrect_prism(-hw - w, hw + w, z0 - (w if i == 0 else 4.0),
                    z1 + (w if i == len(P.ZONES) - 1 else 4.0),
                    P.BAY_CORNER_R + w, fl, BACK)
        for i, (hw, z0, z1, fl, _) in enumerate(P.ZONES)
    ])

    posts, ribs = [], []
    for x, z, od in ([(x, z, P.POST_OD) for x, z in P.POST_XY]
                     + [(x, z, P.POST_OD_BATT) for x, z in P.POST_XY_BATT]):
        base = root_y(x, z, od / 2)
        posts.append(cyl_y(x, z, od, base, -P.COVER_T, P.SEG))
        hw, _, _, fl, _ = P.zone_of(z)
        sgn = 1.0 if x >= 0 else -1.0
        x_in, x_out = sorted((x, sgn * (hw + P.BAY_WALL)))
        if abs(x_out - x_in) > 0.5:
            ribs.append(rrect_prism(x_in, x_out, z - P.POST_RIB / 2, z + P.POST_RIB / 2,
                                    0.0, max(base, fl), -P.COVER_T))

    bosses = []
    for sx in (-1, 1):
        for sz in (-1, 1):
            bx = P.BOARD_CX + sx * P.HOLE_DX / 2
            bz = P.BOARD_CZ + sz * P.HOLE_DY / 2
            bosses.append(cyl_y(bx, bz, P.BOSS_OD, root_y(bx, bz, P.BOSS_OD / 2),
                                P.BOARD_SEAT_Y, P.SEG))

    add = union([tube] + posts + ribs + bosses)
    clip = extrude_y(sil_poly, min(f for _, _, _, f, _ in P.ZONES) - 5.0, BACK + 1.0)
    return intersection([add, clip])


# ───────────────────────────────────────────────────────────────── cutters
def build_cuts():
    cuts = []
    # one pocket per zone, z ranges overlapping so each step is a single clean face
    for i, (hw, z0, z1, fl, _) in enumerate(P.ZONES):
        cuts.append(rrect_prism(-hw, hw, z0 - (0 if i == 0 else EPS),
                                z1 + (0 if i == len(P.ZONES) - 1 else EPS),
                                P.BAY_CORNER_R, fl, BACK))
    # the cell pocket: deeper than the battery zone's floor by the cell's own thickness
    cuts.append(rrect_prism(-P.CELL_POCKET_W / 2, P.CELL_POCKET_W / 2,
                            P.CELL_CZ - P.CELL_POCKET_H / 2,
                            P.CELL_CZ + P.CELL_POCKET_H / 2,
                            8.0, P.FLOOR_Y_BATT, BACK))

    # cover rebate: the opening plus lip and clearance, from the cover's inner face back
    lip = P.COVER_LIP + P.COVER_CLR
    for i, (hw, z0, z1, fl, _) in enumerate(P.ZONES):
        cuts.append(rrect_prism(-hw - lip, hw + lip,
                                z0 - (lip if i == 0 else EPS),
                                z1 + (lip if i == len(P.ZONES) - 1 else EPS),
                                P.COVER_CORNER_R, -P.COVER_T, BACK))

    # the brow aperture: one cylinder, camera pocket -> straight out through the relief
    cuts.append(cyl_y(P.LENS_X, P.LENS_Z, P.APERTURE_D,
                      -(P.LENS_SITE_STANDOFF + 2.0), P.CAM_POCKET_Y + EPS, P.SEG))
    # the camera pocket behind it, and the seat the clamp lies flush in
    cuts.append(rrect_prism(P.LENS_X - P.CAM_POCKET / 2, P.LENS_X + P.CAM_POCKET / 2,
                            P.LENS_Z - P.CAM_POCKET / 2, P.LENS_Z + P.CAM_POCKET / 2,
                            P.CAM_POCKET_R, P.CAM_POCKET_Y, P.CAM_SEAT_Y + EPS))
    cuts.append(rrect_prism(-P.CAM_SEAT_HW, P.CAM_SEAT_HW,
                            P.CAM_SEAT_Z0, P.CAM_SEAT_Z1_OPEN, P.CAM_SEAT_R,
                            P.CAM_SEAT_Y, P.FLOOR_Y_MID + EPS))
    # pilot for the camera clamp.  ONE, below the pocket: the waist ends at z=97 and the
    # pocket reaches 96.1, so there is no second place to put one that a screwdriver can
    # reach.  Cutting one at z=99 anyway just buried it -- see CAM_SEAT_Z1_OPEN.
    for pz in P.CAM_MOUNT_Z:
        cuts.append(cyl_y(P.LENS_X, pz, P.CAM_MOUNT_PILOT,
                          P.CAM_SEAT_Y - P.CAM_MOUNT_DEPTH, P.CAM_SEAT_Y + EPS, 48))

    # the eye pupils -- cosmetic, blanked by printed plugs
    if P.EYE_PUPILS:
        for s in (-1, 1):
            cuts.append(cyl_y(s * P.EYE_X, P.EYE_Z, P.EYE_PUPIL_D,
                              -(P.EYE_STANDOFF + 2.0), P.FLOOR_Y_UP + EPS, P.SEG))

    # pilots
    for x, z in list(P.POST_XY) + list(P.POST_XY_BATT):
        cuts.append(cyl_y(x, z, P.POST_PILOT, -P.COVER_T - P.COVER_SCREW_LEN,
                          -P.COVER_T + EPS, 48))
    for sx in (-1, 1):
        for sz in (-1, 1):
            cuts.append(cyl_y(P.BOARD_CX + sx * P.HOLE_DX / 2,
                              P.BOARD_CZ + sz * P.HOLE_DY / 2,
                              P.BOSS_PILOT, P.BOARD_SEAT_Y - P.BOARD_SCREW_LEN,
                              P.BOARD_SEAT_Y + EPS, 48))

    # Cable exit: a slot through the BOARD zone's lower wall, so the USB-C lead reaches
    # the power module in the waist by running up inside the bay, and leaves through the
    # mask's own hollow at the bottom.  No connector is exposed on the outside.
    cuts.append(rrect_prism(-P.CABLE_SLOT_W / 2, P.CABLE_SLOT_W / 2,
                            P.BAY_Z0_UP - P.BAY_WALL - 2.0, P.BAY_Z0_UP + EPS, 1.5,
                            P.FLOOR_Y_UP, P.FLOOR_Y_UP + P.CABLE_SLOT_H))
    return cuts


def main():
    print("=== derived geometry ===")
    print(P.summary())
    print("\n=== clearance checks (re-measured from the mesh) ===")
    check_clearances()

    print("=== build ===")
    mask = report("donor mask", load_mask())

    grid = np.load("pod.npz")
    sil = silhouette_polygon(grid["outline"], grid["xs"], grid["zs"], shrink=0.8)
    print(f"  silhouette clip: {sil.area:.0f} mm^2, {len(sil.exterior.coords)} pts")

    add = report("additions", build_additions(sil))
    m = report("mask + additions", union([mask, add]))
    m = report("after cuts", difference(m, build_cuts()))

    # Everything added ran BACK past the wall plane so no cutter would ever end up
    # coplanar with a face it was trimming.  Shave the overshoot off flush: the mask's
    # own rear-most point is already y=0, so this removes nothing of the donor, and it
    # guarantees the promise that nothing protrudes past the wall.
    lo, hi = m.bounds
    trim = rrect_prism(lo[0] - 5, hi[0] + 5, lo[2] - 5, hi[2] + 5, 0.0, 0.0, BACK + 5.0)
    m = report("trimmed to the wall", difference(m, [trim]))

    if not m.is_watertight:
        raise SystemExit("result is NOT watertight -- do not print")
    if m.body_count != 1:
        print(f"  ⚠ {m.body_count} bodies -- check for orphaned islands before printing")

    m.export("mask_cam.stl")
    lo, hi = m.bounds
    print(f"\nwrote mask_cam.stl   bbox {(hi-lo).round(2)}   "
          f"{m.volume/1000:.1f} cm^3  (~{m.volume/1000*1.24:.0f} g PLA)")


if __name__ == "__main__":
    main()
