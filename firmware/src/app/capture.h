// capture.h — owns the camera, and owns the one thing everything else wants:
// the latest frame.
//
// The stream and the recorder are two consumers of one sensor. If they each
// called esp_camera_fb_get() they would halve each other's frame rate and
// starve each other unpredictably. So a single pump task grabs frames at the
// target rate, hands each one to the recorder, and publishes a copy that any
// number of stream clients can read without touching the driver.
#pragma once

#include <Arduino.h>
#include <esp_camera.h>

struct CapStats {
  bool       running;
  uint16_t   width, height;
  framesize_t framesize;
  uint8_t    quality;
  uint8_t    fps_target;
  float      fps_actual;
  uint32_t   frames;
  uint32_t   fails;        // esp_camera_fb_get() returned nothing
  uint32_t   last_len;
  uint16_t   sensor_pid;
};

bool capture_begin();
void capture_start_pump();

// Wait for a frame newer than *seq, copy it into dst, update *seq.
// Returns the byte count, or 0 on timeout. Pass *seq = 0 for "whatever is
// current". This is what the MJPEG handler and /still both run on.
size_t capture_wait_frame(uint8_t *dst, size_t cap, uint32_t *seq, uint32_t timeout_ms);
size_t capture_max_frame_bytes();

bool capture_set_framesize(framesize_t fs);
bool capture_set_quality(int q);
void capture_set_fps(int fps);

// Stand the pump down. Writing the app partition stalls the cache, and a
// camera DMA plus PSRAM traffic through that is asking for a corrupt frame or
// a watchdog. Used only by OTA.
void capture_set_paused(bool paused);

void capture_stats(CapStats *out);
const char *capture_sensor_name();
