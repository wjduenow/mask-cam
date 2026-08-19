"""Canonical working frame for the mask-cam build, plus the mask loader.

The donor STL arrives in Bambu plate coordinates.  Everything downstream works in
THIS frame instead, so no build script ever repeats the transform:

    X  +right across the mask's width      (0 = the mask's vertical mirror line)
    Y  -Y is OUT of the wall (toward the viewer / the camera's subject)
       +Y is INTO the wall.  y = 0 is the BACK-MOST point of the whole mask,
       i.e. the plane the mask rests against when hung flat.  All mask material
       therefore lives at y <= 0.
    Z  +up.  z = 0 is the bottom of the mask (the chin/lower fangs).

Chosen so that "how deep is the rear cavity here" is just `-y`, and the wall is y=0.
"""
import numpy as np
import trimesh

SRC_3MF = "Sri_Lankan_Mask_2.3mf"

# Uniform scale applied to the donor before anything measures it.  1.0 is the artist's
# original; 1.5 was chosen to make room for a 55 x 55 x 12 mm cell.  Scaling UNIFORMLY
# matters: stretching x and z alone squashes the sculpt, and on a face the eyes and
# muzzle are exactly where that reads as wrong.  The ELECTRONICS do not scale -- every
# board, pocket and fastener dimension in mask_params.py stays in real millimetres --
# which is the whole point: a bigger mask is bigger relative to the same hardware.
MASK_SCALE = 1.75


def load_mask(path=SRC_3MF, process=False, scale=None):
    """Load the donor mask, scale it, and move it into the canonical frame."""
    m = trimesh.load(path, force="mesh", process=process)
    s = MASK_SCALE if scale is None else scale
    if s != 1.0:
        m.apply_scale(s)
    lo, hi = m.bounds
    # x -> centred on the silhouette midline; y -> back-most point at 0; z -> base at 0
    m.apply_translation([-(lo[0] + hi[0]) / 2.0, -hi[1], -lo[2]])
    return m


if __name__ == "__main__":
    m = load_mask()
    lo, hi = m.bounds
    print(f"bounds min={lo.round(2)} max={hi.round(2)}")
    print(f"extents={m.extents.round(2)}  volume={m.volume/1000:.1f} cm^3  "
          f"watertight={m.is_watertight}")
    m.export("mask_frame.stl")
    print("wrote mask_frame.stl")
