"""Small solid-modelling helpers, all in the mask frame (x right, y out-of-wall, z up).

trimesh + manifold3d rather than CadQuery for anything that touches the mask: the donor
is a 1.1 M-face mesh, which an OCC B-rep kernel cannot ingest, and manifold does the
whole boolean in ~1 s.  The free-standing parts (cover, camera mount, plug) are built in
CadQuery, where a parametric B-rep is the better tool.

Everything here extrudes along +Y, because in this frame Y is the "into the mask"
direction that every pocket, bore and boss runs along.
"""
import numpy as np
import trimesh
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

# trimesh extrudes a polygon's (X, Y) along +Z.  Our polygons are drawn in the mask's
# (x, z) plane and must extrude along y, so we need (X, Y, Z) -> (x=X, y=-Z, z=Y):
# a +90° rotation about X.  The -90° version maps to (X, Z, -Y), which silently MIRRORS
# the part in z -- it still builds, still comes out watertight, and puts every feature
# at the wrong height.  Sign matters here.
_Z_TO_Y = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])


def extrude_y(polygon, y0, y1):
    """Extrude a shapely polygon (in the x/z plane) between y0 and y1.

    simplify() before extruding is not cosmetic: coincident or near-coincident ring
    vertices become zero-area triangles in the extruder's cap triangulation, the prism
    comes out non-watertight, and manifold3d then rejects the whole boolean with
    "Not all meshes are volumes".  Cheaper to clean the ring than to debug that.
    """
    if y1 <= y0:
        raise ValueError(f"extrude_y needs y1 > y0, got {y0} .. {y1}")
    # Tolerance ladder.  An organic 637-point ring (the mask silhouette) defeats the cap
    # triangulator at fine tolerances and succeeds at 0.3 mm; a clean rounded rectangle
    # succeeds at the first rung.  So try progressively coarser rings and take the first
    # that closes, rather than hard-coding a tolerance that suits one caller and not the
    # other.  0.3 mm is harmless here: the only organic ring is the silhouette clip,
    # which is already inset 0.8 mm from the true outline.
    last = None
    for tol in (1e-4, 0.05, 0.1, 0.2, 0.3, 0.5):
        poly = polygon.simplify(tol)
        if poly.is_empty:
            continue
        m = trimesh.creation.extrude_polygon(poly, height=y1 - y0)
        m.merge_vertices()
        m.update_faces(m.nondegenerate_faces())
        if m.is_watertight:
            m.apply_transform(_Z_TO_Y)
            # after the rotation the prism spans y in [-(y1-y0), 0]; slide it into place
            m.apply_translation([0, y1, 0])
            return m
        last = (tol, len(m.faces))
    raise RuntimeError(f"extrude_y could not close a prism for this polygon "
                       f"(best {last}) -- check it for slivers or self-touches")


def rrect(x0, x1, z0, z1, r, arc=16):
    """Rounded rectangle in the x/z plane as a shapely polygon.

    Built as ONE clean ring rather than a union of boxes and circles: that union leaves
    coincident vertices where the primitives meet, and trimesh's extruder turns those
    into degenerate triangles, which makes the prism non-watertight and manifold3d then
    refuses it with "Not all meshes are volumes".
    """
    r = min(r, (x1 - x0) / 2 - 1e-6, (z1 - z0) / 2 - 1e-6)
    if r <= 0:
        return box(x0, z0, x1, z1)
    pts = []
    for cx, cz, a0 in ((x1 - r, z0 + r, -np.pi / 2), (x1 - r, z1 - r, 0.0),
                       (x0 + r, z1 - r, np.pi / 2), (x0 + r, z0 + r, np.pi)):
        t = np.linspace(a0, a0 + np.pi / 2, arc)
        pts.append(np.column_stack([cx + r * np.cos(t), cz + r * np.sin(t)]))
    return Polygon(np.vstack(pts))


def rrect_prism(x0, x1, z0, z1, r, y0, y1):
    return extrude_y(rrect(x0, x1, z0, z1, r), y0, y1)


def cyl_y(cx, cz, d, y0, y1, sections=96):
    """Cylinder with its axis along Y, spanning y0..y1."""
    c = trimesh.creation.cylinder(radius=d / 2, height=y1 - y0, sections=sections)
    c.apply_transform(_Z_TO_Y)
    c.apply_translation([cx, (y0 + y1) / 2, cz])
    return c


def cyl_x(cy, cz, d, x0, x1, sections=96):
    """Cylinder with its axis along X, spanning x0..x1.

    The USB-C breakout is the only thing here that bolts to a SIDE wall, so its pilots
    are the only holes that do not run along y.
    """
    c = trimesh.creation.cylinder(radius=d / 2, height=x1 - x0, sections=sections)
    c.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    c.apply_translation([(x0 + x1) / 2, cy, cz])
    return c


def cone_y(cx, cz, d0, d1, y0, y1, sections=96):
    """Truncated cone along Y: diameter d0 at y0, d1 at y1."""
    t = np.linspace(0, 2 * np.pi, sections, endpoint=False)
    ring0 = np.column_stack([cx + d0 / 2 * np.cos(t), np.full(sections, y0),
                             cz + d0 / 2 * np.sin(t)])
    ring1 = np.column_stack([cx + d1 / 2 * np.cos(t), np.full(sections, y1),
                             cz + d1 / 2 * np.sin(t)])
    verts = np.vstack([ring0, ring1, [[cx, y0, cz]], [[cx, y1, cz]]])
    n = sections
    c0, c1 = 2 * n, 2 * n + 1
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces += [[i, j, n + j], [i, n + j, n + i]]     # side
        faces += [[c0, j, i]]                            # y0 cap
        faces += [[c1, n + i, n + j]]                    # y1 cap
    return trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=True)


def union(parts):
    parts = [p for p in parts if p is not None]
    if len(parts) == 1:
        return parts[0]
    return trimesh.boolean.union(parts, engine="manifold")


def difference(a, parts):
    parts = [p for p in parts if p is not None]
    if not parts:
        return a
    return trimesh.boolean.difference([a] + parts, engine="manifold")


def intersection(parts):
    return trimesh.boolean.intersection(parts, engine="manifold")


def silhouette_polygon(outline, xs, zs, shrink=0.0):
    """The mask's front-view outline, as a shapely polygon, from the sampled grid.

    Used to clip everything added to the mask, so no added feature can ever poke out
    past the silhouette and become visible from the front.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Pad with a ring of empty cells first.  The mask's extreme points sit ON the grid
    # boundary, and a contour that runs into the domain edge is left OPEN -- which is
    # why the unpadded version returned four 200 mm² scraps instead of one 7085 mm² ring.
    dx = float(xs[1] - xs[0])
    dz = float(zs[1] - zs[0])
    outline = np.pad(outline.astype(float), 1, mode="constant", constant_values=0.0)
    xs = np.concatenate([[xs[0] - dx], xs, [xs[-1] + dx]])
    zs = np.concatenate([[zs[0] - dz], zs, [zs[-1] + dz]])

    fig, ax = plt.subplots()
    cs = ax.contour(xs, zs, outline, levels=[0.5])
    polys = []
    for seg in cs.allsegs[0]:
        if len(seg) < 4:
            continue
        # marching-squares contours can self-touch; buffer(0) repairs them
        p = Polygon(seg).buffer(0)
        if p.is_empty:
            continue
        for g in (p.geoms if p.geom_type == "MultiPolygon" else [p]):
            if g.area > 1.0:
                polys.append(g)
    plt.close(fig)
    if not polys:
        raise RuntimeError("no silhouette contour found")
    merged = unary_union(polys)
    if merged.geom_type == "MultiPolygon":
        merged = max(merged.geoms, key=lambda g: g.area)
    merged = Polygon(merged.exterior)          # drop interior holes (teeth gaps etc.)
    if shrink:
        merged = merged.buffer(-shrink, join_style=2)
        if merged.geom_type == "MultiPolygon":
            merged = max(merged.geoms, key=lambda g: g.area)
    return merged


def report(name, mesh):
    print(f"  {name:22s} {len(mesh.faces):8d} faces  "
          f"vol {mesh.volume/1000:7.2f} cm^3  "
          f"watertight={mesh.is_watertight}  bodies={mesh.body_count}")
    return mesh
