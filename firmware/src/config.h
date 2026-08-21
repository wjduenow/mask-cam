// config.h — the knobs, in one place, with the reasoning attached.
//
// Defaults chosen for a camera sealed inside a wall-hung mask, where the two
// things that can actually hurt are HEAT (the bay is closed apart from the
// cover's vent slots) and a CARD THAT FILLS UP while nobody is watching.
#pragma once

#include <esp_camera.h>

// --- identity --------------------------------------------------------------
#define MC_HOSTNAME     "mask-cam"        // -> http://mask-cam.local/
#define MC_HTTP_PORT    80
#define MC_STREAM_PORT  81                // the stream gets its own server, see web.cpp

// --- capture ---------------------------------------------------------------
// One sensor, so the stream and the recording share a framesize. SVGA is the
// balance point: an OV3660 frame at quality 12 lands around 40 kB, which is
// ~1.4 GB/hour at 10 fps -- about 22 hours on the 32 GB card. UXGA looks
// better and fills the card in four.
#define MC_DEFAULT_FRAMESIZE  FRAMESIZE_SVGA   // 800x600
#define MC_DEFAULT_QUALITY    12               // 0 best .. 63 worst
#define MC_DEFAULT_FPS        10

// The sensor can go to QXGA (2048x1536) -- it is an OV3660, not the OV2640 the
// main README's optics section assumes. Left available, not default.
#define MC_MAX_FRAMESIZE      FRAMESIZE_QXGA

// A generous upper bound on one JPEG, so every buffer that has to hold a frame
// is sized once rather than grown mid-stream. UXGA at quality 8 peaks near
// 200 kB; QXGA near 350 kB.
#define MC_MAX_FRAME_BYTES    (400 * 1024)

// --- recording -------------------------------------------------------------
// Clips rather than one endless file: a power cut truncates the clip being
// written and nothing else. 60 s also keeps the in-memory AVI index small.
// How often an open clip is made real on the card -- header sizes patched and
// the directory entry synced. This is the worst case a power cut can cost you.
#define MC_SYNC_SECONDS       5

#ifndef MC_CLIP_SECONDS
#  define MC_CLIP_SECONDS     60
#endif
#define MC_REC_DIR            "/DCIM"

// This is a set-and-forget wall camera: it arms itself as soon as the card is
// mounted, so a power cut cannot leave it streaming happily and recording
// nothing. Turn it off here if you would rather press the button yourself.
#define MC_RECORD_ON_BOOT     true

// Ring mode -- delete the oldest clip to make room -- is ON to match. The card
// then holds a rolling window, roughly 30 hours at SVGA/10 fps, and never
// fills. This DESTROYS the oldest footage by design; the UI says so and the
// checkbox turns it off.
#define MC_DEFAULT_RING       true

// Two water marks, not one.
//   TARGET  housekeeping keeps free space above this, deleting oldest first.
//   FLOOR   the writer's hard stop, if housekeeping ever falls behind.
// Keeping them apart means deletion happens on a background task, well before
// the recorder is in trouble, instead of in the middle of a frame write.
// Overridable from the build so the ring can be exercised on demand: setting
// TARGET just below the card's free space makes it fill in seconds instead of
// thirty hours. See firmware/README.md, "Testing the ring".
#ifndef MC_FREE_TARGET_MB
#  define MC_FREE_TARGET_MB   512
#endif
#ifndef MC_FREE_FLOOR_MB
#  define MC_FREE_FLOOR_MB    256
#endif

// Deleting scans the directory, and a 29 GB card holds ~1800 clips. Doing that
// once per deletion would put a long directory walk between frames every
// minute, so a scan collects this many victims at once and the next fifteen
// deletions are free.
#define MC_RING_BATCH         16

// Frames waiting to go onto the card. MEASURED on this board: a single SD
// write in 1-bit mode usually takes a few ms but spikes to 240. With the write
// on the capture path that spike is a visible stutter in the live view, so the
// card gets its own task and this queue absorbs the spikes. Four slots at SVGA
// covers ~400 ms of stall; each slot costs one max-size frame of PSRAM.
#define MC_REC_QUEUE_SLOTS    4

// A 60 s clip at 30 fps is 1800 frames; the index is 16 bytes each. Capped so
// a runaway clip cannot eat PSRAM.
#define MC_MAX_CLIP_FRAMES    4000

// --- streaming -------------------------------------------------------------
// Each viewer needs its own copy of the frame to send. Two is plenty for a
// mask on a wall, and it bounds both PSRAM and the heat they generate.
#define MC_MAX_STREAM_CLIENTS 2

// --- motion detection -------------------------------------------------------
//
// PHASE 1: the detector ANNOTATES, it does not gate. The ring keeps recording
// everything exactly as before, and motion events are logged beside it. That
// way a badly tuned threshold costs a wrong label instead of lost footage,
// and there is a real false-positive record to tune against -- on a camera
// that ends up behind a screwed-down cover, where "try it and see" is
// expensive.
#define MC_MOTION_ENABLED     true

// 2 Hz. Measured on this board: an SVGA frame decodes at JPG_SCALE_8X in
// 39.4 ms, so this is ~7.9 % of one core when the board is otherwise idle --
// more under streaming and SD load, since it contends for the same cores.
// 1/8 is the only scale worth using: 1/4, 1/2 and 1/1 all cost ~310-340 ms
// because only 1/8 skips the IDCT.
#define MC_MOTION_HZ          2

// A block is "changed" if its mean absolute difference exceeds this. The
// field converges on 12-15 across every project that publishes a number.
#define MC_MOT_BLOCK_DIFF     12

// ...and motion is declared when at least this many blocks changed. The grid
// is 8x8 pixels over a 100x75 image, so 108 blocks; 6 is ~5.5 % of frame.
#define MC_MOT_MIN_BLOCKS     6

// The single most valuable false-positive defence there is. A 5 % brightness
// step and a person occupying 5 % of frame are IDENTICAL under summed
// difference; counting blocks separates them, and only counting blocks makes
// a ceiling possible at all. Above this share of blocks changed, it is
// lighting or the AEC, never a person.
#define MC_MOT_GLOBAL_PCT     60

// Nobody triggers on one frame. Two checks at 2 Hz is a one-second
// confirmation, which suits a room.
#define MC_MOT_CONSEC         2

// The AEC and AWB are still settling for the first several seconds, and every
// project that skips this reports false positives at startup.
#define MC_MOT_WARMUP_MS      15000

// Don't log the same person walking through as forty events.
#define MC_MOT_COOLDOWN_MS    5000

// The cheap veto. Reading the OV3660's overall average (0x56A1) costs 0.65 ms
// -- 60x less than a decode. It is one global number, useless for detection,
// which is exactly what makes it a lighting-change detector. Measured as a
// percentage because the value is LINEAR-domain: in a dark room the whole
// scale compresses into single digits, so a fixed step would be meaningless.
#define MC_MOT_LUM_PCT        20
#define MC_MOT_LUM_FLOOR      2

// Events land beside the footage, not inside MC_REC_DIR -- the ring must
// never consider the log a clip.
#define MC_MOTION_LOG         "/motion.log"
#define MC_MOTION_LOG_MAX     (512 * 1024)

// --- OTA --------------------------------------------------------------------
//
// This is the feature that decides whether the mask is a write-once device.
// The one USB-C that reaches the outside goes to the POWER module's socket,
// for charging; the ESP32's own USB is on the cam board, inside the bay,
// behind ten screws and the cover. Once assembled there is no wired path to
// this chip at all -- so over-the-air is not a convenience here, it is the
// only way firmware ever changes again.
//
// The partition table already provides for it: default_8MB.csv gives two
// 3.3 MB app slots and an otadata block, and the image is 936 kB. A failed
// upload writes only to the INACTIVE slot, so the running firmware survives.
#define MC_OTA_ENABLED        true

// Set OTA_PASSWORD in secrets.h to require one. Without it, anyone on the
// network can reflash the mask.
#define MC_OTA_PORT           3232

// --- health ----------------------------------------------------------------
// The bay is sealed apart from the vents. Above this, the UI says so.
#define MC_TEMP_WARN_C        70.0f
