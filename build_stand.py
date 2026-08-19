"""stand.stl -- a desk/mantle stand, using the SAME keyhole interface as the wall screws.

THE IDEA.  The cover already presents three coplanar pads at y = 0 -- two keyhole pads at
z = 71 and a foot at z = 27 -- because it has to sit flat against a wall.  So the stand is
just "a pair of wall screws on a stick": an angled back panel carrying two mushroom pegs
at the keyhole spacing, on a base deep enough to beat the mask's forward centre of mass.

Hang it on a wall or drop it on this stand; the mask itself is identical either way, and
nothing extra bolts to it.

WHY 18°.  Measured: the mask's CoM sits 19.04 mm forward of its back plane and 48.76 mm
up (analyze_stand.py).  Leaning back moves that overhang toward the pivot --
19.04·cos θ − 48.76·sin θ -- which reaches zero at ~21°.  18° leaves the CoM just 2.4 mm
proud, killed by a base that reaches 55 mm forward, while still reading as a display
piece rather than something falling over backwards.

Printed FLAT ON ITS BACK PANEL: every overhang then faces up, the pegs grow out of the
bed-side face, and there is nothing to support.
"""
import math
import cadquery as cq
import trimesh

import mask_params as P

# The mask's real centre of mass, MEASURED from the built mesh -- not the 1x constants
# this file used to carry, which would size the base for a mask three times lighter.
_M = trimesh.load("mask_cam.stl", process=True)
COM_Y = -float(_M.center_mass[1])      # mm forward of the back plane
COM_Z = float(_M.center_mass[2])       # mm up from the bottom
MASK_G = _M.volume / 1000.0 * 1.24

# ---------------------------------------------------------------- parameters
TILT = 18.0             # degrees back from vertical
BASE_W = P.MASK_W * 0.94          # mm  x -- a little under the mask's 110.4 so it hides behind it
BASE_D = 0.0    # derived below           # mm  depth on the shelf; needs >= 13 mm past the CoM at 18°
BASE_T = 6.0            # mm  thick enough to be the ballast
PANEL_W = abs(P.HANG_XY[0][0]) * 2 + 24.0          # mm  wide enough to span both keyhole pads (22 mm apart)
PANEL_T = 6.0           # mm
PANEL_TOP_Z = P.HANG_XY[0][1] + 9.0      # mm  measured UP THE MASK's back from its bottom edge
GUSSET_T = 5.0          # mm

# ---- USB cable passthrough -------------------------------------------------------
# The mask's cable leaves the bottom of its own hollow, which lands on the base's top
# surface just in front of the panel.  Without a route out it would be pinched between
# the mask and the stand, so: a channel straight back through the base, and a notch in
# the panel's foot so the cable can turn into it.  Sized for a USB-C overmold, not the
# bare cable -- the plug is what has to pass.
CABLE_W = 14.0          # mm  clears a chunky USB-C overmold
CABLE_H = 8.0           # mm
CABLE_NOTCH_H = 12.0    # mm  how far up the panel the notch reaches

PEG_SHANK_D = P.KEYHOLE_SHANK_D - 0.35      # 3.85, slides in the Ø4.2 slot
PEG_HEAD_D = P.KEYHOLE_HEAD_D - 0.6         # 6.90, passes the Ø7.5 entry
PEG_HEAD_T = 2.2
PEG_SHANK_L = P.KEYHOLE_CAP_T + 0.3         # 2.5, clears the capturing lip

# the mask's own keyhole geometry -- imported, never retyped
PEG_X = [x for x, _ in P.HANG_XY]
# Where the shank ends up once the mask has dropped: entry is BELOW the pad centre,
# and the mask drops KEYHOLE_DROP, so the rest position is ABOVE the entry.
PEG_Z_ON_MASK = P.HANG_XY[0][1] - P.KEYHOLE_ENTRY_DZ + P.KEYHOLE_DROP
FOOT_Z_ON_MASK = P.FOOT_XY[0][1]

t = math.radians(TILT)
# CoM overhang once tilted back, then a base deep enough to bury it with margin
_OVERHANG = COM_Y * math.cos(t) - COM_Z * math.sin(t)
BASE_D = max(60.0, _OVERHANG + 45.0)


def build_stand():
    """Panel and pegs are assembled FLAT first, then tilted as one body.

    An earlier version positioned the pegs with hand-written trigonometry after the tilt
    and put them slightly off the panel face -- the mesh came out as three separate
    bodies, which verify_stand.py caught.  Assembling before rotating removes the trig.
    """
    # ---- base slab: front edge at y=0, back edge at y=-BASE_D
    base = (cq.Workplane("XY").rect(BASE_W, BASE_D).extrude(BASE_T)
            .edges("|Z").fillet(8.0)
            .translate((0, -BASE_D / 2, 0)))

    # ---- panel + pegs, built upright in a local frame: face at y=0 pointing +y,
    #      body behind it, base of the panel at z=0
    panel_len = PANEL_TOP_Z + 6.0
    asm = (cq.Workplane("XY").rect(PANEL_W, PANEL_T).extrude(panel_len)
           .translate((0, -PANEL_T / 2, 0))
           .edges("|Y").fillet(3.0))
    for px in PEG_X:
        peg = (cq.Workplane("XZ", origin=(0, 0, 0))
               .circle(PEG_SHANK_D / 2).extrude(-PEG_SHANK_L)
               .faces("<Y").workplane().circle(PEG_HEAD_D / 2).extrude(PEG_HEAD_T)
               .translate((px, 0, PEG_Z_ON_MASK)))
        asm = asm.union(peg)

    # tip the top toward -y (backwards): +TILT about +X sends (0,0,h) to (0,-h sin, h cos)
    asm = asm.rotate((0, 0, 0), (1, 0, 0), TILT)
    asm = asm.translate((0, -BASE_D + PANEL_T + 3.0, BASE_T - 1.0))
    stand = base.union(asm)

    # ---- cable passthrough: a channel out the back of the base, and a notch through
    #      the panel's foot so the cable can turn into it
    ch = (cq.Workplane("XY").rect(CABLE_W, BASE_D)
          .extrude(CABLE_H)
          .translate((0, -BASE_D / 2, BASE_T - CABLE_H))
          .edges("|Z").fillet(2.0))
    stand = stand.cut(ch)
    notch = (cq.Workplane("XY").rect(CABLE_W, PANEL_T * 3)
             .extrude(CABLE_NOTCH_H)
             .translate((0, -BASE_D + PANEL_T + 3.0, BASE_T - 1.0)))
    stand = stand.cut(notch)

    # ---- gussets: right triangles in the YZ plane, overlapping both base and panel
    gy = -BASE_D + PANEL_T + 3.0
    gz = BASE_T - 1.0
    for sx in (-1, 1):
        g = (cq.Workplane("YZ")
             .polyline([(gy, gz), (gy + BASE_D * 0.55, gz),
                        (gy - PANEL_TOP_Z * 0.55 * math.sin(t),
                         gz + PANEL_TOP_Z * 0.55 * math.cos(t))])
             .close().extrude(GUSSET_T)
             .translate((sx * (PANEL_W / 2) - (GUSSET_T if sx > 0 else 0), 0, 0)))
        stand = stand.union(g)
    return stand


if __name__ == "__main__":
    s = build_stand()
    cq.exporters.export(s, "stand.stl", tolerance=0.01, angularTolerance=0.1)
    bb = s.val().BoundingBox()
    com_off = _OVERHANG
    print(f"wrote stand.stl   {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} mm")
    print(f"  mask {MASK_G:.0f} g, CoM {COM_Y:.1f} fwd / {COM_Z:.1f} up")
    print(f"  tilt {TILT} deg -> CoM overhangs the pivot by {com_off:+.2f} mm")
    print(f"  base reaches {BASE_D:.0f} mm forward")
    print(f"  pegs at x = {PEG_X}, {PEG_Z_ON_MASK:.1f} mm up the mask's back")
