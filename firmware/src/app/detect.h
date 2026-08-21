// detect.h — motion detection that annotates rather than gates.
//
// Phase 1 deliberately does NOT control recording. The ring keeps everything;
// this only says "something happened at 15:44:12, twelve blocks changed, in
// clip 001300000". A wrong threshold costs a wrong label, never footage.
//
// Everything here was sized from measurements on this board, not from the
// literature -- see firmware/README.md and the `bench` environment.
#pragma once

#include <Arduino.h>

struct MotStats {
  bool     enabled;
  bool     running;
  uint32_t checks;          // decodes performed
  uint32_t events;          // motion events logged, since boot
  uint32_t rejected_global; // suppressed as a lighting change
  uint16_t last_blocks;     // blocks changed on the last check
  uint16_t total_blocks;    // ...out of this many
  uint16_t last_decode_ms;
  uint8_t  last_lum;        // OV3660 0x56A1
  bool     last_global;     // was the last check a whole-scene change?
  uint32_t last_event_ms;   // millis() of the last logged event
  char     last_event[80];  // human-readable
};

bool motion_begin();
void motion_start_task();
void motion_stats(MotStats *out);
void motion_set_enabled(bool on);

// Tunables, adjustable at runtime so thresholds can be found without
// unscrewing the cover.
void motion_set_params(int block_diff, int min_blocks, int global_pct, int hz);
void motion_get_params(int *block_diff, int *min_blocks, int *global_pct, int *hz);
