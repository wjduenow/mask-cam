// main.cpp — mask-cam bring-up self-test.
//
// This firmware does not do anything useful yet on purpose.  It is the
// software half of the rule the rest of this project runs on: VERIFY AGAINST
// THE HARDWARE, NOT THE DATASHEET.  Before a line of application code is
// written, this asks the board itself four questions and prints the answers:
//
//   1. Is the PSRAM really there, and really 8 MB octal?
//   2. Does the camera initialise on the pin map in board_pins.h, and which
//      sensor answered?
//   3. Does a capture come back with a plausible JPEG in it?
//   4. Does the microSD mount in 1-bit mode, and can we write to it?
//
// Every answer is printed as PASS/FAIL with the measured number beside it, so
// a wrong assumption surfaces here rather than three layers into a streaming
// server.  Run this once with the board on the bench; keep it as the thing you
// re-flash when something later stops working.

#include <Arduino.h>
#include <esp_camera.h>
#include <SD_MMC.h>
#include <esp_heap_caps.h>
#include <esp_chip_info.h>
#include <esp_flash.h>

#include "board_pins.h"

static bool ok_psram = false, ok_cam = false, ok_frame = false, ok_sd = false;

// ---------------------------------------------------------------------------

static void banner(const char *s) {
  Serial.printf("\n=== %s %.*s\n", s, (int)(60 - strlen(s)), "==========================================================");
}

static void result(const char *name, bool pass, const char *fmt, ...) {
  char detail[160];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(detail, sizeof(detail), fmt, ap);
  va_end(ap);
  Serial.printf("  [%s] %-22s %s\n", pass ? "PASS" : "FAIL", name, detail);
}

static const char *sensor_name(uint16_t pid) {
  switch (pid) {
    case OV2640_PID: return "OV2640";
    case OV3660_PID: return "OV3660";
    case OV5640_PID: return "OV5640";
    case OV7725_PID: return "OV7725";
    case OV7670_PID: return "OV7670";
    case GC2145_PID: return "GC2145";
    default:         return "unrecognised";
  }
}

// --- 1. the silicon --------------------------------------------------------

static void report_chip() {
  banner("chip");

  esp_chip_info_t chip;
  esp_chip_info(&chip);
  // chip.revision is a bare number on this IDF, not major*100+minor -- it
  // reads 0 on a part esptool calls v0.2. Print it raw rather than inventing
  // a decimal point that is not there.
  Serial.printf("  ESP32-S3 rev %d, %d core(s) @ %lu MHz\n",
                chip.revision, chip.cores, (unsigned long)getCpuFrequencyMhz());

  uint32_t flash_bytes = 0;
  esp_flash_get_size(NULL, &flash_bytes);
  Serial.printf("  flash %.1f MB, sketch %lu bytes in a %lu byte partition\n",
                flash_bytes / (1024.0 * 1024.0),
                (unsigned long)ESP.getSketchSize(),
                (unsigned long)(ESP.getSketchSize() + ESP.getFreeSketchSpace()));

  // The board carries 8 MB of OCTAL PSRAM.  If platformio.ini's memory_type
  // is wrong this comes back either zero or ~2 MB, and the camera then quietly
  // refuses any framesize above SVGA.  That failure is much easier to read
  // here than it is three layers up.
  size_t psram = ESP.getPsramSize();
  ok_psram = psram > 4 * 1024 * 1024;
  result("PSRAM", ok_psram, "%u bytes (%.1f MB), %u free",
         (unsigned)psram, psram / (1024.0 * 1024.0), (unsigned)ESP.getFreePsram());
  if (!ok_psram)
    Serial.println("        -> expected ~8 MB. Check board_build.arduino.memory_type = qio_opi");

  Serial.printf("  internal heap %u free of %u\n",
                (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getHeapSize());
}

// --- 2 and 3. the camera ---------------------------------------------------

static void report_camera() {
  banner("camera");

  camera_config_t cfg = {};
  cfg.pin_pwdn      = CAM_PIN_PWDN;
  cfg.pin_reset     = CAM_PIN_RESET;
  cfg.pin_xclk      = CAM_PIN_XCLK;
  cfg.pin_sccb_sda  = CAM_PIN_SIOD;
  cfg.pin_sccb_scl  = CAM_PIN_SIOC;
  cfg.pin_d7        = CAM_PIN_D7;
  cfg.pin_d6        = CAM_PIN_D6;
  cfg.pin_d5        = CAM_PIN_D5;
  cfg.pin_d4        = CAM_PIN_D4;
  cfg.pin_d3        = CAM_PIN_D3;
  cfg.pin_d2        = CAM_PIN_D2;
  cfg.pin_d1        = CAM_PIN_D1;
  cfg.pin_d0        = CAM_PIN_D0;
  cfg.pin_vsync     = CAM_PIN_VSYNC;
  cfg.pin_href      = CAM_PIN_HREF;
  cfg.pin_pclk      = CAM_PIN_PCLK;

  cfg.xclk_freq_hz  = 20000000;
  cfg.ledc_timer    = LEDC_TIMER_0;
  cfg.ledc_channel  = LEDC_CHANNEL_0;
  cfg.pixel_format  = PIXFORMAT_JPEG;
  cfg.frame_size    = ok_psram ? FRAMESIZE_UXGA : FRAMESIZE_SVGA;
  cfg.jpeg_quality  = 12;                       // 0 best .. 63 worst
  cfg.fb_count      = ok_psram ? 2 : 1;
  cfg.fb_location   = ok_psram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  cfg.grab_mode     = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&cfg);
  ok_cam = (err == ESP_OK);
  result("camera init", ok_cam, "%s (0x%04x)", esp_err_to_name(err), err);
  if (!ok_cam) {
    Serial.println("        -> ribbon seated both ends? pin map in board_pins.h?");
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  Serial.printf("  sensor PID 0x%04x -> %s, MIDL/MIDH 0x%02x%02x\n",
                s->id.PID, sensor_name(s->id.PID), s->id.MIDH, s->id.MIDL);

  // The lens looks out of the brow of a mask that hangs on a wall, so the
  // sensor's own orientation is the only thing that can fix an upside-down
  // image once it is glued in.  Recorded here, not corrected: which way is up
  // is a question for when the thing is actually mounted.
  Serial.printf("  defaults: framesize %d, quality %d, vflip %d, hmirror %d\n",
                s->status.framesize, s->status.quality,
                s->status.vflip, s->status.hmirror);

  // A capture that returns a buffer is not the same as a capture that returns
  // a PICTURE.  A dead ribbon on the data lines still hands back a frame --
  // one that is all zeroes.  So check the JPEG SOI marker and a sane length.
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    result("capture", false, "esp_camera_fb_get() returned NULL");
    return;
  }
  bool soi = fb->len > 2 && fb->buf[0] == 0xFF && fb->buf[1] == 0xD8;
  ok_frame = soi && fb->len > 1000;
  result("capture", ok_frame, "%ux%u, %u bytes, SOI %s",
         fb->width, fb->height, (unsigned)fb->len, soi ? "ok" : "MISSING");
  if (!ok_frame)
    Serial.println("        -> a tiny or SOI-less frame usually means the DVP data lines");

  esp_camera_fb_return(fb);
}

// --- 4. the card -----------------------------------------------------------

static void report_sd() {
  banner("microSD");

  // Only CMD/CLK/DAT0 are wired on this board, so 1-bit is the only mode
  // available -- the 4-bit default would fail here for a reason that has
  // nothing to do with the card.
  SD_MMC.setPins(SD_PIN_CLK, SD_PIN_CMD, SD_PIN_D0);
  if (!SD_MMC.begin("/sdcard", true /* 1-bit */, false /* no format */)) {
    result("mount", false, "SD_MMC.begin() failed");
    Serial.println("        -> card seated? FAT32? 1-bit pins 39/38/40?");
    return;
  }

  uint8_t type = SD_MMC.cardType();
  if (type == CARD_NONE) {
    result("mount", false, "mounted but cardType() == NONE");
    return;
  }
  const char *tname = type == CARD_MMC ? "MMC" : type == CARD_SD ? "SDSC"
                    : type == CARD_SDHC ? "SDHC" : "unknown";
  Serial.printf("  card %s, %llu MB, %llu MB used\n", tname,
                SD_MMC.cardSize() / (1024ULL * 1024ULL),
                SD_MMC.usedBytes() / (1024ULL * 1024ULL));

  // Mounting proves the card answers.  Only a write proves it is usable, and
  // a write-protected or worn card mounts perfectly and then silently drops
  // everything you record.  Write, read back, compare.
  const char *probe = "/masktest.txt";
  const char *msg   = "mask-cam bring-up";
  File f = SD_MMC.open(probe, FILE_WRITE);
  if (!f) { result("write", false, "could not open %s", probe); return; }
  f.print(msg);
  f.close();

  f = SD_MMC.open(probe, FILE_READ);
  String back = f ? f.readString() : String();
  if (f) f.close();
  SD_MMC.remove(probe);

  bool wrote = back == msg;
  result("write + readback", wrote, "%s", wrote ? "round-tripped" : "MISMATCH");
  ok_sd = wrote;

  // And if the camera worked, park a real frame on the card.  Pull the card,
  // open the file: that is the end-to-end proof that lens, sensor, ribbon,
  // PSRAM and card all work together.
  if (ok_frame) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) {
      File img = SD_MMC.open("/selftest.jpg", FILE_WRITE);
      if (img) {
        size_t n = img.write(fb->buf, fb->len);
        img.close();
        result("saved frame", n == fb->len, "/selftest.jpg, %u of %u bytes",
               (unsigned)n, (unsigned)fb->len);
      }
      esp_camera_fb_return(fb);
    }
  }
}

// --- looking at a frame ----------------------------------------------------
//
// Every check above measures the frame. None of them SEES it. A lens still
// under its protective film, a sensor staring at the inside of the bay, a
// ribbon in backwards -- all of those produce a structurally perfect JPEG of
// nothing. So: send one up the wire, base64, and open it at the other end.
//
// Press 'p' in a serial monitor, or let the host tooling send it. The frame
// arrives between the two markers below.

static const char B64[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

// HWCDC::write() returns a SHORT count when the host is not reading fast
// enough, and Print throws that away -- which loses bytes out of the middle of
// a dump without a word. Write the remainder until it is gone.
static bool serial_write_all(const uint8_t *p, size_t n) {
  size_t sent = 0;
  uint32_t stalls = 0;
  while (sent < n) {
    size_t w = Serial.write(p + sent, n - sent);
    sent += w;
    if (w == 0) {
      if (++stalls > 2000) return false;
      delay(1);
    } else {
      stalls = 0;
    }
  }
  return true;
}

static void dump_frame_base64() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { Serial.println("!! capture failed, nothing to dump"); return; }

  Serial.setTxTimeoutMs(1000);

  Serial.printf("---BEGIN JPEG %ux%u %u---\n", fb->width, fb->height,
                (unsigned)fb->len);

  // Encoded in place, 57 input bytes per line, so nothing the size of the
  // frame is ever allocated twice.
  char line[80];
  size_t i = 0;
  while (i < fb->len) {
    size_t n = fb->len - i;
    if (n > 57) n = 57;
    size_t o = 0;
    for (size_t j = 0; j < n; j += 3) {
      uint32_t v = (uint32_t)fb->buf[i + j] << 16;
      if (j + 1 < n) v |= (uint32_t)fb->buf[i + j + 1] << 8;
      if (j + 2 < n) v |= (uint32_t)fb->buf[i + j + 2];
      line[o++] = B64[(v >> 18) & 63];
      line[o++] = B64[(v >> 12) & 63];
      line[o++] = (j + 1 < n) ? B64[(v >> 6) & 63] : '=';
      line[o++] = (j + 2 < n) ? B64[v & 63]        : '=';
    }
    line[o++] = '\n';
    if (!serial_write_all((const uint8_t *)line, o)) {
      Serial.setTxTimeoutMs(100);
      Serial.println("---ABORTED JPEG---");
      esp_camera_fb_return(fb);
      return;
    }
    i += n;
  }

  Serial.setTxTimeoutMs(100);
  Serial.println("---END JPEG---");
  esp_camera_fb_return(fb);
}

// ---------------------------------------------------------------------------

void setup() {
  // GPIO3 is the flashlight. Kill it FIRST and leave it dead: this board ends
  // up sealed inside a mask whose cover vents leak light, and there is no
  // reason for it ever to come on.
  pinMode(PIN_FLASH_LED, OUTPUT);
  digitalWrite(PIN_FLASH_LED, LOW);

  Serial.begin(115200);
  // Native USB CDC: the port only exists once the host has enumerated it, and
  // anything printed before that is lost.  Wait, but never forever -- this
  // board has to boot standalone on battery too.
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);
  delay(200);

  Serial.println("\n\n#############################################");
  Serial.println("#  mask-cam bring-up self-test");
  Serial.printf ("#  built %s %s\n", __DATE__, __TIME__);
  Serial.println("#############################################");

  report_chip();
  report_camera();
  report_sd();

  banner("summary");
  Serial.printf("  PSRAM %s | camera %s | frame %s | microSD %s\n",
                ok_psram ? "ok" : "NO", ok_cam ? "ok" : "NO",
                ok_frame ? "ok" : "NO", ok_sd ? "ok" : "NO");
  Serial.println(ok_psram && ok_cam && ok_frame && ok_sd
                 ? "  ALL PASS -- the board is ready for application firmware."
                 : "  SOMETHING FAILED -- fix it here before building on top of it.");
  Serial.println("\nHeartbeat: one capture every 5 s, so a fault that only shows up warm\n"
                 "or on battery has somewhere to show up.\n");
}

void loop() {
  static uint32_t n = 0;
  if (!ok_cam) { delay(5000); return; }

  // 'p' -> send a frame up the wire to be looked at.
  while (Serial.available()) {
    if (Serial.read() == 'p') dump_frame_base64();
  }

  uint32_t t0 = millis();
  camera_fb_t *fb = esp_camera_fb_get();
  uint32_t dt = millis() - t0;

  if (!fb) {
    Serial.printf("[%6lu] capture FAILED\n", (unsigned long)++n);
  } else {
    Serial.printf("[%6lu] %ux%u %6u bytes in %3lu ms | heap %u | psram %u\n",
                  (unsigned long)++n, fb->width, fb->height, (unsigned)fb->len,
                  (unsigned long)dt, (unsigned)ESP.getFreeHeap(),
                  (unsigned)ESP.getFreePsram());
    esp_camera_fb_return(fb);
  }

  // Broken into short naps so a 'p' is answered promptly rather than whenever
  // the heartbeat next comes round.
  for (int i = 0; i < 50 && !Serial.available(); i++) delay(100);
}
