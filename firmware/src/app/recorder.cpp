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

#include "../board_pins.h"

// --- AVI layout ------------------------------------------------------------
// Offsets into the 224-byte header. Named rather than magic so the patching
// at the end of the clip is readable.
static const size_t AVI_HDR_LEN        = 224;
static const size_t OFF_RIFF_SIZE      = 4;    // filesize - 8
static const size_t OFF_USEC_PER_FRAME = 32;
static const size_t OFF_MAX_BYTES_SEC  = 36;
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
  wr32  (h + 44, 0x10);                       // AVIF_HASINDEX
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

static void make_clip_name(char *out, size_t n) {
  // A real timestamp if NTP answered, a counter if it did not. Either is fine;
  // silently writing 1970 all over the card is not.
  time_t now = time(nullptr);
  struct tm tm_now;
  if (now > 1600000000 && localtime_r(&now, &tm_now)) {
    strftime(out, n, MC_REC_DIR "/%Y%m%d-%H%M%S.avi", &tm_now);
    return;
  }

  // No clock. The counter cannot just start from clips_written, because that
  // resets at every boot -- which had this overwriting clip0001.avi on the
  // second power-up, destroying the first recording without a word. Ask the
  // card what already exists instead.
  for (unsigned i = st.clips_written + 1; i < 10000; i++) {
    snprintf(out, n, MC_REC_DIR "/clip%04u.avi", i);
    if (!SD_MMC.exists(out)) return;
  }
  snprintf(out, n, MC_REC_DIR "/clip9999.avi");   // card is absurdly full of clips
}

// --- space -----------------------------------------------------------------

void recorder_refresh_space() {
  if (!st.mounted) return;
  uint64_t total = SD_MMC.totalBytes(), used = SD_MMC.usedBytes();
  st.card_total_mb = total / (1024ULL * 1024ULL);
  st.card_free_mb  = (total > used ? total - used : 0) / (1024ULL * 1024ULL);
  space_checked_ms = millis();
}

// Oldest clip by the card's own modification time, NOT by name.
//
// Names sort chronologically within either scheme but not across them, and a
// card that has both -- clips recorded before NTP answered, then clips named
// by wall clock -- sorts "20260821-055559.avi" BELOW "clip0001.avi", because
// '2' < 'c'. By name, ring mode would delete the newest footage first. This is
// the one path here that destroys data, so it asks the filesystem instead:
// clips written before the clock was set carry a 1970 timestamp, which makes
// them genuinely the oldest, which is exactly right.
static bool delete_oldest_clip() {
  File dir = SD_MMC.open(MC_REC_DIR);
  if (!dir) return false;
  char oldest[64] = "";
  time_t oldest_t = 0;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    const char *n = f.name();
    const char *base = strrchr(n, '/');
    if (base) n = base + 1;
    if (!f.isDirectory() && strstr(n, ".avi")) {
      time_t t = f.getLastWrite();
      if (!oldest[0] || t < oldest_t || (t == oldest_t && strcmp(n, oldest) < 0)) {
        oldest_t = t;
        snprintf(oldest, sizeof(oldest), "%s", n);
      }
    }
    f.close();
  }
  dir.close();
  if (!oldest[0]) return false;

  char path[96];
  snprintf(path, sizeof(path), MC_REC_DIR "/%s", oldest);
  bool ok = SD_MMC.remove(path);
  Serial.printf("[rec] ring: %s %s\n", ok ? "deleted" : "FAILED to delete", path);
  if (ok) recorder_refresh_space();
  return ok;
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
  clip_started_ms = millis();
  Serial.printf("[rec] -> %s  (%ux%u @ %u fps)\n", st.clip, w, h, fps);
  return true;
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
  uint32_t file_end = clip.position();

  // Patch everything the header could not know when it was written.
  uint32_t fps_actual = 0;
  uint32_t elapsed = millis() - clip_started_ms;
  if (elapsed > 0) fps_actual = (uint32_t)((uint64_t)st.clip_frames * 1000 / elapsed);
  if (!fps_actual) fps_actual = 1;

  uint8_t v[4];
  clip.seek(OFF_RIFF_SIZE);    wr32(v, file_end - 8);            clip.write(v, 4);
  clip.seek(OFF_USEC_PER_FRAME); wr32(v, 1000000UL / fps_actual); clip.write(v, 4);
  clip.seek(OFF_TOTAL_FRAMES); wr32(v, st.clip_frames);          clip.write(v, 4);
  clip.seek(OFF_STRH_RATE);    wr32(v, fps_actual);              clip.write(v, 4);
  clip.seek(OFF_STRH_LENGTH);  wr32(v, st.clip_frames);          clip.write(v, 4);
  clip.seek(OFF_MOVI_SIZE);    wr32(v, movi_end - MOVI_LIST_POS); clip.write(v, 4);

  clip.flush();
  clip.close();

  st.clips_written++;
  Serial.printf("[rec] closed %s: %u frames, %llu bytes, %u fps measured\n",
                st.clip, (unsigned)st.clip_frames,
                (unsigned long long)file_end, (unsigned)fps_actual);
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

  index_buf = (uint8_t *)ps_malloc(MC_MAX_CLIP_FRAMES * 16);
  if (!index_buf) { fail("no PSRAM for the AVI index"); return false; }

  st.mounted = true;
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
  if (st.armed) return true;
  st.last_error[0] = 0;
  st.armed = true;          // the pump opens the clip; it knows the frame size
  return true;
}

void recorder_disarm() {
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

  if (st.card_free_mb < MC_FREE_FLOOR_MB) {
    if (!st.ring || !delete_oldest_clip()) {
      fail("card down to %llu MB, stopping", (unsigned long long)st.card_free_mb);
      st.armed = false;      // writer_task closes the clip once the queue drains
      return;
    }
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
  if (ok) recorder_refresh_space();
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

// Newest by modification time, for the same reason delete_oldest_clip() is:
// on a card carrying both naming schemes, "newest by name" is wrong.
bool recorder_newest_clip(char *out, size_t n) {
  if (!st.mounted) return false;
  File dir = SD_MMC.open(MC_REC_DIR);
  if (!dir) return false;
  char best[64] = "";
  time_t best_t = 0;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    const char *nm = f.name(); const char *b = strrchr(nm, '/');
    if (b) nm = b + 1;
    if (!f.isDirectory() && strstr(nm, ".avi")) {
      time_t t = f.getLastWrite();
      if (!best[0] || t > best_t || (t == best_t && strcmp(nm, best) > 0)) {
        best_t = t;
        snprintf(best, sizeof(best), "%s", nm);
      }
    }
    f.close();
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
