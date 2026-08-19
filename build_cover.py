"""cover.stl -- the plate that closes the bay and hangs the mask.

Built in CadQuery rather than trimesh: this one is a clean parametric B-rep part with
countersinks and an undercut keyhole, which is what CadQuery is good at.  The mask
itself stays in trimesh/manifold because a 1.1 M-face donor is not something an OCC
kernel will ingest.

LOCAL FRAME (chosen so the exported STL is already in print orientation)
    cq X = mask x        cq Y = mask z        cq Z = mask y

so the plate lies flat in XY with its thickness along Z, spanning Z = -COVER_T .. 0.
Z = 0 is the wall plane; the hanging pads stand up from it into positive Z.

PRINT IT INNER FACE DOWN.  Then the countersinks open upward and need no support, and
the keyhole's capturing lip is a 1.65 mm ledge that bridges cleanly.
"""
import cadquery as cq

import mask_params as P


def outline():
    """The cover's plan shape: every bay zone's rebate, less a running clearance.

    Built from P.ZONES rather than two hard-coded rectangles -- the 1.75x mask has three
    zones of very different widths (board 52, waist 48, battery 68) and the old two-zone
    version simply failed to build.
    """
    c = P.COVER_CLR
    plate = None
    for i, (hw, z0, z1, fl, _) in enumerate(P.ZONES):
        lo = z0 - (0.5 if i == 0 else -1.0)
        hi = z1 + (P.COVER_LIP - c if i == len(P.ZONES) - 1 else 1.0)
        w = 2 * (hw + P.COVER_LIP) - 2 * c
        seg = (cq.Workplane("XY").rect(w, hi - lo).extrude(P.COVER_T)
               .translate((0, (lo + hi) / 2, 0))
               .edges("|Z").fillet(min(P.COVER_CORNER_R - c, w / 2 - 0.5,
                                       (hi - lo) / 2 - 0.5)))
        plate = seg if plate is None else plate.union(seg)
    return plate.translate((0, 0, -P.COVER_T))


def build_cover():
    plate = outline()

    # hanging pads and the foot, standing proud into +Z
    for x, z in P.HANG_XY:
        plate = plate.union(
            cq.Workplane("XY").rect(P.HANG_PAD_W, P.HANG_PAD_L)
            .extrude(P.HANG_PAD_H).edges("|Z").fillet(3.0)
            .translate((x, z, 0)))
    for x, z in P.FOOT_XY:
        plate = plate.union(
            cq.Workplane("XY").rect(P.FOOT_W, P.FOOT_L)
            .extrude(P.HANG_PAD_H).edges("|Z").fillet(3.0)
            .translate((x, z, 0)))

    # The undercut keyhole in each pad: a wide stadium behind the face, with the entry
    # circle and the narrow capturing slot cut through the lip.
    #
    # ⚠ ORIENTATION IS FUNCTIONAL, NOT COSMETIC.  The screw is FIXED in the wall; hanging
    # the mask lets it DROP, so the screw travels UP relative to this plate.  The entry
    # circle must therefore sit BELOW the resting position -- big hole at the bottom,
    # narrow slot above it, load taken at the TOP of the slot.
    #
    # This was built inverted (entry above, slot below) until 2026-08-18.  It looked
    # plausible and every dimensional check passed, because nothing tested which way up
    # it was: the mask would simply have slid off the screws.
    deep = P.HANG_PAD_H - P.KEYHOLE_CAP_T
    for x, z in P.HANG_XY:
        ze = z - P.KEYHOLE_ENTRY_DZ                      # head entry -- BELOW
        zb = ze + P.KEYHOLE_DROP                         # rests here -- ABOVE the entry
        head = P.KEYHOLE_HEAD_D
        # lower cavity: a stadium the head can slide down inside
        cav = (cq.Workplane("XY").workplane(offset=0.0)
               .moveTo(x, (ze + zb) / 2).rect(head, P.KEYHOLE_DROP + head)
               .extrude(deep).edges("|Z").fillet(head / 2 - 0.01))
        # through the lip: the entry circle, plus the narrow slot
        entry = (cq.Workplane("XY").workplane(offset=deep)
                 .moveTo(x, ze).circle(head / 2).extrude(P.KEYHOLE_CAP_T + 0.1))
        slot = (cq.Workplane("XY").workplane(offset=deep)
                .moveTo(x, (ze + zb) / 2)
                .rect(P.KEYHOLE_SHANK_D, P.KEYHOLE_DROP)
                .extrude(P.KEYHOLE_CAP_T + 0.1))
        plate = plate.cut(cav).cut(entry).cut(slot)

    # ---- vents: stadium slots, a chimney rather than decoration (see mask_params)
    for _label, zs in P.VENT_BANKS.items():
        for z in zs:
            slot = (cq.Workplane("XY").moveTo(0, z)
                    .rect(P.VENT_L - P.VENT_W, P.VENT_W).extrude(P.COVER_T + 1.0)
                    .edges("|Z").fillet(P.VENT_R - 0.01)
                    .translate((0, 0, -P.COVER_T - 0.5)))
            plate = plate.cut(slot)

    # cover screws: countersunk from the OUTER face, which is the face that meets the
    # wall -- a proud head would rock the mask
    for x, z in list(P.POST_XY) + list(P.POST_XY_BATT):
        plate = plate.cut(
            cq.Workplane("XY").moveTo(x, z).circle(P.COVER_SCREW_D / 2)
            .extrude(-P.COVER_T - 0.2))
        csk_r = P.COVER_CSK_D / 2
        depth = (P.COVER_CSK_D - P.COVER_SCREW_D) / 2   # 90° included
        plate = plate.cut(
            cq.Workplane("XY").workplane(offset=-depth)
            .circle(P.COVER_SCREW_D / 2).workplane(offset=depth)
            .circle(csk_r).loft(combine=False).translate((x, z, 0)))
    return plate


if __name__ == "__main__":
    c = build_cover()
    cq.exporters.export(c, "cover.stl", tolerance=0.01, angularTolerance=0.1)
    bb = c.val().BoundingBox()
    print(f"wrote cover.stl  {bb.xlen:.1f} × {bb.ylen:.1f} × {bb.zlen:.1f} mm  "
          f"(plate {P.COVER_T} mm + {P.HANG_PAD_H} mm pads)")
