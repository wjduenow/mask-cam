// recorder.cpp — MJPEG AVI clips onto the microSD.
//
// Why AVI and not a folder of JPEGs: a clip you can double-click is worth a
// great deal more than 36 000 numbered stills, and MJPEG-in-AVI is the one
// container you can write straight out of a camera with no encoder, no
// timestamps to interpolate and no library. Every frame the sensor hands over
// is already a complete JPEG; the container is a header, the frames, and an
// index bolted on the end.
//
// The awkward part is that AVI wants sizes it cannot know until the file is
// finished -- total length, index offsets, frame count. So the header goes
// down as zeroes, the frames follow, and close_clip() seeks back and patches
// it. A clip that is never closed (power cut mid-write) keeps its zeroed
// header and will not play: that is why this records CLIPS and not one long
// file, so the blast radius of a power cut is the last minute, not everything.

#include "recorder.h"
#include "../config.h"

#include <SD_MMC.h>
#include <time.h>
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <Preferences.h>

#include "../board_pins.h"

// --- AVI layout ------------------------------------------------------------
// Offsets into the 224-byte header. Named rather than magic so the patching
// at the end of the clip is readable.
static const size_t AVI_HDR_LEN        = 224;
static const size_t OFF_RIFF_SIZE      = 4;    // filesize - 8
static const size_t OFF_USEC_PER_FRAME = 32;
static const size_t OFF_MAX_BYTES_SEC  = 36;
static const size_t OFF_FLAGS          = 44;
static const size_t OFF_TOTAL_FRAMES   = 48;
static const size_t OFF_SUGG_BUF       = 60;
static const size_t OFF_WIDTH          = 64;
static const size_t OFF_HEIGHT         = 68;
static const size_t OFF_STRH_RATE      = 132;
static const size_t OFF_STRH_LENGTH    = 140;
static const size_t OFF_STRH_SUGG_BUF  = 144;
static const size_t OFF_BI_WIDTH       = 176;
static const size_t OFF_BI_HEIGHT      = 180;
static const size_t OFF_BI_SIZEIMAGE   = 192;
static const size_t OFF_MOVI_SIZE      = 216;  // LIST size covering 'movi' + frames
static const size_t MOVI_LIST_POS      = 220;  // where the 'movi' FOURCC sits

static RecStats st;
static File     clip;
static uint8_t *index_buf = nullptr;   // 16 bytes per frame, in PSRAM
static uint32_t index_n   = 0;
static uint32_t clip_started_ms = 0;
static uint32_t last_sync_ms = 0;
static uint32_t space_checked_ms = 0;
static portMUX_TYPE st_mux = portMUX_INITIALIZER_UNLOCKED;

static void fail(const char *fmt, ...) {
  va_list ap; va_start(ap, fmt);
  vsnprintf(st.last_error, sizeof(st.last_error), fmt, ap);
  va_end(ap);
  Serial.printf("[rec] %s\n", st.last_error);
}

static inline void wr32(uint8_t *p, uint32_t v) {
  p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}
static inline void wr16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static inline void fourcc(uint8_t *p, const char *s) { memcpy(p, s, 4); }

// Build the fixed part of the header. Everything the clip cannot know yet is
// left zero and patched by close_clip().
static void build_header(uint8_t *h, uint16_t w, uint16_t hgt, uint8_t fps) {
  memset(h, 0, AVI_HDR_LEN);

  fourcc(h + 0,  "RIFF");                     // [4] size patched later
  fourcc(h + 8,  "AVI ");
  fourcc(h + 12, "LIST");
  wr32  (h + 16, 192);                        // hdrl payload
  fourcc(h + 20, "hdrl");

  fourcc(h + 24, "avih");
  wr32  (h + 28, 56);
  wr32  (h + OFF_USEC_PER_FRAME, 1000000UL / (fps ? fps : 1));
  // AVIF_HASINDEX is deliberately NOT set here. It goes on at close, once the
  // index actually exists -- so a clip cut short by a power failure does not
  // advertise an index that was never written.
  wr32  (h + 56, 1);                          // one stream
  wr32  (h + OFF_WIDTH,  w);
  wr32  (h + OFF_HEIGHT, hgt);

  fourcc(h + 88, "LIST");
  wr32  (h + 92, 124);                        // strl payload
  fourcc(h + 96, "strl");

  fourcc(h + 100, "strh");
  wr32  (h + 104, 56);
  fourcc(h + 108, "vids");
  fourcc(h + 112, "MJPG");
  wr32  (h + 128, 1);                         // dwScale
  wr32  (h + OFF_STRH_RATE, fps);             // dwRate / dwScale = fps
  wr32  (h + 148, 0xFFFFFFFF);                // dwQuality: not specified
  wr16  (h + 158, w);                         // rcFrame right
  wr16  (h + 160, hgt);                       // rcFrame bottom

  fourcc(h + 164, "strf");
  wr32  (h + 168, 40);
  wr32  (h + 172, 40);                        // biSize
  wr32  (h + OFF_BI_WIDTH,  w);
  wr32  (h + OFF_BI_HEIGHT, hgt);
  wr16  (h + 184, 1);                         // biPlanes
  wr16  (h + 186, 24);                        // biBitCount
  fourcc(h + 188, "MJPG");                    // biCompression

  fourcc(h + 212, "LIST");                    // [216] movi size patched later
  fourcc(h + MOVI_LIST_POS, "movi");
}

// --- naming, and why every clip carries a number ---------------------------
//
// Ring mode deletes the oldest clip, so "which is oldest" has to be answerable
// at all times, including the twenty seconds after every boot when WiFi has
// not connected and there is no clock. Neither obvious answer survives that:
//
//   by filename   two schemes coexist, and "20260821-055559.avi" sorts BELOW
//                 "clip0001.avi" because '2' < 'c' -- the ring would eat the
//                 newest footage first.
//   by mtime      clips written before NTP answers carry 1970, so the first
//                 clip of EVERY boot looks like the oldest thing on the card
//                 and is deleted first. That is the moment the power came
//                 back, which is often the moment you wanted.
//
// So each clip gets a monotonic sequence number of its own, ahead of the
// timestamp: boot count from NVS, times 100000, plus the clip index within
// this boot. Names then sort chronologically by plain strcmp forever, with or
// without a clock, and nothing has to open a file to find out how old it is.
//
//   000200017_20260821-055559.avi    boot 2, clip 17, clock known
//   000200000_noclock.avi            boot 2, clip 0, before NTP answered
//
// One NVS write per boot, not per clip -- a counter bumped 1440 times a day
// would be a flash-wear problem all of its own.

static uint32_t boot_count = 0;
static uint32_t clip_index = 0;

static void load_boot_count() {
  Preferences nvs;
  if (!nvs.begin("maskcam", false)) { boot_count = 0; return; }
  boot_count = nvs.getUInt("boot", 0) + 1;
  if (boot_count > 9999) boot_count = 1;      // 27 years of daily reboots
  nvs.putUInt("boot", boot_count);
  nvs.end();
}

// The sequence a filename claims. Anything that does not carry one -- a clip
// from an older firmware, a file dropped on the card by hand -- reads as 0,
// which makes it the oldest and therefore the first to go.
static uint32_t seq_of(const char *name) {
  for (int i = 0; i < 9; i++)
    if (name[i] < '0' || name[i] > '9') return 0;
  if (name[9] != '_') return 0;
  return (uint32_t)strtoul(String(name).substring(0, 9).c_str(), nullptr, 10);
}

static void make_clip_name(char *out, size_t n) {
  uint32_t seq = boot_count * 100000 + (clip_index > 99999 ? 99999 : clip_index);
  clip_index++;

  time_t now = time(nullptr);
  struct tm tm_now;
  char stamp[24];
  if (now > 1600000000 && localtime_r(&now, &tm_now))
    strftime(stamp, sizeof(stamp), "%Y%m%d-%H%M%S", &tm_now);
  else
    snprintf(stamp, sizeof(stamp), "noclock");

  snprintf(out, n, MC_REC_DIR "/%09u_%s.avi", (unsigned)seq, stamp);
}

// --- space -----------------------------------------------------------------

void recorder_refresh_space() {
  if (!st.mounted) return;
  uint64_t total = SD_MMC.totalBytes(), used = SD_MMC.usedBytes();
  st.card_total_mb = total / (1024ULL * 1024ULL);
  st.card_free_mb  = (total > used ? total - used : 0) / (1024ULL * 1024ULL);
  space_checked_ms = millis();
}

// The victims list. A 29 GB card holds around 1800 sixty-second clips, and
// walking that directory is not something to do between two frame writes. One
// scan collects the MC_RING_BATCH oldest, and the next fifteen deletions cost
// nothing.
static char ring_cache[MC_RING_BATCH][80];
static int  ring_n = 0, ring_i = 0;

static void ring_invalidate() { ring_n = ring_i = 0; }

static void ring_scan() {
  ring_invalidate();
  File dir = SD_MMC.open(MC_REC_DIR);
  if (!dir) return;

  uint32_t seqs[MC_RING_BATCH];
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    const char *n = f.name();
    const char *base = strrchr(n, '/');
    if (base) n = base + 1;
    bool isdir = f.isDirectory();
    f.close();
    if (isdir || !strstr(n, ".avi")) continue;

    uint32_t sq = seq_of(n);
    // Keep the MC_RING_BATCH smallest sequences, in order. Insertion sort:
    // the array is tiny and this runs once per sixteen deletions.
    int pos = ring_n;
    while (pos > 0 && seqs[pos - 1] > sq) pos--;
    if (pos >= MC_RING_BATCH) continue;
    for (int k = (ring_n < MC_RING_BATCH ? ring_n : MC_RING_BATCH - 1); k > pos; k--) {
      seqs[k] = seqs[k - 1];
      memcpy(ring_cache[k], ring_cache[k - 1], sizeof(ring_cache[0]));
    }
    seqs[pos] = sq;
    snprintf(ring_cache[pos], sizeof(ring_cache[0]), "%s", n);
    if (ring_n < MC_RING_BATCH) ring_n++;
  }
  dir.close();
}

// Delete the oldest clip on the card. Never the one being written -- that is
// the newest by construction, so it cannot be at the front of the list, but
// the check is cheap and the consequence of getting it wrong is a corrupt
// recording.
static bool delete_oldest_clip() {
  if (ring_i >= ring_n) ring_scan();
  while (ring_i < ring_n) {
    const char *name = ring_cache[ring_i++];
    if (st.clip[0] && !strcmp(name, st.clip)) continue;

    char path[96];
    snprintf(path, sizeof(path), MC_REC_DIR "/%s", name);
    if (SD_MMC.remove(path)) {
      Serial.printf("[rec] ring: deleted %s\n", path);
      st.clips_deleted++;
      recorder_refresh_space();
      return true;
    }
    Serial.printf("[rec] ring: FAILED to delete %s\n", path);
    ring_invalidate();       // the list is stale; rescan next time
    return false;
  }
  return false;              // nothing left to delete
}

// --- clip open / close -----------------------------------------------------

static bool open_clip(uint16_t w, uint16_t h, uint8_t fps) {
  char name[64];
  make_clip_name(name, sizeof(name));

  clip = SD_MMC.open(name, "w+");   // w+ : we have to seek back and patch
  if (!clip) { fail("could not create %s", name); return false; }

  uint8_t hdr[AVI_HDR_LEN];
  build_header(hdr, w, h, fps);
  if (clip.write(hdr, AVI_HDR_LEN) != AVI_HDR_LEN) {
    fail("short header write on %s", name);
    clip.close();
    return false;
  }

  snprintf(st.clip, sizeof(st.clip), "%s", strrchr(name, '/') + 1);
  st.clip_frames = 0;
  st.clip_bytes  = AVI_HDR_LEN;
  index_n = 0;
  clip_started_ms = last_sync_ms = millis();
  Serial.printf("[rec] -> %s  (%ux%u @ %u fps)\n", st.clip, w, h, fps);
  return true;
}

// Write into the header the things it could not know when it was written.
//
// This runs periodically, not only at close, and that is the difference
// between a power cut costing you the last few seconds and costing you the
// whole minute. Until a size lands in the header and the directory entry is
// synced, the file on the card is zero bytes long -- which is exactly what an
// interrupted clip looked like before: not truncated, GONE.
static void patch_sizes(bool final, uint32_t movi_end) {
  uint32_t file_end = clip.position();

  uint32_t fps_actual = 0;
  uint32_t elapsed = millis() - clip_started_ms;
  if (elapsed > 0) fps_actual = (uint32_t)((uint64_t)st.clip_frames * 1000 / elapsed);
  if (!fps_actual) fps_actual = 1;

  uint8_t v[4];
  clip.seek(OFF_RIFF_SIZE);      wr32(v, file_end - 8);            clip.write(v, 4);
  clip.seek(OFF_USEC_PER_FRAME); wr32(v, 1000000UL / fps_actual);  clip.write(v, 4);
  clip.seek(OFF_TOTAL_FRAMES);   wr32(v, st.clip_frames);          clip.write(v, 4);
  clip.seek(OFF_STRH_RATE);      wr32(v, fps_actual);              clip.write(v, 4);
  clip.seek(OFF_STRH_LENGTH);    wr32(v, st.clip_frames);          clip.write(v, 4);
  clip.seek(OFF_MOVI_SIZE);      wr32(v, movi_end - MOVI_LIST_POS); clip.write(v, 4);
  // Only now, with an index really on disk, may the header claim to have one.
  if (final) { clip.seek(OFF_FLAGS); wr32(v, 0x10); clip.write(v, 4); }

  clip.seek(file_end);           // back to where the next frame goes
  clip.flush();                  // f_sync: puts the size in the directory entry
}

static void close_clip() {
  if (!clip) return;

  // idx1: one 16-byte entry per frame. Offsets are relative to the 'movi'
  // FOURCC, which is the convention every player expects -- so the first
  // frame's chunk, which starts at 224, indexes as 4.
  uint32_t movi_end = clip.position();
  if (index_n) {
    uint8_t tag[8];
    fourcc(tag, "idx1");
    wr32(tag + 4, index_n * 16);
    clip.write(tag, 8);
    clip.write(index_buf, index_n * 16);
  }

  patch_sizes(true, movi_end);
  clip.close();

  st.clips_written++;
  Serial.printf("[rec] closed %s: %u frames, %.2f MB\n",
                st.clip, (unsigned)st.clip_frames, st.clip_bytes / 1048576.0);
  st.clip[0] = 0;
  recorder_refresh_space();
}

// --- public ----------------------------------------------------------------

bool recorder_begin() {
  memset(&st, 0, sizeof(st));
  st.ring = MC_DEFAULT_RING;

  // Only CMD/CLK/DAT0 are wired on this board, so 1-bit is not a fallback --
  // it is the only mode. The 4-bit default fails for a reason that has nothing
  // to do with the card.
  SD_MMC.setPins(SD_PIN_CLK, SD_PIN_CMD, SD_PIN_D0);
  if (!SD_MMC.begin("/sdcard", true, false)) { fail("SD_MMC.begin() failed"); return false; }
  if (SD_MMC.cardType() == CARD_NONE)        { fail("no card"); return false; }

  if (!SD_MMC.exists(MC_REC_DIR) && !SD_MMC.mkdir(MC_REC_DIR)) {
    fail("could not create " MC_REC_DIR);
    return false;
  }

  load_boot_count();
  Serial.printf("[rec] boot #%u -- clips this boot are numbered %09u and up\n",
                (unsigned)boot_count, (unsigned)(boot_count * 100000));

  index_buf = (uint8_t *)ps_malloc(MC_MAX_CLIP_FRAMES * 16);
  if (!index_buf) { fail("no PSRAM for the AVI index"); return false; }

  st.mounted = true;

  // A power cut leaves the clip that was being written unclosed. With periodic
  // syncing most of those are playable, but one cut in the first second leaves
  // a file with a header and nothing else -- or nothing at all. Sweep them:
  // they are unplayable by definition, and an always-on camera behind a
  // screwed-down cover would otherwise collect one per power blip forever.
  {
    File dir = SD_MMC.open(MC_REC_DIR);
    if (dir) {
      char victims[16][80];
      int n = 0;
      for (File f = dir.openNextFile(); f && n < 16; f = dir.openNextFile()) {
        const char *nm = f.name(); const char *b = strrchr(nm, '/');
        if (b) nm = b + 1;
        bool junk = !f.isDirectory() && strstr(nm, ".avi") && f.size() < 4096;
        if (junk) snprintf(victims[n++], sizeof(victims[0]), "%s", nm);
        f.close();
      }
      dir.close();
      for (int i = 0; i < n; i++) {
        char path[96];
        snprintf(path, sizeof(path), MC_REC_DIR "/%s", victims[i]);
        if (SD_MMC.remove(path))
          Serial.printf("[rec] swept empty clip %s\n", victims[i]);
      }
    }
  }

  recorder_refresh_space();
  Serial.printf("[rec] card %llu MB, %llu MB free\n",
                (unsigned long long)st.card_total_mb,
                (unsigned long long)st.card_free_mb);
  return true;
}

bool recorder_armed() { return st.armed; }
void recorder_set_ring(bool on) { st.ring = on; }

bool recorder_arm() {
  if (!st.mounted) { fail("cannot record, no card mounted"); return false; }
  st.paused_for_space = false;
  if (st.armed) return true;
  st.last_error[0] = 0;
  st.armed = true;          // the pump opens the clip; it knows the frame size
  return true;
}

void recorder_disarm() {
  st.paused_for_space = false;    // a deliberate stop is not a paused one
  if (!st.armed) return;
  st.armed = false;
  // The writer owns the file. Let it drain what is queued and close the clip
  // itself rather than closing a File out from under a write in flight.
  for (int i = 0; i < 60 && st.clip[0]; i++) vTaskDelay(pdMS_TO_TICKS(50));
  if (st.clip[0]) Serial.println("[rec] warning: writer did not close the clip in 3 s");
}

static void write_frame(const uint8_t *jpeg, size_t len, uint16_t w, uint16_t h, uint8_t fps) {
  if (!st.mounted || !len) return;

  // Free space is a syscall, so check it on a timer rather than per frame.
  if (millis() - space_checked_ms > 5000) recorder_refresh_space();

  // Deleting happens on the housekeeping task, well above this point. Getting
  // here means housekeeping could not keep up -- or ring mode is off and the
  // card is simply full -- so stop, and say which.
  if (st.card_free_mb < MC_FREE_FLOOR_MB) {
    fail(st.ring ? "card down to %llu MB and housekeeping cannot keep up, pausing"
                 : "card down to %llu MB and ring mode is off, stopping",
         (unsigned long long)st.card_free_mb);
    st.paused_for_space = st.ring;   // housekeeping re-arms if it can free room
    st.armed = false;                // writer_task closes the clip as it drains
    return;
  }

  // Roll to a new clip on time or when the index is full.
  if (clip && (millis() - clip_started_ms > MC_CLIP_SECONDS * 1000UL ||
               index_n >= MC_MAX_CLIP_FRAMES))
    close_clip();

  if (!clip && !open_clip(w, h, fps)) { st.armed = false; return; }

  // '00dc' chunk: fourcc, size, payload, pad to even.
  uint8_t chunk[8];
  fourcc(chunk, "00dc");
  wr32(chunk + 4, len);

  uint32_t offset = clip.position() - MOVI_LIST_POS;   // for idx1
  uint32_t t0 = millis();
  bool ok = clip.write(chunk, 8) == 8 && clip.write(jpeg, len) == len;
  if (ok && (len & 1)) { uint8_t z = 0; ok = clip.write(&z, 1) == 1; }
  uint32_t dt = millis() - t0;

  st.write_ms_last = dt;
  if (dt > st.write_ms_max) st.write_ms_max = dt;

  if (!ok) {
    // A short write means the card gave up. Count it and end the clip rather
    // than indexing a frame that is not entirely on the card.
    st.frames_dropped++;
    fail("short write at frame %u, closing clip", (unsigned)st.clip_frames);
    close_clip();
    st.armed = false;
    return;
  }

  if (index_n < MC_MAX_CLIP_FRAMES) {
    uint8_t *e = index_buf + index_n * 16;
    fourcc(e, "00dc");
    wr32(e + 4, 0x10);          // AVIIF_KEYFRAME -- every MJPEG frame is one
    wr32(e + 8, offset);
    wr32(e + 12, len);
    index_n++;
  }

  st.clip_frames++;
  st.clip_bytes += len + 8 + (len & 1);

  // Every few seconds, make the clip real on the card. Costs a handful of
  // seeks and one f_sync; buys a playable file if the power goes.
  if (millis() - last_sync_ms >= MC_SYNC_SECONDS * 1000UL) {
    last_sync_ms = millis();
    patch_sizes(false, clip.position());
  }
}

// --- the writer task -------------------------------------------------------
//
// The card is the slow, bursty part of this system and the camera is the part
// that must not be made to wait. So frames cross between them through a small
// ring of PSRAM slots: the pump fills one and moves on, the writer empties
// them in its own time. When the card stalls the queue absorbs it; when the
// queue fills, frames are DROPPED and counted rather than silently stretching
// the frame interval, because a recording that quietly runs slow is worse than
// one that says it lost four frames.

struct Slot {
  uint8_t *buf;
  size_t   len;
  uint16_t w, h;
  uint8_t  fps;
};

static Slot          slots[MC_REC_QUEUE_SLOTS];
static QueueHandle_t q_free = nullptr, q_full = nullptr;

bool recorder_queue_frame(const uint8_t *jpeg, size_t len, uint16_t w, uint16_t h, uint8_t fps) {
  if (!st.armed || !st.mounted || !q_free || !len) return false;

  int i;
  if (xQueueReceive(q_free, &i, 0) != pdTRUE) { st.frames_dropped++; return false; }
  if (len > MC_MAX_FRAME_BYTES) { xQueueSend(q_free, &i, 0); st.frames_dropped++; return false; }

  memcpy(slots[i].buf, jpeg, len);
  slots[i].len = len; slots[i].w = w; slots[i].h = h; slots[i].fps = fps;
  xQueueSend(q_full, &i, 0);
  st.queue_depth = uxQueueMessagesWaiting(q_full);
  return true;
}

static void writer_task(void *) {
  for (;;) {
    int i;
    if (xQueueReceive(q_full, &i, pdMS_TO_TICKS(100)) == pdTRUE) {
      write_frame(slots[i].buf, slots[i].len, slots[i].w, slots[i].h, slots[i].fps);
      xQueueSend(q_free, &i, 0);
      st.queue_depth = uxQueueMessagesWaiting(q_full);
      continue;
    }
    // Nothing queued. If recording has been stopped -- or stopped itself on a
    // full card -- this is the moment the clip is complete and can be closed.
    if (!st.armed && clip) close_clip();
  }
}

void recorder_start_writer() {
  q_free = xQueueCreate(MC_REC_QUEUE_SLOTS, sizeof(int));
  q_full = xQueueCreate(MC_REC_QUEUE_SLOTS, sizeof(int));
  for (int i = 0; i < MC_REC_QUEUE_SLOTS; i++) {
    slots[i].buf = (uint8_t *)ps_malloc(MC_MAX_FRAME_BYTES);
    if (!slots[i].buf) { fail("no PSRAM for record queue slot %d", i); return; }
    xQueueSend(q_free, &i, 0);
  }
  // Core 0, alongside the network stack and away from the capture pump on
  // core 1 -- the whole point is that a slow write cannot stall the camera.
  xTaskCreatePinnedToCore(writer_task, "recwrite", 8192, nullptr, 4, nullptr, 0);
}

// --- housekeeping ----------------------------------------------------------
//
// Keeping room on the card is a background job, not something to do between
// two frame writes. This runs well above the writer's hard floor, so by the
// time the recorder could be in trouble there is already space. It also
// re-arms recording if the card filled while ring mode was off and somebody
// has since made room -- "always recording" should mean it.

static void housekeeper_task(void *) {
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(5000));
    if (!st.mounted) continue;

    recorder_refresh_space();

    if (st.ring && st.card_free_mb < MC_FREE_TARGET_MB) {
      // Bounded: one pass frees at most this many clips, so a card that is
      // full of something other than clips cannot spin here forever.
      int freed = 0;
      while (st.card_free_mb < MC_FREE_TARGET_MB && freed < 64) {
        if (!delete_oldest_clip()) break;
        freed++;
      }
      if (freed)
        Serial.printf("[rec] housekeeping freed %d clip(s), %llu MB free\n",
                      freed, (unsigned long long)st.card_free_mb);
    }

    // Recording stopped because the card filled, and there is room again.
    if (st.paused_for_space && !st.armed && st.card_free_mb >= MC_FREE_TARGET_MB) {
      st.paused_for_space = false;
      st.last_error[0] = 0;
      st.armed = true;
      Serial.println("[rec] room again, recording resumed");
    }
  }
}

void recorder_start_housekeeper() {
  // Low priority and off the capture core: nothing here is urgent, and a
  // directory walk must never be what makes the camera miss a frame.
  xTaskCreatePinnedToCore(housekeeper_task, "rechouse", 4096, nullptr, 2, nullptr, 0);
}

void recorder_stats(RecStats *out) {
  portENTER_CRITICAL(&st_mux);
  *out = st;
  portEXIT_CRITICAL(&st_mux);
}

String recorder_list_json() {
  String out = "[";
  if (!st.mounted) return out + "]";
  File dir = SD_MMC.open(MC_REC_DIR);
  if (!dir) return out + "]";
  bool first = true;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    if (!f.isDirectory()) {
      const char *n = f.name();
      const char *base = strrchr(n, '/');
      if (base) n = base + 1;
      if (!first) out += ",";
      out += "{\"name\":\"" + String(n) + "\",\"size\":" + String((uint32_t)f.size()) + "}";
      first = false;
    }
    f.close();
  }
  dir.close();
  return out + "]";
}

bool recorder_delete(const char *name) {
  // Refuse anything with a path separator in it: the name comes off a query
  // string, and MC_REC_DIR is the only place this is allowed to touch.
  if (!name || !*name || strchr(name, '/') || strstr(name, "..")) return false;
  char path[96];
  snprintf(path, sizeof(path), MC_REC_DIR "/%s", name);
  if (st.clip[0] && !strcmp(name, st.clip)) return false;   // not the live one
  bool ok = SD_MMC.remove(path);
  if (ok) { ring_invalidate(); recorder_refresh_space(); }
  return ok;
}

// --- USB console -----------------------------------------------------------

void recorder_print_listing() {
  if (!st.mounted) { Serial.println("no card"); return; }
  File dir = SD_MMC.open(MC_REC_DIR);
  if (!dir) { Serial.println("no " MC_REC_DIR); return; }
  uint32_t n = 0;
  uint64_t total = 0;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    if (!f.isDirectory()) {
      const char *nm = f.name(); const char *b = strrchr(nm, '/');
      Serial.printf("  %-28s %8.2f MB\n", b ? b + 1 : nm, f.size() / 1048576.0);
      total += f.size(); n++;
    }
    f.close();
  }
  dir.close();
  Serial.printf("  %u clip(s), %.2f MB, %llu MB free\n",
                (unsigned)n, total / 1048576.0, (unsigned long long)st.card_free_mb);
}

// Newest by sequence number -- the same ordering the ring deletes by, read
// straight off the filename with nothing opened.
bool recorder_newest_clip(char *out, size_t n) {
  if (!st.mounted) return false;
  File dir = SD_MMC.open(MC_REC_DIR);
  if (!dir) return false;
  char best[64] = "";
  uint32_t best_seq = 0;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    const char *nm = f.name(); const char *b = strrchr(nm, '/');
    if (b) nm = b + 1;
    bool isdir = f.isDirectory();
    char keep[80];
    snprintf(keep, sizeof(keep), "%s", nm);
    f.close();
    if (isdir || !strstr(keep, ".avi")) continue;
    uint32_t sq = seq_of(keep);
    if (!best[0] || sq > best_seq || (sq == best_seq && strcmp(keep, best) > 0)) {
      best_seq = sq;
      snprintf(best, sizeof(best), "%s", keep);
    }
  }
  dir.close();
  if (!best[0]) return false;
  snprintf(out, n, "%s", best);
  return true;
}

static const char B64[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

// HWCDC::write() returns a SHORT count when its ring buffer backs up because
// the host is not reading fast enough -- and Serial.print(), like every other
// Print method, throws that return value away. That is exactly how 16 kB went
// missing out of the middle of a 4 MB dump, silently, leaving a file that was
// structurally plausible and quietly corrupt.
//
// So: write the remainder until it is gone, and give up honestly if the host
// has actually disappeared rather than spinning here forever.
static bool serial_write_all(const uint8_t *p, size_t n) {
  size_t sent = 0;
  uint32_t stalls = 0;
  while (sent < n) {
    size_t w = Serial.write(p + sent, n - sent);
    sent += w;
    if (w == 0) {
      if (++stalls > 2000) return false;    // ~2 s of no progress: host is gone
      delay(1);
    } else {
      stalls = 0;
    }
  }
  return true;
}

// Send a clip up the USB wire so it can be decoded and PLAYED at the other
// end. A recorder that reports "60 frames written" and produces a file no
// player will open has still failed, and only opening it proves otherwise.
bool recorder_dump_base64(const char *name) {
  if (!name || strchr(name, '/') || strstr(name, "..")) return false;
  char path[96];
  snprintf(path, sizeof(path), MC_REC_DIR "/%s", name);
  File f = SD_MMC.open(path, FILE_READ);
  if (!f) { Serial.printf("!! no %s\n", path); return false; }

  // The default 100 ms CDC timeout is short for a multi-megabyte dump; give
  // the ring buffer room to drain before write() starts reporting stalls.
  Serial.setTxTimeoutMs(1000);

  Serial.printf("---BEGIN FILE %s %u---\n", name, (unsigned)f.size());
  uint8_t chunk[57];
  char line[80];
  bool ok = true;
  while (ok) {
    size_t n = f.read(chunk, sizeof(chunk));
    if (!n) break;
    size_t o = 0;
    for (size_t j = 0; j < n; j += 3) {
      uint32_t v = (uint32_t)chunk[j] << 16;
      if (j + 1 < n) v |= (uint32_t)chunk[j + 1] << 8;
      if (j + 2 < n) v |= (uint32_t)chunk[j + 2];
      line[o++] = B64[(v >> 18) & 63];
      line[o++] = B64[(v >> 12) & 63];
      line[o++] = (j + 1 < n) ? B64[(v >> 6) & 63] : '=';
      line[o++] = (j + 2 < n) ? B64[v & 63]        : '=';
    }
    line[o++] = '\n';
    ok = serial_write_all((const uint8_t *)line, o);
  }
  f.close();
  Serial.setTxTimeoutMs(100);

  // The end marker says whether the dump is whole. The host checks the byte
  // count too -- belt and braces, because a truncated clip that looks fine is
  // the failure this whole path exists to avoid.
  Serial.println(ok ? "---END FILE---" : "---ABORTED FILE---");
  return ok;
}

// --- motion annotation -----------------------------------------------------

void recorder_note_motion(uint16_t changed, uint16_t total, uint8_t lum,
                          char *desc_out, size_t desc_len) {
  // Seconds into the clip, taken from the clock rather than from the frame
  // count: frames get dropped when the card stalls, and an offset that drifts
  // against the footage is worse than no offset at all.
  uint32_t into = (clip && clip_started_ms) ? (millis() - clip_started_ms) / 1000 : 0;
  const char *which = st.clip[0] ? st.clip : "-";

  char stamp[24];
  time_t now = time(nullptr);
  struct tm tm_now;
  if (now > 1600000000 && localtime_r(&now, &tm_now))
    strftime(stamp, sizeof(stamp), "%Y-%m-%d %H:%M:%S", &tm_now);
  else
    snprintf(stamp, sizeof(stamp), "up+%lus", (unsigned long)(millis() / 1000));

  if (desc_out)
    snprintf(desc_out, desc_len, "%s  %s +%lus  %u/%u blocks  lum %u",
             stamp, which, (unsigned long)into, changed, total, lum);

  if (!st.mounted) return;

  // Rotate rather than grow without bound. One line is ~70 bytes, so the cap
  // is thousands of events -- but this thing is meant to run for months.
  File f = SD_MMC.open(MC_MOTION_LOG, FILE_APPEND);
  if (f && f.size() > MC_MOTION_LOG_MAX) {
    f.close();
    SD_MMC.remove(MC_MOTION_LOG ".1");
    SD_MMC.rename(MC_MOTION_LOG, MC_MOTION_LOG ".1");
    f = SD_MMC.open(MC_MOTION_LOG, FILE_APPEND);
  }
  if (!f) return;
  f.printf("%s\t%s\t%lu\t%u\t%u\t%u\n", stamp, which,
           (unsigned long)into, changed, total, lum);
  f.close();
}

String recorder_motion_json(int limit) {
  String out = "[";
  if (!st.mounted) return out + "]";
  File f = SD_MMC.open(MC_MOTION_LOG, FILE_READ);
  if (!f) return out + "]";

  // Only the tail is interesting, and the whole file must never be pulled
  // into RAM -- read a window off the end and drop the partial first line.
  const size_t WINDOW = 16 * 1024;
  size_t sz = f.size();
  if (sz > WINDOW) f.seek(sz - WINDOW);
  String blob = f.readString();
  f.close();
  if (sz > WINDOW) {
    int nl = blob.indexOf('\n');
    if (nl >= 0) blob = blob.substring(nl + 1);
  }

  // Walk backwards so the newest events come first and `limit` means the most
  // recent ones, not the oldest.
  int lines = 0;
  int end = blob.length();
  bool first = true;
  while (end > 0 && lines < limit) {
    int start = blob.lastIndexOf('\n', end - 1);
    String line = blob.substring(start + 1, end);
    end = start;
    line.trim();
    if (line.length()) {
      int t1 = line.indexOf('\t');
      int t2 = line.indexOf('\t', t1 + 1);
      int t3 = line.indexOf('\t', t2 + 1);
      int t4 = line.indexOf('\t', t3 + 1);
      int t5 = line.indexOf('\t', t4 + 1);
      if (t5 > 0) {
        if (!first) out += ",";
        out += "{\"t\":\"" + line.substring(0, t1) + "\"";
        out += ",\"clip\":\"" + line.substring(t1 + 1, t2) + "\"";
        out += ",\"into\":" + line.substring(t2 + 1, t3);
        out += ",\"blocks\":" + line.substring(t3 + 1, t4);
        out += ",\"total\":" + line.substring(t4 + 1, t5);
        out += ",\"lum\":" + line.substring(t5 + 1) + "}";
        first = false;
        lines++;
      }
    }
    if (start < 0) break;
  }
  return out + "]";
}

void recorder_clear_motion_log() {
  if (!st.mounted) return;
  SD_MMC.remove(MC_MOTION_LOG);
  SD_MMC.remove(MC_MOTION_LOG ".1");
}
