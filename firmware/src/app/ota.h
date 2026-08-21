// ota.h — over-the-air firmware update, by two routes.
//
// Once the cover is on there is no wired path to this chip: the USB-C that
// reaches the outside world goes to the power module's charging socket, and
// the ESP32's own USB is inside the sealed bay. So this is the only way the
// firmware ever changes again, and it is the one feature whose failure mode is
// a mask that has to be unscrewed.
//
// Two routes, one mechanism:
//   espota   pio run -t upload --upload-port mask-cam.local
//   web      a file picker at /  ->  POST the raw .bin to /update
//
// Both call ota_prepare() first, which stands the camera and the recorder
// down. Neither can brick the device: Update writes to the INACTIVE app slot
// and only flips otadata once the whole image has arrived and verified.
#pragma once

#include <Arduino.h>

struct OtaStats {
  bool     active;
  uint8_t  percent;
  uint32_t received, total;
  char     source[8];        // "espota" | "web"
  char     last_error[80];
  char     running_part[16]; // which app slot is executing
};

bool ota_begin();            // starts the espota listener; safe without WiFi
void ota_prepare(const char *source);  // quiesce before writing flash
void ota_resume();           // undo ota_prepare() after a FAILED update
void ota_note_progress(uint32_t received, uint32_t total);
void ota_note_error(const char *msg);
void ota_stats(OtaStats *out);
bool ota_password_required();
