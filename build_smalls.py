"""The small parts: camera clamp, battery shim, depth shims, eye plugs.

All exported flat, in print orientation, thickness along Z.

WHY SEPARATE PARTS AT ALL.  The camera module's dimensions are the one input to this
whole design that could not be verified (the vendor STEP does not model it and no
mechanical drawing exists for the bundled mini-CCM).  Putting the module's retention in
a 1 cm³ part means a wrong guess costs an eight-minute reprint of THIS, and never the
79 g mask.  The battery shim is the same insurance for the pouch, and the depth shims
for the module's depth: if your module is shorter than the 6.2 mm measured, stack shims
behind it to push the lens up the aperture bore -- which also widens the field of view.

⚠ EVERY DIMENSION HERE IS CUT TO THE MASK THAT IS ALREADY PRINTED, not to the mask the
parameters describe.  The two differ in one place that matters: the clamp seat is
specified z 80..102 but the battery zone's floor crosses it at z=97, so the reachable
seat is 17.0 mm long, not 22.0, and it carries ONE pilot, not two.  See
CAM_SEAT_Z1_OPEN / CAM_MOUNT_Z in mask_params, and verify_smalls.py, which re-measures
all of it off mask_cam.stl rather than trusting this comment.
"""
import cadquery as cq

import mask_params as P

CLAMP_CLR = 0.20          # per side in the seat -- it drops in, it is not a press fit
CLAMP_PAD_PROUD = 0.65    # how far the pressure rib stands below the clamp's underside
CLAMP_RIB_W = 1.6         # width of that rib
CLAMP_TONGUE_W = 11.0     # the neck that reaches down to the single pilot
CLAMP_SCREW_CLR = 2.9     # clearance hole for an M2.5 self-tapper into a Ø2.0 pilot
CLAMP_CSK_D = 4.4         # as much countersink as the tongue's end will carry
CLAMP_SLOT_HW = 2.6       # half-width of the ribbon slot THROUGH the clamp

SHIMS = (0.5, 1.0, 2.0)


# ───────────────────────────────────────────────────────────── camera clamp
def build_clamp():
    """One screw, and it reaches the pocket from below.

    THE SHAPE IS FORCED, not styled.  Three facts about the seat that is actually in the
    mask decide all of it:

      * it is 15.98 x 17.00 mm and ends in a 20 mm wall at z = 97, so the clamp can be
        16.6 mm long and no longer.  The old 21.5 mm one simply would not go in;
      * the only pilot a screwdriver can reach is at z = 83, BELOW the pocket, so the
        clamp is a head over the pocket and a tongue reaching down to that screw;
      * the camera's ribbon has to leave the pocket, and the only way out is over the
        module's back face -- there is 0.5 mm there and nowhere else.  So the clamp is
        slotted THROUGH, on the mirror line, from below the pocket's lower lip to the top
        of the pressure rib: the ribbon comes straight up out of the pocket, through the
        clamp, and lies on top of it in a bay that is 39 mm deep.  It never has to squeeze
        along the seat, and nothing it crosses is a square edge.

    Rotation is taken by the seat's own walls (0.20 mm per side), not by a second screw,
    which is why one is enough.

    PRINT IT TOP FACE DOWN -- as exported.  Then the countersink is a self-supporting
    cone, the flat top face is on the bed, and the pressure rib is the last thing laid
    down.  Nothing here needs support.
    """
    z0, z1 = P.CAM_SEAT_Z0, P.CAM_SEAT_Z1_OPEN      # 80.00 .. 97.00, MEASURED
    cz = (z0 + z1) / 2                              # 88.50 -- local Y = mask z - cz
    length = (z1 - z0) - 2 * CLAMP_CLR              # 16.60
    width = 2 * P.CAM_SEAT_HW - 2 * CLAMP_CLR       # 15.60
    r = P.CAM_SEAT_R - CLAMP_CLR                    # 2.80: the seat's own corners are
    #                                                 R3.0, so the clamp's must be R>=2.4
    #                                                 or the corners foul before the
    #                                                 faces ever touch.

    pocket_y0 = P.LENS_Z - P.CAM_POCKET / 2 - cz    # -2.59, the pocket's lower lip
    head_y0 = -1.90                                 # where the head takes over from the
    #                                                 tongue (mask z 86.60)
    head_y1 = length / 2                            # +8.30
    tongue_y0 = -length / 2                         # -8.30

    head = (cq.Workplane("XY").rect(width, head_y1 - head_y0).extrude(P.CAM_CLAMP_T)
            .translate((0, (head_y0 + head_y1) / 2, 0))
            .edges("|Z").fillet(r))
    tongue = (cq.Workplane("XY").rect(CLAMP_TONGUE_W, head_y0 - tongue_y0)
              .extrude(P.CAM_CLAMP_T)
              .translate((0, (tongue_y0 + head_y0) / 2, 0))
              .edges("|Z").fillet(r))
    # break the top edges BEFORE the union: this is the lip the ribbon rides over on its
    # way out of the pocket, and a printed square corner is what creases an FPC.
    head = head.edges(">Z").chamfer(0.4)
    tongue = tongue.edges(">Z").chamfer(0.4)
    c = head.union(tongue)

    # the pressure rib: a U on three sides of the module's back face, OPEN toward the
    # ribbon so nothing lands on it, and inside the pocket's rounded corners.
    my = P.LENS_Z - cz                              # +2.50, module centre
    ro = P.CAM_BODY / 2 - 0.3                       # 4.20, rib outer half-width
    ri = ro - CLAMP_RIB_W                           # 2.60 -- also the slot's half-width
    rib_y0 = head_y0 + 0.2
    for x0, x1, y0, y1 in ((-ro, ro, my + ri, my + ro),      # across the top
                           (-ro, -ri, rib_y0, my + ri),      # down the left
                           (ri, ro, rib_y0, my + ri)):       # down the right
        c = c.union(cq.Workplane("XY")
                    .moveTo((x0 + x1) / 2, (y0 + y1) / 2)
                    .rect(x1 - x0, y1 - y0)
                    .extrude(-CLAMP_PAD_PROUD))

    # the ribbon slot: through everything, from BELOW the pocket's lower lip (so the mouth
    # is genuinely open, not merely nearly open) to the inside of the rib's top bar.
    slot_y0, slot_y1 = pocket_y0 - 0.5, my + ri
    c = c.cut(cq.Workplane("XY")
              .moveTo(0, (slot_y0 + slot_y1) / 2)
              .rect(2 * CLAMP_SLOT_HW, slot_y1 - slot_y0)
              .extrude(P.CAM_CLAMP_T + 2).translate((0, 0, -1.0)))

    # the screw: a plain clearance hole, countersunk as far as the tongue's end allows.
    sy = P.CAM_MOUNT_Z[0] - cz                      # -5.50
    c = c.cut(cq.Workplane("XY").moveTo(0, sy).circle(CLAMP_SCREW_CLR / 2)
              .extrude(P.CAM_CLAMP_T + 1).translate((0, 0, -1.0)))
    csk = (CLAMP_CSK_D - CLAMP_SCREW_CLR) / 2       # 90° included
    c = c.cut(cq.Workplane("XY").workplane(offset=P.CAM_CLAMP_T - csk)
              .circle(CLAMP_SCREW_CLR / 2).workplane(offset=csk)
              .circle(CLAMP_CSK_D / 2).loft(combine=False).translate((0, sy, 0)))

    # exported top face DOWN: rotate 180° about X and drop onto Z=0
    c = c.rotate((0, 0, 0), (1, 0, 0), 180)
    bb = c.val().BoundingBox()
    return c.translate((0, 0, -bb.zmin))


# ───────────────────────────────────────────────────────────── battery shim
def build_batt_shim():
    """Fills the 9.20 mm between the cell's back face and the cover, and locates it.

    The pouch sits in a 68 x 62 mm zone.  It is 55 x 55, so left alone it can walk 4.7 mm
    each way in x, and there is nothing at all stopping it lifting off the floor -- the
    original note said "retained by foam pressure under the cover", and this is that
    foam, printed.

    NOT SPRUNG, on purpose.  The battery zone's floor is only flat where the donor was
    thick enough to cut: down the middle the mask's own hollow falls away to y = -51, so
    the cell is carried on a ring around its edge.  Preloading the middle of a pouch that
    is supported only at its rim is how you bend a LiPo, so this fills the gap and stops
    it moving, and does not squeeze it.  If your cell measures thicker or thinner than
    CELL_T, change CELL_T -- do not scale the STL, because only the height should move.

    PRINT IT AS EXPORTED, face plate down.  The face plate is the cover side; the ribs
    and the two capture walls stand up off it, so there is no overhang anywhere.
    """
    w, t = P.BATT_SHIM_W, P.BATT_SHIM_WALL
    h = P.BATT_SHIM_T
    d = P.BATT_SHIM_Z1 - P.BATT_SHIM_Z0             # 56.0
    r = P.BATT_SHIM_R

    body = (cq.Workplane("XY").rect(w, d).extrude(h).edges("|Z").fillet(r))
    # hollow it out from the cell side, leaving the face plate against the COVER
    body = body.cut(cq.Workplane("XY").workplane(offset=t)
                    .rect(w - 2 * t, d - 2 * t).extrude(h)
                    .edges("|Z").fillet(max(r - t, 0.5)))
    # rib grid, so a 62 x 56 x 9.2 block costs 10 g and not 40
    for x in (-w / 4, 0.0, w / 4):
        body = body.union(cq.Workplane("XY").workplane(offset=t)
                          .moveTo(x, 0).rect(t, d - 2 * t).extrude(h - t))
    for y in (-d / 4, 0.0, d / 4):
        body = body.union(cq.Workplane("XY").workplane(offset=t)
                          .moveTo(0, y).rect(w - 2 * t, t).extrude(h - t))

    # the two capture walls: they reach past the cell's back face and hold it in x, which
    # is the axis with 4.7 mm of slop.  z is already held by the zone itself (1.5 mm).
    grip_i = P.CELL_W / 2 + P.BATT_SHIM_CLR         # 28.0
    for s in (-1, 1):
        wall = (cq.Workplane("XY")
                .moveTo(s * (grip_i + w / 2) / 2, 0)
                .rect(w / 2 - grip_i, d).extrude(h + P.BATT_SHIM_GRIP))
        body = body.union(wall.intersect(
            cq.Workplane("XY").rect(w, d).extrude(h + P.BATT_SHIM_GRIP)
            .edges("|Z").fillet(r)))

    # wire gates through both end walls, so the pouch's tabs have somewhere to go
    # whichever way round it is fitted
    for s in (-1, 1):
        body = body.cut(cq.Workplane("XY").workplane(offset=t)
                        .moveTo(0, s * d / 2)
                        .rect(P.BATT_SHIM_NOTCH, 4 * t)
                        .extrude(h + P.BATT_SHIM_GRIP))
    return body


# ───────────────────────────────────────────────────────────── depth shims, plugs
def build_shims():
    """Three loose shims on one plate, spaced so they are easy to pick off the bed."""
    side = P.CAM_POCKET - 0.8
    out = None
    for i, t in enumerate(SHIMS):
        s = (cq.Workplane("XY").rect(side, side).extrude(t)
             .edges("|Z").fillet(1.5)
             .translate(((i - 1) * (side + 4.0), 0, 0)))
        out = s if out is None else out.union(s)
    return out


def build_plugs():
    """Blanking plugs for the two eye pupils.

    Push in from the FRONT with tweezers until the face sits ~1.5 mm below the eyeball,
    so it reads as a recessed pupil.  Print in black.  Leaving the bores open also reads
    black -- they are 20 mm tunnels into an unlit bay -- so these are belt and braces
    against dust and against anyone shining a torch at the mask.
    """
    d = P.EYE_PUPIL_D - P.EYE_PLUG_CLR
    out = None
    for i in (-1, 1):
        p = (cq.Workplane("XY").circle(d / 2).extrude(6.0)
             .edges(">Z").chamfer(0.4)
             .translate((i * (d + 4.0), 0, 0)))
        out = p if out is None else out.union(p)
    return out


if __name__ == "__main__":
    for name, part in (("camera_clamp", build_clamp()),
                       ("battery_shim", build_batt_shim()),
                       ("camera_shims", build_shims()),
                       ("eye_plugs", build_plugs())):
        cq.exporters.export(part, f"{name}.stl", tolerance=0.01, angularTolerance=0.1)
        bb = part.val().BoundingBox()
        print(f"wrote {name}.stl   {bb.xlen:5.1f} × {bb.ylen:5.1f} × {bb.zlen:5.1f} mm")
    print(f"\n  clamp seat, as printed: {2*P.CAM_SEAT_HW:.2f} × "
          f"{P.CAM_SEAT_Z1_OPEN-P.CAM_SEAT_Z0:.2f} × {P.CAM_SEAT_DEPTH} mm deep, "
          f"one pilot at z={P.CAM_MOUNT_Z[0]:.0f}")
    print(f"  battery shim fills {P.BATT_SHIM_T:.2f} mm "
          f"(floor {P.FLOOR_Y_BATT:.2f} + cell {P.CELL_T} -> cover {-P.COVER_T})")
    print(f"  depth shims {SHIMS} mm -- stack behind the module to push the lens forward")
    print(f"  plugs Ø{P.EYE_PUPIL_D - P.EYE_PLUG_CLR:.2f} for the Ø{P.EYE_PUPIL_D} pupils")
