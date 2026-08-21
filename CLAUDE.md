# mask-cam — working notes for Claude

A Sri Lankan Gini Raksha mask converted to carry an ESP32-S3 camera, a battery and a
charger, with the donor's outside surface untouched. Read `README.md` first — it is the
design document and it is current. This file is the operational stuff that does not belong
in it.

---

## Before anything else: the donor is not in this repo

`Sri_Lankan_Mask_2.3mf` is Tbridge3D's, under a licence that forbids redistribution, so it
is gitignored and absent from every commit. **Nothing builds without it.** If it is not in
this directory, stop and say so — do not try to work around it.

`mask_cam.3mf`, `mask_cam.stl`, `mask_raw.stl`, `extracted/` and the `*.npz` grids are
gitignored too. All of them regenerate:

```bash
python build_all.py --force      # re-samples the donor, rebuilds everything, verifies
```

## Running things

The interpreter is the venv one directory up, and the scripts import each other by name,
so run from this directory with `PYTHONPATH=.`:

```bash
PYTHONPATH=. /home/wesd/Projects/printing/.venv/bin/python build_mask.py
```

| script | time | note |
|---|---|---|
| `build_mask.py` | ~2–3 min | 1 M-face booleans via manifold3d |
| `verify.py` | **~8 min** | ray-casts the finished mesh; start it in the background |
| `build_cover.py` / `build_stand.py` / `build_smalls.py` | seconds | CadQuery |
| `verify_cover.py` / `verify_stand.py` / `verify_smalls.py` | ~1 min | |

## Things that will waste your time if you rediscover them

- **`mesh.contains()` on the 1 M-face mask gets OOM-killed** past a few thousand points.
  Cast rays instead. `verify_smalls.py`'s `fits()` shows the pattern — a point is in free
  air exactly when `y > surface(x, z)` for the first surface a ray from behind meets.
- **Thousands of single-ray calls segfault.** Batch them into one
  `intersects_location` call with an array of origins.
- **A ray cast exactly along a designed face grazes it** and returns an odd number of
  crossings. `verify.py` §3 offsets its sample grid by `JIG_X/JIG_Z` for this reason; a
  bay with 19 mm of relief once reported 0.00.
- **Coplanar cutter and boss faces** make degenerate slivers. Offset one by 0.05.
- `git filter-repo` **checks out the rewritten HEAD and deletes now-untracked files from
  the working tree.** Back up `.git` before using it.

## The two rules this project runs on

**1. Derive, never type.** Floors, seats and clearances are computed at import time in
`mask_params.py` from the sampled surface. If you find yourself typing a number that
another number implies, derive it instead.

**2. Verify against the MESH, not the parameters.** Every serious bug here passed its
dimensional checks. The clamp was cut to a seat that did not exist; all 14 posts and
bosses were built and then deleted by the bay they stood in, and `verify.py` reported
"all checks passed" for months because nothing looked. When you add a feature, add the
check that asks the exported mesh whether it is really there.

`build_mask.py`'s order of operations is load-bearing: **walls → cuts → pillars → pilots.**
Walls before the carve so it cuts a clean pocket inside them; pillars after it because they
stand in the volume the carve removes; pilots last because until the pillars exist there is
nothing to drill. The DWEII pocket is built as its own boolean assembly inside
`build_pillars()` because its retaining lip is an undercut, which one cutter cannot make.

---

## Where this was left, 2026-08-21

Everything builds and all four checkers pass. `README.md` §"What the checker caught" is the
full list of what went wrong and why.

**Printed and in hand:** an early mask and cover — both **superseded**, they predate the
posts, the SD clearance and the module pocket. `camera_clamp.stl` is printed and fits.

**Not yet printed:** the current `mask_cam.stl` and `cover.stl`, plus `power_clamp.stl`.

**Wiring:** the cell is on the DWEII module's `+`/`−` pair (it was reversed once — see the
README's polarity warning, the fuel gauge shows a reversed cell as a full one). The boost
auto-starts on load current, tested, so `K` stays unwired and nothing comes out through the
cover. Last step in progress was the module's `5V ±` to the cam board's **square** `5V` pad
and the `GND` below it, first and second down from the corner mounting hole. **The pad
silkscreened `1` is GPIO1 and 5 V into it kills the board.**

### Open

- ⚠ **The SD card's span along the board is photo-scaled**, not callipered — `SD_Z0/SD_Z1`
  = z 51.7–66.0 with `SD_MARGIN` carrying 1.0 mm. The post at (+21, 45.5) is what gets
  tight if it is wrong. One calliper reading retires it.
- **The USB-C port arrangement was never settled.** Today the plug enters from under the
  chin, up a 9 × 14 mm channel, into the module's socket — which needs a slim cable. The
  alternative the user raised was a cable feed-through with the module somewhere roomier.
  Asked, not answered; the current design is the plug-up-the-chin one.
- `PWR_T` (5.5 mm) is not dimensioned on the module's drawing, and the Type-C socket's
  position along its 20 mm edge is eyeballed. The pocket is cut 6.5 deep and the channel
  14 mm wide so neither can bite.
