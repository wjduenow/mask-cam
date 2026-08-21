#include "ota.h"
#include "capture.h"
#include "recorder.h"
#include "detect.h"
#include "../config.h"

#include <ArduinoOTA.h>
#include <WiFi.h>
#include <esp_ota_ops.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#if defined(__has_include)
#  if __has_include("../secrets.h")
#    include "../secrets.h"
#  endif
#endif

static OtaStats st;

bool ota_password_required() {
#ifdef OTA_PASSWORD
  return true;
#else
  return false;
#endif
}

// --- quiescing -------------------------------------------------------------
//
// Three things have to stop before the app partition is written, and the
// order matters.
//
// The recorder goes first and is given time to CLOSE its clip: an AVI whose
// header was never patched will not play, so rebooting mid-clip throws away
// the last minute for no reason.
//
// The camera goes next. Writing flash stalls the cache, and a camera DMA plus
// PSRAM traffic through a stalled cache is how you get a corrupt frame or a
// watchdog reset in the middle of an update.
//
// The detector is only CPU, but there is no reason to leave it decoding
// frames that are no longer being captured.
void ota_prepare(const char *source) {
  if (st.active) return;
  st.active = true;
  st.percent = 0;
  st.received = st.total = 0;
  st.last_error[0] = 0;
  snprintf(st.source, sizeof(st.source), "%s", source);

  Serial.printf("\n[ota] %s update starting -- standing everything down\n", source);

  motion_set_enabled(false);
  if (recorder_armed()) {
    recorder_disarm();               // blocks until the writer closes the clip
    Serial.println("[ota] recording stopped and the clip closed");
  }
  capture_set_paused(true);
  vTaskDelay(pdMS_TO_TICKS(300));    // let an in-flight capture finish
}

// Only for a FAILED update. A successful one reboots, so nothing to resume.
void ota_resume() {
  st.active = false;
  capture_set_paused(false);
  motion_set_enabled(MC_MOTION_ENABLED);
  recorder_arm();
  Serial.println("[ota] update failed -- camera and recording resumed");
}

void ota_note_progress(uint32_t received, uint32_t total) {
  st.received = received;
  st.total = total;
  st.percent = total ? (uint8_t)((uint64_t)received * 100 / total) : 0;
}

void ota_note_error(const char *msg) {
  snprintf(st.last_error, sizeof(st.last_error), "%s", msg);
  Serial.printf("[ota] ERROR: %s\n", msg);
}

void ota_stats(OtaStats *out) { *out = st; }

// --- espota ----------------------------------------------------------------

static void ota_task(void *) {
  for (;;) {
    ArduinoOTA.handle();
    // 20 ms idle. During the transfer itself handle() does not return until
    // the image is in, so this rate only governs how quickly an incoming
    // request is noticed.
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

bool ota_begin() {
  memset(&st, 0, sizeof(st));

  const esp_partition_t *run = esp_ota_get_running_partition();
  snprintf(st.running_part, sizeof(st.running_part), "%s", run ? run->label : "?");
  Serial.printf("[ota] running from partition '%s'\n", st.running_part);

  if (!MC_OTA_ENABLED) return false;

  // The espota listener needs an address. The web route does not -- it rides
  // on the HTTP server -- so a board that never joined still reports its
  // partition and can still be updated once the link comes back.
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ota] no network yet -- espota listener not started");
    return false;
  }

  ArduinoOTA.setHostname(MC_HOSTNAME);
  ArduinoOTA.setPort(MC_OTA_PORT);
#ifdef OTA_PASSWORD
  ArduinoOTA.setPassword(OTA_PASSWORD);
#else
  Serial.println("[ota] WARNING: no OTA_PASSWORD in secrets.h -- anyone on this "
                 "network can reflash the mask");
#endif

  ArduinoOTA.onStart([]() { ota_prepare("espota"); });
  ArduinoOTA.onProgress([](unsigned int done, unsigned int total) {
    ota_note_progress(done, total);
    static uint8_t last = 255;
    OtaStats s; ota_stats(&s);
    if (s.percent / 10 != last) { last = s.percent / 10; Serial.printf("[ota] %u%%\n", s.percent); }
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("[ota] image received and verified -- rebooting into it");
  });
  ArduinoOTA.onError([](ota_error_t e) {
    const char *m = e == OTA_AUTH_ERROR    ? "auth failed"
                  : e == OTA_BEGIN_ERROR   ? "begin failed"
                  : e == OTA_CONNECT_ERROR ? "connect failed"
                  : e == OTA_RECEIVE_ERROR ? "receive failed"
                  : e == OTA_END_ERROR     ? "end failed" : "unknown";
    ota_note_error(m);
    // The running firmware is untouched -- only the inactive slot was being
    // written -- so put the camera back to work rather than sitting dead.
    ota_resume();
  });

  ArduinoOTA.begin();
  // Its own task so the 200 ms loop() delay cannot make OTA unresponsive, and
  // a deep stack because the whole transfer runs inside handle().
  xTaskCreatePinnedToCore(ota_task, "ota", 8192, nullptr, 4, nullptr, 0);
  Serial.printf("[ota] espota listening on %s:%d%s\n", MC_HOSTNAME, MC_OTA_PORT,
                ota_password_required() ? " (password set)" : " (NO PASSWORD)");
  return true;
}
