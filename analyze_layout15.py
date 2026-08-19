"""Lay out the 1.5x mask: battery, board, camera -- all three, no overlaps.

The electronics do NOT scale, so a bigger mask is bigger RELATIVE to the same hardware.
That is what makes the 55 x 55 x 12 cell possible, and what may finally let the camera
sit clear of the board instead of under it.
"""
import numpy as np
from measure import standoff_min_rect
from mask_frame import MASK_SCALE

FW, CT = 3.0, 2.5
BOARD_W, BOARD_H = 30.4 + 3.6, 40.0 + 4.0        # 34.0 x 44.0 with clearance
BOARD_NEED = 4.96 + 2.54 + 2.5 + 1.0             # comps + wire tails + plenum + air
CELL_W, CELL_H, CELL_T = 55.0, 55.0, 12.0
CELL_FACE_W, CELL_FACE_H = CELL_W + 3.0, CELL_H + 3.0
CELL_NEED = CELL_T + 1.0
LENS_Z = 52.0 * MASK_SCALE

print(f"mask scaled {MASK_SCALE}x   lens site at z = {LENS_Z:.0f}")
print(f"board needs {BOARD_W:.0f} x {BOARD_H:.0f} face and {BOARD_NEED:.2f} mm interior")
print(f"cell  needs {CELL_FACE_W:.0f} x {CELL_FACE_H:.0f} face and {CELL_NEED:.2f} mm interior\n")

def scan(fw, fh, need, label, zlo=20, zhi=150):
    out = []
    for hw in (fw/2, fw/2+2, fw/2+4):
        for z0 in np.arange(zlo, zhi - fh, 2.5):
            z1 = z0 + fh
            s = standoff_min_rect(-hw, hw, z0, z1)
            if not np.isfinite(s):
                continue
            interior = s - FW - CT
            if interior >= need:
                out.append((interior, hw, z0, z1))
    out.sort(reverse=True)
    print(f"--- {label} ---")
    seen = set()
    for interior, hw, z0, z1 in out[:40]:
        key = round(z0/5)
        if key in seen: continue
        seen.add(key)
        print(f"   x±{hw:4.1f}  z {z0:6.1f}..{z1:6.1f}   interior {interior:6.2f}")
        if len(seen) >= 6: break
    return out

cell = scan(CELL_FACE_W, CELL_FACE_H, CELL_NEED, "CELL 58 x 58")
board = scan(BOARD_W, BOARD_H, BOARD_NEED, "BOARD 34 x 44")

print("\n=== combinations with no overlap, and the camera clear of the board ===")
best = None
for ci, chw, cz0, cz1 in cell:
    for bi, bhw, bz0, bz1 in board:
        if not (bz1 + 4 <= cz0 or cz1 + 4 <= bz0):
            continue                              # zones overlap
        cam_clear = (LENS_Z < bz0 - 6) or (LENS_Z > bz1 + 6)
        score = (cam_clear, min(ci - CELL_NEED, bi - BOARD_NEED))
        if best is None or score > best[0]:
            best = (score, (ci, chw, cz0, cz1), (bi, bhw, bz0, bz1), cam_clear)
if best:
    (cam_clear, margin), (ci, chw, cz0, cz1), (bi, bhw, bz0, bz1), _ = best
    print(f"  CELL   x±{chw:.1f}  z {cz0:.1f}..{cz1:.1f}   interior {ci:.2f}")
    print(f"  BOARD  x±{bhw:.1f}  z {bz0:.1f}..{bz1:.1f}   interior {bi:.2f}")
    print(f"  camera at z={LENS_Z:.0f} -> "
          + ("CLEAR of the board (serviceable without unbolting it)" if cam_clear
             else "still under the board"))
    print(f"  tightest margin {margin:.2f} mm")
else:
    print("  no non-overlapping combination")
