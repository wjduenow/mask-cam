#include "capture.h"
#include "recorder.h"
#include "../config.h"
#include "../board_pins.h"

#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>

static CapStats st;
static volatile bool paused = false;

// The published frame. One writer (the pump), several readers (stream
// clients), so a plain mutex is enough -- readers copy out and let go rather
// than holding it across a socket write, which could block for seconds.
static uint8_t         *pub_buf = nullptr;
static size_t           pub_cap = 0, pub_len = 0;
static volatile uint32_t pub_seq = 0;
static SemaphoreHandle_t pub_mtx = nullptr;

static const char *sensor_name(uint16_t pid) {
  switch (pid) {
    case OV2640_PID: return "OV2640";
    case OV3660_PID: return "OV3660";
    case OV5640_PID: return "OV5640";
    case GC2145_PID: return "GC2145";
    default:         return "unknown";
  }
}
const char *capture_sensor_name() { return sensor_name(st.sensor_pid); }

// A generous upper bound on one JPEG, so buffers are sized once rather than
// grown mid-stream. UXGA at quality 10 peaks near 200 kB; QXGA near 350 kB.
size_t capture_max_frame_bytes() { return MC_MAX_FRAME_BYTES; }

bool capture_begin() {
  memset(&st, 0, sizeof(st));

  camera_config_t cfg = {};
  cfg.pin_pwdn     = CAM_PIN_PWDN;   cfg.pin_reset    = CAM_PIN_RESET;
  cfg.pin_xclk     = CAM_PIN_XCLK;
  cfg.pin_sccb_sda = CAM_PIN_SIOD;   cfg.pin_sccb_scl = CAM_PIN_SIOC;
  cfg.pin_d7 = CAM_PIN_D7; cfg.pin_d6 = CAM_PIN_D6;
  cfg.pin_d5 = CAM_PIN_D5; cfg.pin_d4 = CAM_PIN_D4;
  cfg.pin_d3 = CAM_PIN_D3; cfg.pin_d2 = CAM_PIN_D2;
  cfg.pin_d1 = CAM_PIN_D1; cfg.pin_d0 = CAM_PIN_D0;
  cfg.pin_vsync = CAM_PIN_VSYNC; cfg.pin_href = CAM_PIN_HREF; cfg.pin_pclk = CAM_PIN_PCLK;

  cfg.xclk_freq_hz = 20000000;
  cfg.ledc_timer   = LEDC_TIMER_0;
  cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.pixel_format = PIXFORMAT_JPEG;
  cfg.frame_size   = MC_DEFAULT_FRAMESIZE;
  cfg.jpeg_quality = MC_DEFAULT_QUALITY;
  cfg.fb_count     = 2;                    // 8 MB of PSRAM; two is comfortable
  cfg.fb_location  = CAMERA_FB_IN_PSRAM;
  cfg.grab_mode    = CAMERA_GRAB_LATEST;   // never serve a stale frame

  esp_err_t err = esp_camera_init(&cfg);
  if (err != ESP_OK) {
    Serial.printf("[cam] init failed: %s\n", esp_err_to_name(err));
    return false;
  }

  sensor_t *s = esp_camera_sensor_get();
  st.sensor_pid = s->id.PID;
  st.framesize  = MC_DEFAULT_FRAMESIZE;
  st.quality    = MC_DEFAULT_QUALITY;
  st.fps_target = MC_DEFAULT_FPS;
  Serial.printf("[cam] %s (PID 0x%04x) up\n", sensor_name(st.sensor_pid), st.sensor_pid);

  pub_cap = capture_max_frame_bytes();
  pub_buf = (uint8_t *)ps_malloc(pub_cap);
  pub_mtx = xSemaphoreCreateMutex();
  if (!pub_buf || !pub_mtx) { Serial.println("[cam] no PSRAM for the publish buffer"); return false; }

  return true;
}

static void publish(camera_fb_t *fb) {
  if (fb->len > pub_cap) return;          // absurdly large; leave the last good one
  if (xSemaphoreTake(pub_mtx, pdMS_TO_TICKS(100)) != pdTRUE) return;
  memcpy(pub_buf, fb->buf, fb->len);
  pub_len = fb->len;
  pub_seq++;
  xSemaphoreGive(pub_mtx);
}

size_t capture_wait_frame(uint8_t *dst, size_t cap, uint32_t *seq, uint32_t timeout_ms) {
  uint32_t t0 = millis();
  while (pub_seq == *seq) {
    if (millis() - t0 > timeout_ms) return 0;
    vTaskDelay(pdMS_TO_TICKS(5));
  }
  if (xSemaphoreTake(pub_mtx, pdMS_TO_TICKS(200)) != pdTRUE) return 0;
  size_t n = pub_len <= cap ? pub_len : 0;
  if (n) memcpy(dst, pub_buf, n);
  *seq = pub_seq;
  xSemaphoreGive(pub_mtx);
  return n;
}

static void pump_task(void *) {
  st.running = true;
  uint32_t window_t0 = millis(), window_frames = 0;

  for (;;) {
    if (paused) { vTaskDelay(pdMS_TO_TICKS(100)); continue; }

    uint8_t fps = st.fps_target ? st.fps_target : 1;
    TickType_t period = pdMS_TO_TICKS(1000 / fps);
    if (period < 1) period = 1;
    TickType_t wake = xTaskGetTickCount();

    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      st.fails++;
      vTaskDelay(pdMS_TO_TICKS(50));
      continue;
    }

    st.width = fb->width; st.height = fb->height; st.last_len = fb->len;
    st.frames++; window_frames++;

    publish(fb);
    // Hand the frame to the recorder's queue and move on. Writing it here
    // would put the card's worst case -- measured at 240 ms on this board --
    // straight into the live view as a stutter.
    recorder_queue_frame(fb->buf, fb->len, fb->width, fb->height, fps);

    esp_camera_fb_return(fb);

    uint32_t now = millis();
    if (now - window_t0 >= 1000) {
      st.fps_actual = window_frames * 1000.0f / (now - window_t0);
      window_frames = 0; window_t0 = now;
    }

    vTaskDelayUntil(&wake, period);
  }
}

void capture_start_pump() {
  // Core 1, away from the WiFi/LwIP stack on core 0, and a deep stack because
  // the SD write path runs on it.
  xTaskCreatePinnedToCore(pump_task, "campump", 8192, nullptr, 5, nullptr, 1);
}

bool capture_set_framesize(framesize_t fs) {
  if (fs > MC_MAX_FRAMESIZE) return false;
  sensor_t *s = esp_camera_sensor_get();
  if (!s || s->set_framesize(s, fs) != 0) return false;
  st.framesize = fs;
  // The sensor needs a frame or two to settle after a size change; the pump
  // picks that up on its own.
  return true;
}

bool capture_set_quality(int q) {
  if (q < 4 || q > 63) return false;
  sensor_t *s = esp_camera_sensor_get();
  if (!s || s->set_quality(s, q) != 0) return false;
  st.quality = q;
  return true;
}

void capture_set_fps(int fps) {
  if (fps < 1) fps = 1;
  if (fps > 30) fps = 30;
  st.fps_target = fps;
}

void capture_set_paused(bool p) {
  paused = p;
  st.running = !p;
}

void capture_stats(CapStats *out) { *out = st; }
