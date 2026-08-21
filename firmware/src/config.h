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

// --- health ----------------------------------------------------------------
// The bay is sealed apart from the vents. Above this, the UI says so.
#define MC_TEMP_WARN_C        70.0f
