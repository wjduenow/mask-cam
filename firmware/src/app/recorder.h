// recorder.h — the microSD side: mount it, write MJPEG AVI clips to it, and
// be honest about how it is coping.
#pragma once

#include <Arduino.h>
#include <stdint.h>

struct RecStats {
  bool     mounted;
  bool     armed;
  char     clip[64];      // filename currently being written, "" if idle
  uint32_t clip_frames;
  uint64_t clip_bytes;
  uint32_t clips_written;
  uint32_t clips_deleted;  // by ring mode, since boot
  uint32_t frames_dropped; // frames the card could not keep up with
  uint8_t  queue_depth;    // slots in use right now
  uint32_t write_ms_max;   // worst single write, ever -- a bad card shows up here
  uint32_t write_ms_last;
  uint64_t card_total_mb;
  uint64_t card_free_mb;
  bool     ring;           // delete oldest clip to make room?
  bool     paused_for_space; // stopped because the card filled; will resume
  char     last_error[96];
};

bool recorder_begin();               // mount the card (1-bit; it is the only mode wired)
bool recorder_arm();                 // start a clip
void recorder_disarm();              // finish the clip and close it cleanly
bool recorder_armed();
void recorder_set_ring(bool on);

void recorder_start_writer();        // the task that owns the card
void recorder_start_housekeeper();   // the task that keeps room on the card

// Called by the capture pump for every frame. Copies into a queue slot and
// returns immediately -- the card is slow and bursty, and the camera must not
// be made to wait for it. Returns false if the queue was full, which is the
// honest signal that the card cannot keep up with the chosen fps.
bool recorder_queue_frame(const uint8_t *jpeg, size_t len, uint16_t w, uint16_t h, uint8_t fps);

void recorder_stats(RecStats *out);
void recorder_refresh_space();       // re-reads free space; not free, so not per frame

// Directory listing for the web UI. Returns a JSON array as a String.
String recorder_list_json();
bool   recorder_delete(const char *name);

// USB console helpers. This board ends up behind a screwed-down cover, so
// everything the web UI can do has to be reachable over the wire too -- a
// mask that can only be talked to over WiFi is a mask you cannot debug the
// day WiFi is the thing that broke.
// --- motion annotation -----------------------------------------------------
// Phase 1: motion is LOGGED beside the footage, never used to gate it. The
// recorder owns the card, so it owns the log too -- and it is the only thing
// that knows which clip is open and how far into it we are, which is what
// makes an event point at footage rather than at a wall-clock time.
void recorder_note_motion(uint16_t changed, uint16_t total, uint8_t lum,
                          char *desc_out, size_t desc_len);
String recorder_motion_json(int limit);
void   recorder_clear_motion_log();

void recorder_print_listing();
bool recorder_newest_clip(char *out, size_t n);
bool recorder_dump_base64(const char *name);
