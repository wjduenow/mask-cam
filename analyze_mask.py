"""Load the Sri Lankan Mask 3MF and report everything the camera retrofit needs to know.

Answers, in order:
  1. Is it one watertight solid?  Overall size?
  2. Is it hollow (a shell) or solid?  -> volume vs. bbox, and a raycast probe.
  3. How thick is the material front-to-back at the candidate lens sites?
  4. How much clear interior volume is there behind the face?
  5. Where is the back opening / rim plane the cover would seal against?
"""
import numpy as np
import trimesh

SRC = "Sri_Lankan_Mask_2.3mf"

m = trimesh.load(SRC, force="mesh", process=False)
print(f"faces={len(m.faces)}  verts={len(m.vertices)}")
print(f"watertight={m.is_watertight}  winding_consistent={m.is_winding_consistent}  "
      f"volume_valid={m.is_volume}  bodies={m.body_count}")

lo, hi = m.bounds
print(f"\nbounds  min={lo.round(2)}  max={hi.round(2)}")
print(f"extents (X,Y,Z) = {m.extents.round(2)} mm")
bbox_v = float(np.prod(m.extents))
print(f"mesh volume = {m.volume/1000:.1f} cm^3   bbox volume = {bbox_v/1000:.1f} cm^3   "
      f"fill = {100*m.volume/bbox_v:.1f}%")

# ---------------------------------------------------------------- orientation
# Which axis is "through the face"?  The mask is a wall plaque: the flat back is a
# plane, the face bulges out.  Find it by looking at the area-weighted normal spread.
for ax, name in enumerate("XYZ"):
    n = m.face_normals[:, ax]
    a = m.area_faces
    print(f"  axis {name}: area with normal >+0.9 = {a[n > 0.9].sum():8.0f} mm^2   "
          f"< -0.9 = {a[n < -0.9].sum():8.0f} mm^2")

# ---------------------------------------------------------------- thickness probe
# Cast rays along -Y (into the face) on a grid over the front and count hits.  An even
# number of surface crossings on a line through a hollow shell = 2 per wall.
def probe(origin, direction, label):
    """Report every surface crossing along a ray, so we can read wall/air/wall."""
    locs, idx_ray, _ = m.ray.intersects_location(
        ray_origins=np.array([origin], dtype=np.float64),
        ray_directions=np.array([direction], dtype=np.float64),
        multiple_hits=True,
    )
    if len(locs) == 0:
        print(f"  {label:26s} no hits")
        return None
    t = np.sort(((locs - origin) @ np.array(direction, dtype=np.float64)))
    spans = np.diff(t)
    txt = " | ".join(f"{s:.2f}" for s in spans)
    print(f"  {label:26s} {len(t)} crossings at "
          + ", ".join(f"{v:.1f}" for v in t) + f"   spans: {txt}")
    return t

print("\n--- ray probes (direction = +Y, i.e. back->front through the plaque) ---")
cx = (lo[0] + hi[0]) / 2
cz = (lo[2] + hi[2]) / 2
y_start = lo[1] - 5.0
for label, (px, pz) in {
    "centre of face": (cx, cz),
    "10mm above centre": (cx, cz + 10),
    "20mm above centre": (cx, cz + 20),
    "20mm below centre": (cx, cz - 20),
    "40mm below centre": (cx, cz - 40),
    "30mm left of centre": (cx - 30, cz),
    "30mm right of centre": (cx + 30, cz),
}.items():
    probe([px, y_start, pz], [0, 1, 0], label)

m.export("mask_raw.stl")
print("\nwrote mask_raw.stl")
