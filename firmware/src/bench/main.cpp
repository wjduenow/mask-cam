// bench/main.cpp — two measurements, so motion detection can be designed from
// numbers off this board instead of numbers off the internet.
//
// A: what does decoding one of our JPEGs actually cost, at each scale?
//    Every published figure for this is either a different resolution, a
//    different chip, or arithmetic. The answer decides whether detection at
//    2 Hz costs 10 % of a core or 25 %.
//
// B: does the OV3660's 4x4 zone-average block (registers 0x5691-0x56A0) work?
//    The datasheet documents it, the driver already initialises the zone
//    weights, and no ESP32 project appears to read it. If it works it is a
//    sub-millisecond motion pre-gate that needs no decode at all.
//
//    It is checked against the decoded image rather than against a hand waved
//    at the lens: decode the same frame, compute its own 4x4 zone means, and
//    see whether the two agree. Agreement is the proof; nothing else is.

#include <Arduino.h>
#include <esp_camera.h>
#include <esp_jpg_decode.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>

#include "../board_pins.h"

// --- a grayscale writer for esp_jpg_decode ---------------------------------
// The ROM tjpgd hands back RGB888 blocks. Converting to grayscale in the
// callback means the big RGB image is never materialised -- this is the trick
// MJPEG2SD and Tasmota both use.

struct GrayCtx {
  const uint8_t *jpeg;
  uint8_t *gray;
  uint16_t w, h;
};

static size_t rd_cb(void *arg, size_t index, uint8_t *buf, size_t len) {
  GrayCtx *c = (GrayCtx *)arg;
  if (buf) memcpy(buf, c->jpeg + index, len);
  return len;
}

static bool gray_cb(void *arg, uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint8_t *data) {
  GrayCtx *c = (GrayCtx *)arg;
  if (!data) {                       // start (x==y==0, w/h = output size) or end
    if (x == 0 && y == 0) { c->w = w; c->h = h; }
    return true;
  }
  for (uint16_t j = 0; j < h; j++) {
    for (uint16_t i = 0; i < w; i++) {
      const uint8_t *p = data + ((j * w + i) * 3);
      c->gray[(y + j) * c->w + (x + i)] = (uint8_t)((p[0] + p[1] + p[2]) / 3);
    }
  }
  return true;
}

static uint8_t *gray_buf = nullptr;
static uint8_t *jpeg_copy = nullptr;

// --- B: the sensor's own 4x4 luminance map ---------------------------------

static bool read_zones(uint8_t z[16], uint8_t *overall, uint32_t *micros_taken) {
  sensor_t *s = esp_camera_sensor_get();
  if (!s) return false;
  int64_t t0 = esp_timer_get_time();
  for (int i = 0; i < 16; i++) {
    int v = s->get_reg(s, 0x5691 + i, 0xFF);
    if (v < 0) return false;
    z[i] = (uint8_t)v;
  }
  int ov = s->get_reg(s, 0x56A1, 0xFF);
  *micros_taken = (uint32_t)(esp_timer_get_time() - t0);
  if (ov < 0) return false;
  *overall = (uint8_t)ov;
  return true;
}

static void print_grid(const char *label, const uint8_t *v) {
  Serial.printf("  %-16s", label);
  for (int r = 0; r < 4; r++) {
    for (int c = 0; c < 4; c++) Serial.printf("%4u", v[r * 4 + c]);
    Serial.print(r < 3 ? " |" : "");
  }
  Serial.println();
}

// The decoded image's own 4x4 zone means, to compare against the sensor's.
static void image_zones(const uint8_t *img, uint16_t w, uint16_t h, uint8_t out[16]) {
  for (int r = 0; r < 4; r++) {
    for (int c = 0; c < 4; c++) {
      uint32_t sum = 0, n = 0;
      for (uint16_t y = h * r / 4; y < h * (r + 1) / 4; y++)
        for (uint16_t x = w * c / 4; x < w * (c + 1) / 4; x++) { sum += img[y * w + x]; n++; }
      out[r * 4 + c] = n ? (uint8_t)(sum / n) : 0;
    }
  }
}

// Pearson correlation: are the two grids measuring the same thing?
static float correlate(const uint8_t *a, const uint8_t *b) {
  float ma = 0, mb = 0;
  for (int i = 0; i < 16; i++) { ma += a[i]; mb += b[i]; }
  ma /= 16; mb /= 16;
  float num = 0, da = 0, db = 0;
  for (int i = 0; i < 16; i++) {
    float x = a[i] - ma, y = b[i] - mb;
    num += x * y; da += x * x; db += y * y;
  }
  if (da <= 0 || db <= 0) return 0;
  return num / sqrtf(da * db);
}

// ---------------------------------------------------------------------------

static bool cam_up(framesize_t fs) {
  camera_config_t cfg = {};
  cfg.pin_pwdn = CAM_PIN_PWDN;  cfg.pin_reset = CAM_PIN_RESET;
  cfg.pin_xclk = CAM_PIN_XCLK;
  cfg.pin_sccb_sda = CAM_PIN_SIOD; cfg.pin_sccb_scl = CAM_PIN_SIOC;
  cfg.pin_d7 = CAM_PIN_D7; cfg.pin_d6 = CAM_PIN_D6;
  cfg.pin_d5 = CAM_PIN_D5; cfg.pin_d4 = CAM_PIN_D4;
  cfg.pin_d3 = CAM_PIN_D3; cfg.pin_d2 = CAM_PIN_D2;
  cfg.pin_d1 = CAM_PIN_D1; cfg.pin_d0 = CAM_PIN_D0;
  cfg.pin_vsync = CAM_PIN_VSYNC; cfg.pin_href = CAM_PIN_HREF; cfg.pin_pclk = CAM_PIN_PCLK;
  cfg.xclk_freq_hz = 20000000;
  cfg.ledc_timer = LEDC_TIMER_0; cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.pixel_format = PIXFORMAT_JPEG;
  cfg.frame_size = fs;
  cfg.jpeg_quality = 12;              // production setting
  cfg.fb_count = 2;
  cfg.fb_location = CAMERA_FB_IN_PSRAM;
  cfg.grab_mode = CAMERA_GRAB_LATEST;
  return esp_camera_init(&cfg) == ESP_OK;
}

static const char *scale_name(jpg_scale_t s) {
  switch (s) {
    case JPG_SCALE_NONE: return "1/1";
    case JPG_SCALE_2X:   return "1/2";
    case JPG_SCALE_4X:   return "1/4";
    case JPG_SCALE_8X:   return "1/8";
    default: return "?";
  }
}

// One timed decode run: N frames, at one scale.
static void bench_scale(jpg_scale_t scale, int iters) {
  uint32_t lo = 0xFFFFFFFF, hi = 0, sum = 0, jpeg_sum = 0;
  uint16_t ow = 0, oh = 0;
  int ok = 0;

  for (int i = 0; i < iters; i++) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) continue;
    // Copy out first: the timing must not include waiting on the driver, and
    // holding a frame buffer across a long decode would stall the pipeline.
    memcpy(jpeg_copy, fb->buf, fb->len);
    size_t len = fb->len;
    esp_camera_fb_return(fb);

    GrayCtx ctx = { jpeg_copy, gray_buf, 0, 0 };
    int64_t t0 = esp_timer_get_time();
    esp_err_t e = esp_jpg_decode(len, scale, rd_cb, gray_cb, &ctx);
    uint32_t dt = (uint32_t)(esp_timer_get_time() - t0);
    if (e != ESP_OK) { Serial.printf("    decode failed: %s\n", esp_err_to_name(e)); continue; }

    ow = ctx.w; oh = ctx.h;
    if (dt < lo) lo = dt;
    if (dt > hi) hi = dt;
    sum += dt; jpeg_sum += len; ok++;
  }

  if (!ok) { Serial.printf("  %-4s  no frames\n", scale_name(scale)); return; }
  Serial.printf("  %-4s  %4ux%-4u  %6.1f ms mean  (%.1f min / %.1f max)   jpeg %5u B\n",
                scale_name(scale), ow, oh,
                sum / 1000.0f / ok, lo / 1000.0f, hi / 1000.0f, jpeg_sum / ok);
}

static void bench_at(framesize_t fs, const char *label) {
  esp_camera_deinit();
  delay(200);
  if (!cam_up(fs)) { Serial.printf("\n%s: camera init FAILED\n", label); return; }
  delay(600);                                   // let AEC settle

  Serial.printf("\n--- decode cost at %s ---\n", label);
  jpg_scale_t scales[] = { JPG_SCALE_8X, JPG_SCALE_4X, JPG_SCALE_2X, JPG_SCALE_NONE };
  for (int i = 0; i < 4; i++) bench_scale(scales[i], 8);
}

void setup() {
  pinMode(PIN_FLASH_LED, OUTPUT);
  digitalWrite(PIN_FLASH_LED, LOW);

  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 2500) delay(10);
  delay(300);

  Serial.println("\n\n########## mask-cam benchmarks ##########");
  Serial.printf("built %s %s\n", __DATE__, __TIME__);

  // Big enough for a full-scale UXGA grayscale image.
  gray_buf  = (uint8_t *)ps_malloc(1600 * 1200);
  jpeg_copy = (uint8_t *)ps_malloc(512 * 1024);
  if (!gray_buf || !jpeg_copy) { Serial.println("!! no PSRAM"); while (1) delay(1000); }

  // ===== A: decode cost =====
  bench_at(FRAMESIZE_SVGA, "SVGA 800x600 (production setting)");
  bench_at(FRAMESIZE_UXGA, "UXGA 1600x1200");

  // ===== B: the OV3660 zone map =====
  esp_camera_deinit(); delay(200);
  cam_up(FRAMESIZE_SVGA); delay(800);

  Serial.println("\n--- B: OV3660 4x4 zone averages, registers 0x5691-0x56A0 ---");
  sensor_t *s = esp_camera_sensor_get();
  Serial.printf("  sensor PID 0x%04x\n", s->id.PID);

  uint8_t zones[16], overall = 0, imgz[16];
  uint32_t us = 0;
  if (!read_zones(zones, &overall, &us)) {
    Serial.println("  !! register reads FAILED -- the block is not reachable this way");
  } else {
    Serial.printf("  17 register reads took %u us\n", us);
    print_grid("sensor zones:", zones);
    Serial.printf("  %-16soverall 0x56A1 = %u\n", "", overall);

    bool all_same = true;
    for (int i = 1; i < 16; i++) if (zones[i] != zones[0]) all_same = false;
    if (all_same)
      Serial.println("  ⚠ every zone identical -- suspicious, may not be live");

    // The proof: decode the same scene and compute its own 4x4 zone means.
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) {
      memcpy(jpeg_copy, fb->buf, fb->len);
      size_t len = fb->len;
      esp_camera_fb_return(fb);
      GrayCtx ctx = { jpeg_copy, gray_buf, 0, 0 };
      if (esp_jpg_decode(len, JPG_SCALE_8X, rd_cb, gray_cb, &ctx) == ESP_OK) {
        image_zones(gray_buf, ctx.w, ctx.h, imgz);
        print_grid("decoded image:", imgz);
        Serial.printf("  correlation sensor vs image: %+.3f\n", correlate(zones, imgz));
        Serial.println("  (>+0.8 = the registers really are the scene's luminance map)");
      }
    }

    // Do they TRACK, or are they a snapshot latched at init?
    //
    // The flashlight was the obvious stimulus and it turned out to change
    // nothing -- the DECODED image did not move either, so it tested the LED,
    // not the registers. Manual exposure is a stimulus that cannot fail: drive
    // the sensor's own integration time and the whole frame must change.
    Serial.println("\n  --- response to a forced exposure sweep ---");
    Serial.println("  (AEC/AGC off, exposure driven by hand; both columns are means)");
    s->set_exposure_ctrl(s, 0);          // manual exposure
    s->set_gain_ctrl(s, 0);              // manual gain
    s->set_agc_gain(s, 0);

    const int steps[] = { 50, 200, 600, 1200, 600, 200, 50 };
    Serial.printf("  %-10s %-14s %-14s %s\n", "aec_value", "sensor 0x56A1", "sensor zonemean", "image mean");
    for (int i = 0; i < 7; i++) {
      s->set_aec_value(s, steps[i]);
      delay(700);                        // several frames at the new exposure
      esp_camera_fb_return(esp_camera_fb_get());   // discard one in-flight frame
      delay(200);

      read_zones(zones, &overall, &us);
      uint32_t zsum = 0;
      for (int k = 0; k < 16; k++) zsum += zones[k];

      uint32_t isum = 0;
      camera_fb_t *f2 = esp_camera_fb_get();
      if (f2) {
        memcpy(jpeg_copy, f2->buf, f2->len);
        size_t l2 = f2->len; esp_camera_fb_return(f2);
        GrayCtx c2 = { jpeg_copy, gray_buf, 0, 0 };
        if (esp_jpg_decode(l2, JPG_SCALE_8X, rd_cb, gray_cb, &c2) == ESP_OK) {
          image_zones(gray_buf, c2.w, c2.h, imgz);
          for (int k = 0; k < 16; k++) isum += imgz[k];
        }
      }
      Serial.printf("  %-10d %-14u %-14u %u\n", steps[i], overall, zsum / 16, isum / 16);
    }

    // How cheap is the cheapest possible gate -- one register, not seventeen?
    int64_t t1 = esp_timer_get_time();
    for (int i = 0; i < 20; i++) (void)s->get_reg(s, 0x56A1, 0xFF);
    Serial.printf("\n  one register read (0x56A1) = %.2f ms   [SCCB is 100 kHz in this SDK]\n",
                  (esp_timer_get_time() - t1) / 1000.0 / 20);

    s->set_exposure_ctrl(s, 1);          // hand it back to auto
    s->set_gain_ctrl(s, 1);
  }

  Serial.println("\n########## done ##########");
}

void loop() { delay(1000); }
