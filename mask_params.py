"""Every dimension for the Gini Raksha camera conversion.  Single source of truth.

`build_mask.py`, `build_cover.py`, `build_camera_mount.py` and `build_plugs.py` all
import this, so the parts cannot drift apart.  House style follows
../sonos-nest/hardware: numbers that came from vendor CAD are marked, numbers MEASURED
off this mesh are marked, and numbers that still want a caliper carry ⚠ and are listed
in README §"Still open".

FRAME (see mask_frame.py)
    x = 0    the mask's mirror line          (+x = viewer's right)
    y = 0    the WALL PLANE.  All mask material is at y <= 0; -y is out of the wall,
             toward the subject.  So "stand-off" is just -y of the front surface, and
             "how deep may I cut" is arithmetic on y.
    z = 0    the bottom of the mask (the lower fangs);  +z up.

THE ONE IDEA
    The donor is not a thin shell -- it is 8-27 mm of solid plastic over a hollow back.
    The relief you actually see is only the outer ~3 mm.  So the bay is CARVED into that
    thickness from behind, and the apertures are bored through what is left.  Nothing is
    added to the mask's outside; nothing protrudes past y = 0 but the cover's own
    hanging pads, which are the wall standoff anyway.

DERIVED, NOT TYPED
    Every floor depth below is computed at import time by measure.py from the same
    0.5 mm sampled grid the build script checks against.  Change FRONT_WALL or a bay
    outline and the floors move with it; there is no second number to forget.
"""
from measure import standoff_min_rect, standoff_min_disc
from mask_frame import MASK_SCALE

# EVERY donor-derived length below is multiplied by MASK_SCALE; every ELECTRONICS length
# is not.  That asymmetry is the entire point of scaling: the mask grows, the hardware
# does not, so the mask gets bigger *relative to* what has to fit inside it.

# ═════════════════════════════════════════════ donor mask, MEASURED off the mesh
MASK_W, MASK_D, MASK_H = (110.42 * MASK_SCALE, 42.49 * MASK_SCALE,
                          107.38 * MASK_SCALE)
MASK_VOL_CM3 = 62.6 * MASK_SCALE ** 3

# The eyeballs.  FOUND, not typed: two spherical caps located by peak stand-off in the
# eye band, then centroid-fitted (analyze_eyes.py).  They came out symmetric to 0.09 mm
# in x and 0.01 mm in z -- that agreement is the check that the detection is real.
EYE_X = 11.39 * MASK_SCALE          # 17.33 measured at 1.5x
EYE_Z = 39.51 * MASK_SCALE          # 59.28 measured at 1.5x
EYE_STANDOFF = 36.55 * MASK_SCALE   # -y of the eyeball apex
EYE_DOME_R = 4.75 * MASK_SCALE      # beyond this the surface falls off a ~5 mm cliff into the
                          # eyelid crease.  That cliff is what makes a bore inside it
                          # read as a pupil rather than as damage.

# ═════════════════════════════════════════════ ESP32-S3-CAM  (vendor KiCad STEP)
# Identical to ../sonos-nest/hardware/cam-button/shell/button_params.py, which read them
# out of nulllaborg/esp32s3-cam's own esp32s3_cam.step.  Do not re-derive.
PCB_W, PCB_L, PCB_T = 30.4, 38.4, 1.60
# ⚠ THE BOARD IS NOT 30.4 WIDE IN USE.  With a microSD card seated, that region juts
# out to 38 mm overall -- 7.6 mm past one long edge -- and nothing in this file knew it,
# so the whole bay was laid out around a bare PCB.  The card exits the side the COMPONENT
# FACE looks away from: the board mounts component side FORWARD, and a card that exits to
# the left when you look AT the component side with the USB-C down therefore ends up at
# -x in the mask.
# MEASURED off the board's own 32 x 24 mm hole pattern in the assembly photo (2026-08-20):
# the card occupies z 51.7..66.0 and stands 6.9 mm proud.  7.6 is carried instead, being
# what the 38 mm overall implies.  ⚠ Both are photo-scaled; one calliper reading across
# the card's span would retire SD_MARGIN.
SD_OUT   = 7.6            # how far the card protrudes past the PCB's edge
SD_SIDE  = -1             # which side of the mask it protrudes toward
SD_MARGIN = 1.0           # carried against the photo-scaled z band
SD_Z0, SD_Z1 = 51.7 - SD_MARGIN, 66.0 + SD_MARGIN
SD_X     = SD_SIDE * (PCB_W / 2 + SD_OUT)     # = -22.80, the card's outer edge
HOLE_D = 3.20                   # M3 clearance, 4x
HOLE_KEEPOUT = 6.40             # concentric pad -> boss OD must stay under this
HOLE_DX, HOLE_DY = 24.0, 32.0   # the 4 holes sit at (±12, ±16)

COMP_Z_MAX = 4.96               # tallest TOP-side part (the USB-C shell), measured from
                                # the PCB BACK face -- the STEP's datum, and ours
J2_HANG = 5.55                  # deepest BOTTOM-side part (J2, the PH2.0-4)
J1_HANG = 4.53                  # J1, the battery JST -- the one we USE

# ⚠ THE DECISION THAT BUYS THE FIT.  As shipped the board is 14.5 mm tip-to-tip because
# of its pre-soldered 8-pin headers, and at 14.5 nothing fits inside this mask.  The
# headers are unused here (power arrives on USB-C or the battery JST), so they get
# FLUSH-CUT and the board collapses to what the STEP actually models:
BOARD_STACK_T = COMP_Z_MAX + J2_HANG          # = 10.51, pins snipped
BOARD_STACK_T_UNCUT = 14.5                    # what it is if you don't cut them

# ✅ SUPERSEDED BY THE BOARD IN HAND (V1.1, photographed 2026-08-18).  On this unit the
# two header rows are BARE PLATED HOLES -- nothing to snip -- and J1/J2 are unpopulated
# footprints, so the back face is flat.  The board as it sits is COMP_Z_MAX + PCB only.
# What governs the rear clearance is therefore not J2 but whatever YOU solder on:
# MEASURED 2026-08-18: 7.50 mm tip-to-tip with the two power wires soldered on.  The
# vendor CAD puts 4.96 of that in front of the PCB back face (the USB-C shell), so the
# wire tails behind it account for the rest.  This supersedes the J1_HANG guess -- there
# is no JST fitted, just wires.
BOARD_TOTAL_T   = 7.50
REAR_PROTRUSION = BOARD_TOTAL_T - COMP_Z_MAX      # = 2.54, the soldered wire tails

# ⚠ PCB OUTLINE: calipers give 30 x 40 against the CAD's 30.4 x 38.4.  The 40 is very
# likely the OVERALL length including the USB-C shell, which the CAD says overhangs the
# board edge by 1.4 mm (38.4 + 1.4 = 39.8).  The cavity is sized for the larger figure
# either way, so this costs nothing:
PCB_L_OVERALL = 40.0

# ═════════════════════════════════════════════ camera module   ⚠ NOT VERIFIED
# The vendor STEP does not model the camera (separate module on an FPC) and no
# mechanical drawing for the bundled OV2640/OV3660 mini-CCM could be sourced.  These are
# the standard 24-pin DVP mini-CCM figures.  CALIPER YOURS -- README §"Still open" #1.
# The design is deliberately insensitive to them: the module is held by a separate
# printed clamp (build_camera_mount.py, ~1 cm³, 8 min), so a mismatch costs a reprint of
# that part alone and never the mask.
CAM_BODY = 9.0            # ⚠ square lens-holder / module footprint
CAM_BODY_CLR = 0.6        # per side in the pocket
CAM_BARREL_D = 7.0        # ⚠ lens barrel OD -- this is what sets the aperture
# ✅ MEASURED 2026-08-18: 6.20 mm from the front of the lens to the back of the module.
# That is the WHOLE stack, superseding the 5.0 + 2.0 = 7.0 estimate.  How it splits
# between protruding barrel and holder body is still unmeasured, so the geometry below
# assumes the pessimistic split -- the module's front face sits on the pocket floor and
# NOTHING noses into the aperture bore.  Any real protrusion only moves the lens closer
# to the aperture, which widens the view; it can never make it worse.
CAM_MODULE_MEASURED = 6.20
CAM_BARREL_L = 4.6        # ⚠ split not measured -- see above, geometry does not rely on it
CAM_PCB_T = 1.6           # ⚠ ditto

# ═════════════════════════════════════════════ the aperture
# ONE cylinder, from the camera pocket straight out through the front surface.  It exits
# a curved surface, so the visible opening is a clean circle of exactly APERTURE_D.
#
# SITE: the brow, dead on the mirror line -- an urna / "third eye", which is an authentic
# motif on these masks rather than a hole that reads as damage.  It is also, by a factor
# of five, the best optical site on the mask: there the relief is a thin skin over the
# deep central cavity, so the lens sits ~3 mm behind the aperture instead of ~11 mm as it
# would behind an eyeball (analyze_fov.py compares all seven candidate sites).
LENS_X, LENS_Z = 0.0, 52.0 * MASK_SCALE
APERTURE_D = 7.6          # clearance over a Ø7.0 barrel.  Deliberately NOT scaled: it
                          # only has to pass the real lens, so on the 1.5x mask it is
                          # proportionally smaller and therefore harder to spot.
# At 1.5x the relief is thick enough that the module can sit anywhere behind the
# aperture -- the setback stopped being a constraint and became a choice.  3.0 mm puts
# the glass down a dark tunnel (nothing visible from the front) while the unvignetted
# cone, 2·atan((7.6/2)/3.0) = 103°, still comfortably exceeds the sensor's own field, so
# the aperture never crops the image.
LENS_SETBACK = 3.0

# The eyeballs get matching Ø7.2 bores and printed blanking plugs, purely so the face
# gains a pair of dark pupils -- symmetry is what makes the brow bore read as ornament.
EYE_PUPILS = True
EYE_PUPIL_D = 7.2 * MASK_SCALE      # cosmetic, so it scales with the face
EYE_PLUG_CLR = 0.15

# ═════════════════════════════════════════════ the bay
BAY_WALL = 3.5            # tube wall.  3.5 rather than 3.0 so that after the cover
                          # rebate eats COVER_LIP + COVER_CLR = 2.25 of it, 1.25 mm of
                          # wall still stands outside the cover.
FRONT_WALL = 3.0          # relief left in front of the bay floor.  THE load-bearing
                          # number: every floor below is "how proud is the front, minus
                          # this".
COVER_T = 2.5             # cover OUTER face lands on y = 0, so nothing protrudes

# THREE zones on the 1.5x mask, each sized from the measured surface by
# analyze_layout15.py.  At 1x there were two and they fought each other; scaling the mask
# without scaling the hardware bought enough room to give each thing its own place:
#
#   BOARD  z 26..72   the cam board, the USB-C breakout and the wiring
#   CAM    z 72..84   a narrow waist carrying the camera pocket and the FPC run
#   BATT   z 84..142  the 55 x 55 x 12 cell
#
# The waist is what lets the camera sit CLEAR of the board -- at 1x the central column
# was too short and the camera had to live underneath it.
# 23 rather than 17: the board is ±15.2 wide and fills a 34 mm zone, leaving nowhere for
# a cover screw.  At ±23 the crown still carries 16.44 mm of interior (the board needs
# 11.0) and there is 4.55 mm of clear width each side for a post column.
BAY_HW_UP,   BAY_Z0_UP,   BAY_Z1_UP   = 26.0, 30.0, 74.0
# The waist is widened to x±17 / z 69..88 so it hosts the POWER MODULE as well as the
# camera.  It has ~33 mm of interior -- far more than anywhere else, because it sits over
# the deepest part of the crown -- and the camera clamp uses only the first ~10 mm of
# that, leaving the rest free behind it.
# z 73..97 rather than 74..96: the power module is 20 mm across its short axis, and the
# 25 mm axis cannot lie along z, so a 22 mm zone left exactly zero clearance.  24 mm
# gives 1 mm each side and costs nothing -- the stand-off over the wider band is
# identical (41.41 mm).
BAY_HW_MID,  BAY_Z0_MID,  BAY_Z1_MID  = 24.0, 73.0, 97.0
# ⚠ z1 MUST NOT exceed ~136.  The crown is one continuous piece only up to z=140; at
# z=142 it has split into five separate petals.  A zone reaching z=144 put its top wall
# across those petals, and because the wall sits behind their rear surfaces it did not
# merge with them -- the exported mesh came apart into four bodies (three ~0.5 cm³
# fragments at z 144..147.5).  Petals are not structural ground.
BAY_HW_BATT, BAY_Z0_BATT, BAY_Z1_BATT = 34.0, 96.0, 158.0
# ⚠ NO NECK ZONE.  A pocket at x±8, z 144..152 was tried, to carry one cover post above
# the cell.  Above z 144 the crown is separate petals, and the pocket plus its wall
# SEVERED three of them -- the exported mesh came apart into five bodies (a 0.71 cm³ tip
# and two 0.57 cm³ side petals floating free).  The crown tip is not structural ground.
# The cover is anchored in the BOARD zone and the WAIST instead, and the cell section
# relies on foam pressure across the cell, which is how battery retention normally works.
# The breakout shares the BOARD zone, which now has 35 mm of interior to play with.
BAY_HW_LO,   BAY_Z0_LO,   BAY_Z1_LO   = BAY_HW_UP, BAY_Z0_UP, BAY_Z1_UP
BAY_CORNER_R = 6.0

FLOOR_Y_UP = -(standoff_min_rect(-BAY_HW_UP, BAY_HW_UP, BAY_Z0_UP, BAY_Z1_UP)
               - FRONT_WALL)
FLOOR_Y_LO = -(standoff_min_rect(-BAY_HW_LO, BAY_HW_LO, BAY_Z0_LO, BAY_Z1_LO)
               - FRONT_WALL)
# The CAM waist's floor is NOT pushed to the relief limit -- it only has to sit behind
# the camera clamp, which is itself derived from the module.  Taking it to the limit
# drove the clamp seat into the relief.
FLOOR_Y_MID_LIMIT = -(standoff_min_rect(-BAY_HW_MID, BAY_HW_MID,
                                        BAY_Z0_MID, BAY_Z1_MID) - FRONT_WALL)
FLOOR_Y_BATT = -(standoff_min_rect(-BAY_HW_BATT, BAY_HW_BATT, BAY_Z0_BATT, BAY_Z1_BATT)
                 - FRONT_WALL)

INTERIOR_UP = -FLOOR_Y_UP - COVER_T
INTERIOR_LO = -FLOOR_Y_LO - COVER_T

INTERIOR_BATT = -FLOOR_Y_BATT - COVER_T


# NOTE: FLOOR_Y_MID is defined in the camera section below (it derives from the clamp
# seat, which derives from the module), so ZONES is assembled at the very bottom of this
# file rather than here.


# ═════════════════════════════════════════════ the cell  (MEASURED by the user)
# A 55 x 55 x 12 pouch.  It does not fit the 1x mask anywhere -- this is the feature the
# 1.5x scale bought.  Retained by a printed strap across two posts rather than glue, so
# it can be replaced: LiPo pouches swell with age and a glued-in cell is a dead mask.
CELL_W, CELL_H, CELL_T = 55.0, 55.0, 12.0
CELL_CLR = 1.5            # per side in the pocket
CELL_CZ = (BAY_Z0_BATT + BAY_Z1_BATT) / 2   # = 127
# No strap posts: the cell pocket fills the battery zone, so there is nowhere to put
# them.  A pouch is retained by foam pressure under the cover -- and deliberately NOT
# glued, because LiPos swell with age and a glued-in cell is a dead mask.

# ═════════════════════════════════════════════ power module  ⚠ DIMENSIONS NOT VERIFIED
# DWEII Type-C 5 V 2 A boost + 2.4 A charge + protection, with an LED display.  One board
# replaces the passive breakout AND a separate charger: USB-C in charges the cell, the
# boost output feeds the cam board's J4 `5V`/`GND`, so nothing depends on the cam board's
# own power path (which has no charger -- measured, VBAT reads 0 V with USB connected).
#
# ✅ DIMENSIONS VERIFIED from the manufacturer's own dimension drawing (Amazon listing
# image 61U6muDgZEL): the board is 25 x 20 mm, with a 13 mm notched section.  This
# supersedes the 27 x 17 x 8 guess -- it is 3 mm WIDER and 2 mm shorter than assumed.
#
# Thickness is NOT dimensioned on that drawing.  The tallest parts are the Type-C
# receptacle (~3.2) and the shielded inductor, on a ~1.2 mm PCB, so ~4.5-5.0; 5.5 is
# carried with margin.  There is no USB-A socket -- the output is solder pads marked
# `5V`, which is why it is thin.  ⚠ Caliper the thickness if you want the number exact;
# the waist has 35 mm of interior so it cannot plausibly bind.
# SOURCE: amazon.com/dp/B09YD5C9QC (DWEII, 10-pack).  The drawing above is that
# listing's image 61U6muDgZEL, saved here as dweii_spec.jpg.  The Type-C socket sits on
# a 20 mm edge; the 13 mm notch is on a 25 mm edge, and nothing is mounted through it --
# the board has NO mounting holes, which is why it is cradled rather than screwed.
PWR_W, PWR_H, PWR_T = 25.0, 20.0, 5.5
PWR_CLR = 1.0
PWR_NOTCH = 13.0          # the notched section, on one 25 mm edge
CELL_POCKET_W = CELL_W + 2 * CELL_CLR
CELL_POCKET_H = CELL_H + 2 * CELL_CLR

# ═════════════════════════════════════════════ battery shim
# The pouch rests on the battery zone's floor and its back face lands well short of the
# cover, so with nothing between them the cell is free to move 9 mm before the cover
# stops it.  The shim is what "foam pressure under the cover" was a note-to-self for.
#
# DERIVED, not typed: floor + cell = where the cell's back face is, and the cover's inner
# face is at -COVER_T.  The difference is the shim.  ⚠ CELL_T is the pouch's NOMINAL
# thickness; caliper yours and change it here rather than scaling the STL.
CELL_BACK_Y  = FLOOR_Y_BATT + CELL_T                   # = -11.70
BATT_SHIM_T  = -COVER_T - CELL_BACK_Y                  # =   9.20, the gap it fills
# Footprint: MEASURED clear opening of the battery bay is |x| <= 32.25 over z 98..156.
BATT_SHIM_W, BATT_SHIM_Z0, BATT_SHIM_Z1 = 62.0, 99.0, 155.0
BATT_SHIM_R = BAY_CORNER_R                             # matches the bay's own corners
BATT_SHIM_WALL = 1.6      # face plate, perimeter and ribs -- 4 perimeters at 0.4
BATT_SHIM_GRIP = 4.0      # how far the two side walls reach past the cell's back face
BATT_SHIM_CLR = 0.5       # per side between those walls and the cell
BATT_SHIM_NOTCH = 16.0    # wire gate through both end walls

# ═════════════════════════════════════════════ camera pocket (in the upper zone)
CAM_WALL = 2.5            # relief left around the pocket
CAM_POCKET = CAM_BODY + 2 * CAM_BODY_CLR       # 10.2 square, rounded
CAM_POCKET_R = 2.5
LENS_SITE_STANDOFF = standoff_min_disc(LENS_X, LENS_Z, 1.0)

# The pocket goes as deep as the relief allows -- DERIVED, so it is automatically the
# most forward position that still keeps CAM_WALL of skin on the front.
CAM_POCKET_Y = -(standoff_min_rect(LENS_X - CAM_POCKET / 2, LENS_X + CAM_POCKET / 2,
                                   LENS_Z - CAM_POCKET / 2, LENS_Z + CAM_POCKET / 2)
                 - CAM_WALL)

# The clamp lies in a seat milled into the bay floor so it finishes FLUSH with it,
# instead of standing 2.5 mm proud and fouling the board 1 mm above.  Run vertically
# (tall and narrow) so it passes between the board's two Ø6 corner bosses at x = ±12
# rather than undercutting them.
CAM_SEAT_HW = 8.0
CAM_SEAT_Z0, CAM_SEAT_Z1 = LENS_Z - 11.0, LENS_Z + 11.0
CAM_SEAT_DEPTH = 2.6
CAM_SEAT_R = 3.0
CAM_CLAMP_T = 2.5
CAM_MOUNT_PILOT = 2.0     # M2.5 self-tapper holds the clamp
CAM_MOUNT_DZ = 8.0        # pilot offset from the lens, on the mirror line
CAM_MOUNT_DEPTH = 5.0

# ⚠ THE SEAT IS SHORTER THAN IT LOOKS, and this is the number the clamp is cut to.
# CAM_SEAT_Z1 asks for 102, but the BATTERY zone's floor (FLOOR_Y_BATT = -23.70) crosses
# this z at BAY_Z1_MID = 97 and sits 20 mm BEHIND the seat.  Everything the seat cutter
# removes above z = 97 is therefore a sealed void 20 mm inside solid plastic -- and the
# upper clamp pilot went into it.  MEASURED on the printed mask_cam.stl: the reachable
# seat is x +/-8.00, z 80.02..97.00, floor y -43.95, and there is exactly ONE pilot,
# at z = 83.00.  Both the mask cutter and the clamp now derive from this, so a rebuilt
# mask stops cutting the void and the clamp fits the mask that is already printed.
CAM_SEAT_Z1_OPEN = min(CAM_SEAT_Z1, BAY_Z1_MID)        # = 97.0, the reachable end
CAM_MOUNT_Z = [LENS_Z - CAM_MOUNT_DZ]                  # = [83.0], the reachable pilot

# What the module actually gets, and therefore the field of view.  Stated as a RANGE
# because the module's own geometry is the ⚠ unverified part: a flat-faced module ends
# up at the back of the aperture bore, one with a protruding barrel noses down it.
# DERIVE the seat from the MODULE, not from the bay floor.  Anchoring it to the floor
# made the two fight: the waist floor is set by the relief, the pocket floor by the
# relief at the aperture, and the gap between them landed at 1.48 mm against the 7.00 the
# module needs.  Deriving forwards -- pocket floor, plus the module, plus the clamp --
# makes the geometry follow the hardware instead.
CAM_MODULE_DEPTH = CAM_MODULE_MEASURED             # = 6.20, measured
CAM_SEAT_Y = CAM_POCKET_Y + CAM_MODULE_DEPTH + 0.5
FLOOR_Y_MID = CAM_SEAT_Y + CAM_SEAT_DEPTH
INTERIOR_MID = -FLOOR_Y_MID - COVER_T
# What the lens actually gets, now that the module's depth is measured:
#   MAX = the module's face flat on the pocket floor, nothing in the bore (pessimistic)
#   MIN = its barrel nosed the full 4.6 mm up the Ø7.6 bore (optimistic)
LENS_SETBACK_MAX = LENS_SITE_STANDOFF + CAM_POCKET_Y
LENS_SETBACK_MIN = max(0.5, LENS_SETBACK_MAX - CAM_BARREL_L)

# ═════════════════════════════════════════════ board placement
# Component side faces FORWARD (toward the face): the camera FPC connector is on that
# side and has to reach the brow, and it leaves J1 (the battery JST) facing the cover so
# the battery can be unplugged without disturbing the board.
BOARD_CX, BOARD_CZ = 0.0, 52.0        # spans z 41.8 .. 80.2: 5.8 mm clear of the bay's
                                      # bottom step and 3.8 mm clear of the top posts
# Air between the board's tallest top-side part and the bay floor.  2.5 rather than a
# token 1.0 because this gap is also the RIBBON PLENUM: the camera ships on a 75 mm FPC
# against a ~18 mm path, so ~57 mm of excess has to fold somewhere, and it cannot be
# trimmed (the gold fingers are the termination).  1.0 lets the ribbon lie flat; it does
# not let it fold.  2.5 gives a 30 x 38 mm plenum across the board's whole footprint,
# which swallows three folded layers with bend radius to spare.  Affordable because the
# board came in thinner than budgeted -- its bottom-side connectors are unpopulated.
BOARD_FRONT_CLR = 2.5
BOARD_BACK_Y = FLOOR_Y_UP + BOARD_FRONT_CLR + COMP_Z_MAX
# The face the board actually RESTS on is its component side, not its back: the bosses
# come up from the floor and touch the PCB's front face inside each Ø6.4 keep-out ring,
# and the screw enters from the cover side.  Topping the bosses out at BOARD_BACK_Y --
# as this file did until 2026-08-18 -- made them exactly PCB_T too tall, so they reached
# through the board and would have held it 1.6 mm further back than every other number
# here assumes.
BOARD_SEAT_Y = BOARD_BACK_Y - PCB_T
BOSS_H = BOARD_SEAT_Y - FLOOR_Y_UP

# ═════════════════════════════════════════════ fasteners -- all thread-forming into
# bare printed plastic, same hardware as ../sonos-nest/hardware.  No nuts, no inserts.
BOSS_OD = 6.0             # < HOLE_KEEPOUT (6.4)
BOSS_PILOT = 2.6
BOARD_SCREW_LEN = 6.0     # M3 × 6 flat head

POST_OD = 6.5
POST_PILOT = 2.6
POST_RIB = 2.5             # web tying each post into the bay's side wall
COVER_SCREW_LEN = 8.0     # M3 × 8 flat head
COVER_SCREW_D = 3.4
COVER_CSK_D = 6.0         # must sit flush: this face is what meets the wall
COVER_CSK_ANG = 90.0
# Posts live where the board is not -- below it and above it.  x is bounded by the
# zone's own inner width minus the post radius.
# Lower pair at z=26, as low as a Ø6.5 post can sit inside a bay starting at z=22.  The
# breakout stands on edge ABOVE them, in the z 29..35 band.
# The -x lower post moves inboard to x=-1.5: the USB-C breakout stands on edge at
# x -11.0 .. -6.25 and anything further out sits inside it.  +9.5 is already clear.
# BOARD zone takes four; the NECK takes the fifth.  The battery zone takes none -- the
# cell fills it -- so the cover is anchored either side of the cell and relies on foam
# pressure across it.
# Four beside the board, two in the waist, and two flanking the cell.  The battery pair
# uses a SMALLER post (POST_OD_BATT) because the 58 mm cell pocket leaves only 5 mm of
# clear width each side of it -- a Ø6.5 column would foul the cell.
# ⚠ THREE THINGS COMPETE FOR THIS ZONE and the old layout lost to two of them silently,
# because build_mask.py deleted every post before anything could measure the collision:
#
#   * the EYE PUPILS bore through at (±19.93, 69.14), Ø12.6.  Posts at (±21, 68) sat
#     1.56 mm off that axis -- entirely INSIDE the bore -- and capped both pupils.  A post
#     needs EYE_PUPIL_D/2 + POST_OD/2 = 9.55 mm of centre distance to clear one.
#   * the USB-C BREAKOUT stands on edge against the -x wall over z 26.5..41.  A post at
#     (-21, 36) went straight through it, and the free gaps either side of that post were
#     1.75 and 2.55 mm against a board 4.75 mm thick.  So the -x side gives up its lower
#     post: the breakout is worth more there than a fifth anchor.
#   * the cam BOARD fills x ±15.2 over z 32.8..71.2, which is why every post is outboard
#     of |x| = 18.45.
#
# What is left: z 44.25..59.65 is the only window on the -x side that clears both the
# breakout below and the pupil above.  check_clearances() now asserts all three.
# The board zone now has three claimants per wall, not two.  On -x the SD card owns
# z 50.7..67.0; on +x the cradle owns z 29..54.5.  Once the pupils are cleared too, what
# is left is z <= 47.5 on the -x wall and a ~2 mm window around z 59 on the +x wall.
POST_XY = [(-21.0, 36.0), (-21.0, 45.5), (21.0, 59.0),
           (-20.0, 79.5), (20.0, 79.5)]
POST_XY_BATT = [(-31.5, 112.0), (31.5, 112.0), (-31.5, 142.0), (31.5, 142.0)]
POST_OD_BATT = 5.0

# ═════════════════════════════════════════════ DWEII module mount
# ⚠ THERE IS NO USB-C BREAKOUT IN THIS BUILD, and a whole mount was cut for one before
# anybody checked.  This file used to carry a UC_* block for a SparkFun-pattern "USB C
# Breakout" v10 -- 21.4 x 14.5 x 4.75, two M3 holes 16.85 apart -- carried over from
# ../sonos-nest/hardware/jukebox-7.  README §7 had already replaced that part with the
# DWEII module (one board does breakout AND charger), and the part actually in hand is
# the DWEII: amazon.com/dp/B09YD5C9QC, whose own dimension drawing is dweii_spec.jpg in
# this directory.  The breakout's numbers are gone; everything here derives from PWR_*.
#
# WHERE IT SITS.  Low in the BOARD zone, on edge against the -x wall, its Type-C mouth
# pointing DOWN at a channel through the back of the chin -- not in the waist at
# PWR_CZ = 78, which has no route to the outside for a plug.  Standing it here also
# leaves the waist free for the camera's ribbon to fold in.
#
# ⚠ TWO NUMBERS ARE STILL SOFT, and the slot is sized so neither can bite:
#   * PWR_T (5.5) is not dimensioned on the drawing -- the slot is cut 6.3 deep, so
#     anything up to 6.3 mm thick drops in;
#   * the Type-C socket's position along the module's 20 mm edge is eyeballed off the
#     drawing at roughly centred -- the port slot is 14 mm wide for a ~9 mm socket, so
#     it can sit up to 2.5 mm either side of centre and still line up.
# No pad and no pilots: the module has no mounting holes, so the bay's own -x wall IS
# the slot's back face.  That buys 3.0 mm of x back, which is what lets the retaining
# lips exist at all without crowding the cam board.
# ⚠ ON THE +x WALL, and that is the SD card's doing.  The cradle sat on -x until the
# card turned up: it owns x -26.0..-18.5 over z 29..54.5, and the card reaches -22.80 over
# z 50.7..67.0, so the two overlapped by 4.3 mm in x and 3.8 mm in z.  The card cannot
# move -- it is where the board's own slot puts it -- so the cradle did.
PWR_SIDE    = -SD_SIDE                        # = +1, the wall the card does NOT use
PWR_FACE_X  = PWR_SIDE * BAY_HW_UP            # = +26.0, the slot's back face
PWR_SLOT_T  = PWR_T + 0.8                     # =   6.3, slot depth across x
PWR_SLOT_H  = PWR_H + 0.8                     # =  20.8, slot width across y
PWR_LIP     = 1.2         # how far the slot's lips overhang, to hold the board in
PWR_X_SLOT  = PWR_FACE_X - PWR_SIDE * PWR_SLOT_T      # = +19.70, the slot's inboard face
PWR_X_LIP   = PWR_X_SLOT - PWR_SIDE * PWR_LIP         # = +18.50, the retaining lid
# The module's 20 mm axis spans the bay's DEPTH, its rear edge against the cover, so the
# cover traps it once fitted.  Its 25 mm axis runs up z from the shelf it rests on.
PWR_SLOT_Y1 = -COVER_T                        # = -2.50, hard against the cover
PWR_SLOT_Y0 = PWR_SLOT_Y1 - PWR_SLOT_H        # = -23.30
PWR_SHELF_Z = BAY_Z0_UP - 1.0                 # = 29.0, what the board's lower edge sits on
PWR_SLOT_Z1 = PWR_SHELF_Z + PWR_W + 0.5       # = 54.5, and it slides in from above
# The plug's channel, below the shelf: wider than the socket in y so its exact place on
# the edge does not matter, and deeper in x than the slot because nothing competes with
# it down here -- the cam board does not start until z = 32.8.
PWR_PORT_W  = 14.0        # across y
PWR_PORT_T  = 9.0         # across x, room for a plug's overmould
PWR_PORT_CY = (PWR_SLOT_Y0 + PWR_SLOT_Y1) / 2 # = -12.90, the socket's assumed centre
# +0.5 rather than -0.5: at x = -26.0 the chin leaves 2.96 mm of relief at z = 19 and
# FRONT_WALL wants 3.00, so the channel starts just inboard of the slot's back face.
# ⚠ That costs the plug's OVERMOULD ~0.9 mm on its outboard side.  A slim USB-C cable
# fits; a chunky moulded one may not, and the answer is a slimmer cable, not a deeper
# channel -- the chin is what is left of the mask's jaw here.
PWR_PORT_XA = PWR_FACE_X - PWR_SIDE * 0.5             # = +25.50
PWR_PORT_XB = PWR_PORT_XA - PWR_SIDE * PWR_PORT_T     # = +16.50
PWR_PORT_Z0 = 14.0        # how far down the chin the channel is opened.  MEASURED: this
                          # leaves 17.5 mm of relief at its thinnest -- back of the chin,
                          # nowhere near the face.

# ═════════════════════════════════════════════ cover
COVER_LIP = 2.0           # how far the rebate eats the 3.0 wall, leaving 1.0 outside
COVER_CLR = 0.25          # per side: it drops in, it is not a press fit
COVER_CORNER_R = BAY_CORNER_R + COVER_LIP

# ═════════════════════════════════════════════ lower bay -- POWER ENTRY, not a battery
# Measured on the board in hand: with USB connected and no cell fitted the VBAT pad reads
# 0 V, so nothing drives it and there is NO CHARGER.  A battery would run the unit but
# could never recharge in place, which is useless on a wall, so this unit is USB-only and
# the lower zone is simply where power arrives and the cable turns.
#   26 x 14 x 21.9 mm = 8 cm^3, with 23.9 mm between the board's USB-C face and the slot
#   -> takes a right-angle plug (10 x 12 x 7), a straight plug (22 x 10 x 6.5), or a
#      USB-C breakout soldered to J4 pin 1 (5V) + pin 2 (GND).
POWER_BAY_W = 2 * BAY_HW_LO - 2.0
POWER_BAY_H = BAY_Z1_LO - BAY_Z0_LO - 2.0

# ═════════════════════════════════════════════ cable exit
# A slot through the bay's LOWER wall, so a USB-C pigtail drops into the mask's own
# hollow below z=22 and leaves through the open bottom -- inside the mask the whole way,
# and invisible from every angle.
CABLE_SLOT_W = 7.0
CABLE_SLOT_H = 4.0

# ═════════════════════════════════════════════ hanging
# Pads on the cover's OUTER face.  They are the only thing touching the wall, so they are
# also the standoff -- and being 3.2 mm proud they give a keyhole screw head room to sit.
# Two blind feet lower down stop it rocking.
# The keyhole is an UNDERCUT in the pad, not a hole through the cover: a through
# keyhole would put the screw head inside the bay, where the board is.  So the pad is
# 5 mm proud, its lower 2.8 mm is a wide stadium the head drops into, and the outer
# 2.2 mm is a lip with only a shank-wide slot in it.  Slide down, head captured, bay
# never breached.
HANG_PAD_H = 5.0
HANG_PAD_W, HANG_PAD_L = 12.0, 18.0
HANG_XY = [(-11.0 * MASK_SCALE, 71.0 * MASK_SCALE),
           (11.0 * MASK_SCALE, 71.0 * MASK_SCALE)]
KEYHOLE_HEAD_D = 7.5      # a #6 or M4 pan head passes this
KEYHOLE_SHANK_D = 4.2
KEYHOLE_DROP = 5.0        # how far the mask slides down onto the screw
KEYHOLE_ENTRY_DZ = 3.0    # entry circle sits this far BELOW the pad centre
KEYHOLE_CAP_T = 2.2       # the capturing lip

# One central foot low down completes a 3-point stance; two would collide with the
# lower cover screws.
FOOT_XY = [(0.0, 27.0 * MASK_SCALE)]
FOOT_W, FOOT_L = 12.0, 10.0

# ═════════════════════════════════════════════ cover vents
# The bay is otherwise sealed, and MJPEG streaming runs the S3 hard.  The cover faces the
# wall, so holes there cost nothing visually -- it is the one surface where venting is
# free.
#
# Placed as a CHIMNEY, not as decoration: an intake bank below the board and an exhaust
# bank above it, so convection has somewhere to go once the mask hangs vertically.  A
# third bank sits over the waist, where the DWEII boost converter dissipates at 2 A.
#
# ⚠ NOTHING over the cell (z 98..156).  Vents there would draw warm air across the LiPo,
# which is the component least happy about heat, and would expose it to debris.
VENT_W = 2.6              # slot width -- 2.6 prints cleanly and resists dust ingress
VENT_L = 26.0             # slot length; stays inside |x| < 16.8 to clear the x=±21 posts
VENT_R = VENT_W / 2
VENT_BANKS = {
    # ⚠ not below z 33: the cover's own bottom edge is at z 29.5, and a slot at 31.0 left
    # 0.2 mm of plastic to it -- a sliver that breaks off in the peel.  verify_cover.py
    # now asserts an edge margin, which is what caught it.
    "intake (below the board)": [33.0, 36.0, 39.0],
    "exhaust (above the board)": [65.5, 69.0, 72.5],
    "waist (the boost module)": [82.0, 86.0, 90.0],
}

SEG = 96                  # cylinder smoothness


def summary():
    import numpy as np
    fov_lo = 2 * np.degrees(np.arctan((APERTURE_D / 2) / LENS_SETBACK_MAX))
    fov_hi = 2 * np.degrees(np.arctan((APERTURE_D / 2) / LENS_SETBACK_MIN))
    return "\n".join([
        f"  bay UPPER  x±{BAY_HW_UP}  z {BAY_Z0_UP}..{BAY_Z1_UP}   "
        f"floor y={FLOOR_Y_UP:7.2f}   interior {INTERIOR_UP:5.2f} mm",
        f"  bay LOWER  x±{BAY_HW_LO}  z {BAY_Z0_LO}..{BAY_Z1_LO}   "
        f"floor y={FLOOR_Y_LO:7.2f}   interior {INTERIOR_LO:5.2f} mm",
        f"  board      back face y={BOARD_BACK_Y:7.2f}   bosses {BOSS_H:5.2f} mm tall",
        f"  camera     pocket floor y={CAM_POCKET_Y:7.2f}   "
        f"{CAM_MODULE_DEPTH:4.1f} mm for the module",
        f"             Ø{APERTURE_D} aperture, lens {LENS_SETBACK_MIN:.1f}"
        f"..{LENS_SETBACK_MAX:.1f} mm behind it -> {fov_lo:.0f}°..{fov_hi:.0f}° cone",
        f"  power bay  {POWER_BAY_W:.0f} × {POWER_BAY_H:.0f} × {INTERIOR_LO:.1f} mm "
        f"(USB entry; no battery -- board has no charger)",
    ])


if __name__ == "__main__":
    print(summary())


# The bay as a list, so build_mask.py iterates instead of hard-coding zone pairs.
# (half-width, z0, z1, floor_y, name)
ZONES = [
    (BAY_HW_UP,   BAY_Z0_UP,   BAY_Z1_UP,   FLOOR_Y_UP,   "BOARD"),
    (BAY_HW_MID,  BAY_Z0_MID,  BAY_Z1_MID,  FLOOR_Y_MID,  "CAM"),
    (BAY_HW_BATT, BAY_Z0_BATT, BAY_Z1_BATT, FLOOR_Y_BATT, "BATT"),
]


def zone_of(z):
    """Which zone contains this z (first match), for rooting posts and pilots."""
    for hw, z0, z1, fl, name in ZONES:
        if z0 - 1e-9 <= z <= z1 + 1e-9:
            return hw, z0, z1, fl, name
    raise ValueError(f"z={z} is outside every bay zone")
