#include "detect.h"
#include "capture.h"
#include "recorder.h"
#include "../config.h"

#include <esp_camera.h>
#include <esp_jpg_decode.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

static MotStats st;
static int p_block_diff = MC_MOT_BLOCK_DIFF;
static int p_min_blocks = MC_MOT_MIN_BLOCKS;
static int p_global_pct = MC_MOT_GLOBAL_PCT;
static int p_hz         = MC_MOTION_HZ;

static uint8_t *jpeg_buf = nullptr;   // PSRAM: a frame copied out of the pump
static uint8_t *gray_now = nullptr;   // internal RAM: 100x75 is only 7.5 kB
static uint8_t *gray_ref = nullptr;
static uint16_t gw = 0, gh = 0;
static bool     have_ref = false;
static uint8_t  ref_lum = 0;

// --- decode straight to grayscale ------------------------------------------
//
// The ROM tjpgd hands back RGB888 blocks. Converting inside the callback means
// the full RGB image -- 1.44 MB at SVGA -- is never materialised at all. This
// is what MJPEG2SD and Tasmota both do, and it is why esp_jpg_decode() is used
// directly instead of the stock jpg2rgb565().

struct GrayCtx { const uint8_t *jpeg; uint8_t *out; uint16_t w, h; };

static size_t rd_cb(void *arg, size_t index, uint8_t *buf, size_t len) {
  GrayCtx *c = (GrayCtx *)arg;
  if (buf) memcpy(buf, c->jpeg + index, len);
  return len;
}

static bool gray_cb(void *arg, uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint8_t *data) {
  GrayCtx *c = (GrayCtx *)arg;
  if (!data) {                        // start (x==y==0, w/h = output size) or end
    if (x == 0 && y == 0) { c->w = w; c->h = h; }
    return true;
  }
  for (uint16_t j = 0; j < h; j++)
    for (uint16_t i = 0; i < w; i++) {
      const uint8_t *p = data + ((j * w + i) * 3);
      c->out[(y + j) * c->w + (x + i)] = (uint8_t)((p[0] + p[1] + p[2]) / 3);
    }
  return true;
}

// --- the cheap veto --------------------------------------------------------
// One SCCB read, 0.65 ms, of the OV3660's overall luminance average. Verified
// on this board against the decoded image (+0.968 correlation) and against a
// forced exposure sweep. Useless as a detector -- one global number -- which
// is exactly what makes it a lighting-change detector.
static uint8_t read_overall_lum() {
  sensor_t *s = esp_camera_sensor_get();
  if (!s || s->id.PID != OV3660_PID) return 0;
  int v = s->get_reg(s, 0x56A1, 0xFF);
  return v < 0 ? 0 : (uint8_t)v;
}

// --- the comparison --------------------------------------------------------
// Blocks, not summed difference. A 5 % brightness step and a person occupying
// 5 % of the frame are numerically identical under sum-of-absolute-difference;
// counting blocks separates them, and only a block count makes the
// global-change CEILING possible.
static uint16_t count_changed_blocks(uint16_t *total_out) {
  const int BS = 8;
  int bx = gw / BS, by = gh / BS;
  uint16_t changed = 0;

  for (int b = 0; b < by; b++) {
    for (int a = 0; a < bx; a++) {
      uint32_t sum = 0;
      for (int j = 0; j < BS; j++) {
        const uint8_t *n = gray_now + (b * BS + j) * gw + a * BS;
        const uint8_t *r = gray_ref + (b * BS + j) * gw + a * BS;
        for (int i = 0; i < BS; i++) sum += abs((int)n[i] - (int)r[i]);
      }
      if ((sum / (BS * BS)) > (uint32_t)p_block_diff) changed++;
    }
  }
  *total_out = bx * by;
  return changed;
}

// ---------------------------------------------------------------------------

bool motion_begin() {
  memset(&st, 0, sizeof(st));
  st.enabled = MC_MOTION_ENABLED;

  jpeg_buf = (uint8_t *)ps_malloc(capture_max_frame_bytes());
  // 100x75 at SVGA/8. Internal RAM on purpose: it is small, and PSRAM latency
  // on a per-pixel loop is exactly where it hurts.
  gray_now = (uint8_t *)heap_caps_malloc(220 * 170, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  gray_ref = (uint8_t *)heap_caps_malloc(220 * 170, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if (!jpeg_buf || !gray_now || !gray_ref) {
    Serial.println("[mot] no memory for the detector");
    return false;
  }
  return true;
}

void motion_set_enabled(bool on) { st.enabled = on; }

void motion_set_params(int block_diff, int min_blocks, int global_pct, int hz) {
  if (block_diff > 0)  p_block_diff = block_diff;
  if (min_blocks > 0)  p_min_blocks = min_blocks;
  if (global_pct > 0)  p_global_pct = global_pct;
  if (hz > 0 && hz <= 10) p_hz = hz;
}

void motion_get_params(int *bd, int *mb, int *gp, int *hz) {
  *bd = p_block_diff; *mb = p_min_blocks; *gp = p_global_pct; *hz = p_hz;
}

static void detect_task(void *) {
  st.running = true;
  uint32_t seq = 0, consec = 0, last_trigger_ms = 0;

  for (;;) {
    uint32_t period = 1000 / (p_hz ? p_hz : 1);
    uint32_t t_start = millis();

    if (!st.enabled) { vTaskDelay(pdMS_TO_TICKS(period)); continue; }

    seq = 0;                                   // "whatever is current"
    size_t len = capture_wait_frame(jpeg_buf, capture_max_frame_bytes(), &seq, 1000);
    if (!len) { vTaskDelay(pdMS_TO_TICKS(period)); continue; }

    uint8_t lum = read_overall_lum();

    GrayCtx ctx = { jpeg_buf, gray_now, 0, 0 };
    int64_t t0 = esp_timer_get_time();
    esp_err_t e = esp_jpg_decode(len, JPG_SCALE_8X, rd_cb, gray_cb, &ctx);
    st.last_decode_ms = (uint16_t)((esp_timer_get_time() - t0) / 1000);
    if (e != ESP_OK) { vTaskDelay(pdMS_TO_TICKS(period)); continue; }

    st.checks++;
    st.last_lum = lum;

    // Frame size changed under us (the UI can do that) -- rebaseline.
    if (ctx.w != gw || ctx.h != gh) {
      gw = ctx.w; gh = ctx.h;
      have_ref = false;
    }

    if (!have_ref) {
      memcpy(gray_ref, gray_now, (size_t)gw * gh);
      ref_lum = lum;
      have_ref = true;
      vTaskDelay(pdMS_TO_TICKS(period));
      continue;
    }

    uint16_t total = 0;
    uint16_t changed = count_changed_blocks(&total);
    st.last_blocks = changed;
    st.total_blocks = total;

    // Veto 1: the whole scene moved. That is light, not a person.
    bool global = total && (changed * 100 > total * p_global_pct);

    // Veto 2: overall luminance stepped. Cheaper than veto 1 and catches the
    // AEC hunting before it has changed enough blocks to trip the ceiling.
    int lum_delta = abs((int)lum - (int)ref_lum);
    int lum_allow = ref_lum * MC_MOT_LUM_PCT / 100;
    if (lum_allow < MC_MOT_LUM_FLOOR) lum_allow = MC_MOT_LUM_FLOOR;
    bool lum_jump = lum_delta > lum_allow;

    st.last_global = global || lum_jump;

    if (global || lum_jump) {
      st.rejected_global++;
      consec = 0;
      // Rebaseline immediately. Every project that skips this reports the
      // lighting change trailing into the NEXT comparison as fake motion.
      memcpy(gray_ref, gray_now, (size_t)gw * gh);
      ref_lum = lum;
    } else {
      consec = (changed >= p_min_blocks) ? consec + 1 : 0;

      bool warm    = millis() > MC_MOT_WARMUP_MS;
      bool cooled  = !last_trigger_ms || (millis() - last_trigger_ms > MC_MOT_COOLDOWN_MS);
      if (consec >= MC_MOT_CONSEC && warm && cooled) {
        last_trigger_ms = millis();
        st.events++;
        st.last_event_ms = millis();

        // The annotation. The recorder knows which clip is open and how far
        // into it we are, so the event points straight at the footage.
        recorder_note_motion(changed, total, lum, st.last_event, sizeof(st.last_event));
        Serial.printf("[mot] %s\n", st.last_event);
        consec = 0;
      }

      // Slow baseline drift: track the scene when nothing is happening, so a
      // gradual change (sun moving) never accumulates into a trigger.
      if (changed < p_min_blocks) {
        memcpy(gray_ref, gray_now, (size_t)gw * gh);
        ref_lum = lum;
      }
    }

    uint32_t spent = millis() - t_start;
    vTaskDelay(pdMS_TO_TICKS(spent >= period ? 1 : period - spent));
  }
}

void motion_start_task() {
  // Core 1 with the pump, but a LOWER priority: a 40 ms decode must never be
  // what makes the camera miss its 100 ms frame deadline. Core 0 is left to
  // WiFi and the SD writer.
  xTaskCreatePinnedToCore(detect_task, "motion", 8192, nullptr, 3, nullptr, 1);
}

void motion_stats(MotStats *out) { *out = st; }
