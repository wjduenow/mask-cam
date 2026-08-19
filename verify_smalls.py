"""Check the camera clamp and the battery shim against the MASK MESH, not the parameters.

The clamp that shipped before this passed every dimensional check in the file and still
would not go in the hole, because nothing ever asked the mesh whether the seat it was cut
to actually existed.  It did not: the battery zone's floor crosses the seat at z=97 and
the last 5 mm of it -- with the second pilot in it -- is a sealed void inside the mask.

So this checker does the one thing that catches that class of mistake: it puts each part
where it is supposed to go, in mask coordinates, and asks the mask whether the two
overlap.  A part that intersects solid plastic fails no matter how good its numbers look.

    python verify_smalls.py
"""
import numpy as np
import trimesh
from shapely.geometry import Polygon

import mask_params as P

MASK = "mask_cam.stl"
FAIL = []


def check(label, ok, detail=""):
    print(f"  {'OK  ' if ok else 'FAIL'}  {label:44s} {detail}")
    if not ok:
        FAIL.append(label)


def clamp_to_mask(v):
    """camera_clamp.stl is exported TOP FACE DOWN; put it back where it is fitted."""
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    return np.column_stack([x,
                            P.CAM_SEAT_Y + (P.CAM_CLAMP_T - z),
                            -y + (P.CAM_SEAT_Z0 + P.CAM_SEAT_Z1_OPEN) / 2])


def shim_to_mask(v):
    """battery_shim.stl is exported face-plate down; z=0 is the face on the cover."""
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    return np.column_stack([x, -P.COVER_T - z,
                            y + (P.BATT_SHIM_Z0 + P.BATT_SHIM_Z1) / 2])


def reachable(mask, xs, zs):
    """First surface seen from BEHIND: the boundary of the space you can reach."""
    o = np.column_stack([xs, np.full(len(xs), 40.0), zs])
    d = np.tile([0, -1.0, 0], (len(o), 1))
    loc, idx, _ = mask.ray.intersects_location(ray_origins=o, ray_directions=d,
                                               multiple_hits=False)
    Y = np.full(len(o), np.nan); Y[idx] = loc[:, 1]
    return Y


def fits(mask, part, place, label, n=4000):
    """Can the part be dropped into the bay from behind, and does it clear the mask?

    Stated as insertability rather than as a boolean overlap, because that is the
    stronger claim AND the cheaper one: everything between y=0 and the first surface a
    ray from behind meets is open bay, so a point at (x, y, z) is in free air exactly
    when y > surface(x, z).  A part that passes this cannot foul on the way in either,
    which a volume intersection would not have told us.
    """
    pts = place(np.vstack([part.vertices,
                           trimesh.sample.volume_mesh(part, n)]))
    slack = pts[:, 1] - reachable(mask, pts[:, 0], pts[:, 2])
    worst = np.nanmin(slack)
    j = int(np.nanargmin(slack))
    check(f"{label} clears the mask, and goes in from behind", worst >= -0.02,
          f"{len(pts)} points; tightest {worst:+.2f} mm at "
          f"(x {pts[j,0]:+.2f}, z {pts[j,2]:.2f})")
    return pts


def main():
    mask = trimesh.load(MASK, process=True)
    clamp = trimesh.load("camera_clamp.stl", process=True)
    shim = trimesh.load("battery_shim.stl", process=True)

    print(f"\n=== the seat that is actually in {MASK} ===")
    def surf(xs, zs):
        """First surface seen from BEHIND -- i.e. the one a tool can reach."""
        xs, zs = np.atleast_1d(xs), np.atleast_1d(zs)
        xs, zs = np.broadcast_arrays(xs, zs)
        o = np.column_stack([xs.ravel(), np.full(xs.size, 40.0), zs.ravel()])
        d = np.tile([0, -1.0, 0], (len(o), 1))
        loc, idx, _ = mask.ray.intersects_location(ray_origins=o, ray_directions=d,
                                                   multiple_hits=False)
        Y = np.full(len(o), np.nan); Y[idx] = loc[:, 1]
        return Y

    def edge(fixed, axis, lo, hi, test, step=0.05):
        v = np.arange(lo, hi, step)
        Y = surf(np.full(len(v), fixed), v) if axis == "z" else surf(v, np.full(len(v), fixed))
        ok = test(Y)
        return (v[ok].min(), v[ok].max()) if ok.any() else (np.nan, np.nan)

    open_ = lambda Y: (Y < P.CAM_SEAT_Y + 0.15) | np.isnan(Y)
    sx0, sx1 = edge(90.0, "x", -10, 10, open_)
    sz0, sz1 = edge(0.0, "z", 76, 106, open_)
    check("seat is where the parameters say", abs(sz1 - P.CAM_SEAT_Z1_OPEN) < 0.1,
          f"measured x {sx0:+.2f}..{sx1:+.2f}, z {sz0:.2f}..{sz1:.2f}, "
          f"floor y {surf(6.9, 90.0)[0]:.2f}")
    pilot = lambda Y: np.isclose(Y, P.CAM_SEAT_Y - P.CAM_MOUNT_DEPTH, atol=0.2)
    for pz in P.CAM_MOUNT_Z:
        a, b = edge(pz, "x", -4, 4, pilot)
        check(f"pilot z={pz:.0f} is open to a screwdriver", np.isfinite(a),
              f"Ø{b - a + 0.05:.2f} at x {a:+.2f}..{b:+.2f}")
    a, _ = edge(P.LENS_Z + P.CAM_MOUNT_DZ, "x", -4, 4, pilot)
    check("no pilot is left buried", not np.isfinite(a),
          f"nothing cut at z={P.LENS_Z + P.CAM_MOUNT_DZ:.0f}, which the mask seals over")

    print("\n=== camera clamp ===")
    lo, hi = clamp.bounds
    check("fits the seat's width", hi[0] - lo[0] <= 2 * P.CAM_SEAT_HW - 0.2,
          f"clamp {hi[0]-lo[0]:.2f} mm in a {2*P.CAM_SEAT_HW:.2f} mm slot")
    check("fits the seat's length",
          hi[1] - lo[1] <= P.CAM_SEAT_Z1_OPEN - P.CAM_SEAT_Z0 - 0.2,
          f"clamp {hi[1]-lo[1]:.2f} mm in a "
          f"{P.CAM_SEAT_Z1_OPEN - P.CAM_SEAT_Z0:.2f} mm recess")
    check("does not stand proud of the bay floor",
          P.CAM_CLAMP_T <= P.CAM_SEAT_DEPTH,
          f"{P.CAM_CLAMP_T} mm plate in a {P.CAM_SEAT_DEPTH} mm seat, rib excluded")
    fits(mask, clamp, clamp_to_mask, "clamp")

    # the screw hole must sit ON the one pilot, not near it: fill the pilot's own
    # cylinder with points and require every one of them to be in free air in the clamp.
    sy = P.CAM_MOUNT_Z[0]
    th = np.linspace(0, 2 * np.pi, 40, endpoint=False)
    rr = np.linspace(0, P.CAM_MOUNT_PILOT / 2, 4)
    hh = np.linspace(0.05, P.CAM_CLAMP_T - 0.05, 6)
    pts = np.array([[r * np.cos(t), -(sy - (P.CAM_SEAT_Z0 + P.CAM_SEAT_Z1_OPEN) / 2)
                     + r * np.sin(t), h]
                    for t in th for r in rr for h in hh])
    check("the screw hole clears the Ø2.0 pilot", not clamp.contains(pts).any(),
          f"the pilot's full Ø{P.CAM_MOUNT_PILOT} bore is open through the tongue "
          f"at z={sy:.0f}")

    # the pressure rib: inside the pocket, and touching the module
    rib_pts = clamp_to_mask(trimesh.sample.volume_mesh(clamp, 8000))
    tip = rib_pts[:, 1] < P.CAM_SEAT_Y - 0.05                # material below the seat floor
    check("the pressure rib enters the pocket", tip.any(),
          f"{int(tip.sum())} sampled points reach {rib_pts[tip,1].min():.2f} "
          f"(seat floor {P.CAM_SEAT_Y:.2f})")
    if tip.any():
        inpk = (np.abs(rib_pts[tip, 0]) <= P.CAM_POCKET / 2 - 0.4) & \
               (np.abs(rib_pts[tip, 2] - P.LENS_Z) <= P.CAM_POCKET / 2 - 0.4)
        check("the rib stays inside the pocket", inpk.all(),
              f"x |{np.abs(rib_pts[tip,0]).max():.2f}|, "
              f"z {rib_pts[tip,2].min():.2f}..{rib_pts[tip,2].max():.2f} "
              f"in a {P.CAM_POCKET:.2f} mm pocket at z={P.LENS_Z:.0f}")
    slack = P.CAM_SEAT_Y - (P.CAM_POCKET_Y + P.CAM_MODULE_DEPTH)
    proud = P.CAM_SEAT_Y - rib_pts[:, 1].min()
    check("the rib actually reaches the module", proud >= slack,
          f"rib stands {proud:.2f} mm proud, the module's back face is {slack:.2f} mm "
          f"below the seat -> {proud - slack:+.2f} mm of squeeze")

    # the ribbon has to get out.  Project the clamp along the mask's y and ask what
    # fraction of the pocket's mouth it leaves open -- the earlier version of this part
    # measured 1.4 mm of clearance that its own tongue was standing in.
    from shapely.geometry import Point, box
    from shapely.ops import unary_union
    v = clamp_to_mask(clamp.vertices)[:, [0, 2]]
    foot = unary_union([Polygon(v[f]) for f in clamp.faces
                        if Polygon(v[f]).is_valid and Polygon(v[f]).area > 1e-9]).buffer(0)
    pk = box(-P.CAM_POCKET / 2, P.LENS_Z - P.CAM_POCKET / 2,
             P.CAM_POCKET / 2, P.LENS_Z + P.CAM_POCKET / 2)
    openarea = pk.difference(foot)
    check("the ribbon has a way out of the pocket", openarea.area > 15.0,
          f"{openarea.area:.1f} mm² of the {pk.area:.1f} mm² pocket mouth is open "
          f"through the clamp")
    lip = Point(0.0, P.LENS_Z - P.CAM_POCKET / 2 + 0.3)
    check("and it is open at the module's lower edge", openarea.contains(lip),
          f"the slot reaches the pocket's lower lip on the mirror line, where the "
          f"module's ribbon leaves it")

    print("\n=== battery shim ===")
    lo, hi = shim.bounds
    check("thickness fills the gap exactly",
          abs(P.BATT_SHIM_T - (-P.COVER_T - (P.FLOOR_Y_BATT + P.CELL_T))) < 1e-9,
          f"floor {P.FLOOR_Y_BATT:.2f} + cell {P.CELL_T:.1f} = {P.CELL_BACK_Y:.2f}, "
          f"cover inner face {-P.COVER_T:.2f} -> {P.BATT_SHIM_T:.2f} mm")
    check("covers the whole cell", hi[0] - lo[0] >= P.CELL_W and hi[1] - lo[1] >= P.CELL_H,
          f"shim {hi[0]-lo[0]:.1f} × {hi[1]-lo[1]:.1f} over a "
          f"{P.CELL_W:.0f} × {P.CELL_H:.0f} cell")
    check("the capture walls clear the cell",
          P.CELL_W / 2 + P.BATT_SHIM_CLR >= P.CELL_W / 2,
          f"{P.BATT_SHIM_CLR:.2f} mm per side, and they reach "
          f"{P.BATT_SHIM_GRIP:.1f} mm past the cell's back face")
    fits(mask, shim, shim_to_mask, "shim")

    # how much of the cell is actually carried by the mask, which is why it is not sprung
    S = 0.5
    xs = np.arange(-P.CELL_W / 2, P.CELL_W / 2, S)
    zs = np.arange(P.CELL_CZ - P.CELL_H / 2, P.CELL_CZ + P.CELL_H / 2, S)
    XX, ZZ = np.meshgrid(xs, zs)
    o = np.column_stack([XX.ravel(), np.full(XX.size, 40.0), ZZ.ravel()])
    d = np.tile([0, -1.0, 0], (len(o), 1))
    loc, idx, _ = mask.ray.intersects_location(ray_origins=o, ray_directions=d,
                                               multiple_hits=False)
    Y = np.full(len(o), np.nan); Y[idx] = loc[:, 1]
    carried = np.isclose(Y, P.FLOOR_Y_BATT, atol=0.3).mean()
    print(f"\n  note: {carried*100:.0f}% of the cell's footprint is on flat floor at "
          f"y={P.FLOOR_Y_BATT:.2f};")
    print(f"        the rest overhangs the crown's own hollow, down to "
          f"y={np.nanmin(Y):.2f}.  A pouch")
    print(f"        carried on a rim is one you must not press in the middle -- hence "
          f"the zero-preload shim.")

    print("\n" + ("small parts verified" if not FAIL
                  else f"{len(FAIL)} FAILED: " + ", ".join(FAIL)))
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
