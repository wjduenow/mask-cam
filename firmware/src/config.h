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
#define MC_CLIP_SECONDS       60
#define MC_REC_DIR            "/DCIM"

// Stop recording with this much left, so the filesystem never runs to zero
// while a write is in flight.
#define MC_FREE_FLOOR_MB      256

// Ring mode -- delete the oldest clip to make room -- is OFF by default. A
// camera that quietly destroys yesterday's footage to record today's is a
// reasonable thing to want and a terrible thing to do without being asked.
// Toggle it in the web UI.
#define MC_DEFAULT_RING       false

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
