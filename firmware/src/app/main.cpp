// main.cpp — mask-cam application firmware.
//
// A camera sealed inside a wall-hung mask: live MJPEG on the LAN, MJPEG AVI
// clips onto the microSD, and a web UI to arm and disarm the recording.
//
// If something here misbehaves, flash the OTHER environment first:
//
//     pio run -e selftest -t upload
//
// That one answers "is the hardware even working" in twenty seconds, and it is
// much easier to read than a fault three layers into a streaming server.

#include <Arduino.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <time.h>

#include "../board_pins.h"
#include "../config.h"
#include "capture.h"
#include "recorder.h"
#include "web.h"

// The one file that is not in the repository. Fail loudly and usefully rather
// than with forty lines of "WIFI_SSID was not declared in this scope".
#if defined(__has_include)
#  if __has_include("../secrets.h")
#    include "../secrets.h"
#  else
#    error "firmware/src/secrets.h is missing. cp src/secrets.h.example src/secrets.h and fill in your WiFi."
#  endif
#else
#  include "../secrets.h"
#endif

static bool wifi_up = false;

// --- USB console -----------------------------------------------------------
// Everything the web UI can do, reachable over the wire. This is not a
// debugging luxury: the board finishes up behind a screwed-down cover, and the
// day WiFi is the thing that broke is the day you need another way in.

static void console_status() {
  CapStats c; capture_stats(&c);
  RecStats s; recorder_stats(&s);
  Serial.printf("camera  %s  %ux%u  %.1f fps (target %u)  %u frames, %u fails\n",
                capture_sensor_name(), c.width, c.height, c.fps_actual,
                c.fps_target, c.frames, c.fails);
  Serial.printf("record  %s  %s  %u frames  %.2f MB\n",
                s.armed ? "ARMED" : (s.paused_for_space ? "PAUSED (no room)" : "idle"),
                s.clip[0] ? s.clip : "-",
                s.clip_frames, s.clip_bytes / 1048576.0);
  Serial.printf("card    %llu MB free of %llu  |  %u written, %u ring-deleted  |  write %u/%u ms\n",
                (unsigned long long)s.card_free_mb, (unsigned long long)s.card_total_mb,
                s.clips_written, s.clips_deleted, s.write_ms_last, s.write_ms_max);
  Serial.printf("ring    %s\n", s.ring ? "ON -- oldest clips are deleted to make room"
                                        : "off -- recording stops when the card fills");
  Serial.printf("queue   %u/%u slots in use  |  %u frames dropped\n",
                s.queue_depth, MC_REC_QUEUE_SLOTS, s.frames_dropped);
  Serial.printf("net     %s  %s  rssi %d\n",
                wifi_up ? "up" : "DOWN", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  Serial.printf("health  %.0f C  heap %u  psram %u  up %lus\n",
                temperatureRead(), (unsigned)ESP.getFreeHeap(),
                (unsigned)ESP.getFreePsram(), (unsigned long)(millis() / 1000));
  if (s.last_error[0]) Serial.printf("error   %s\n", s.last_error);
}

static void console(char c) {
  switch (c) {
    case 's': console_status(); break;
    case 'r':
      if (recorder_armed()) { recorder_disarm(); Serial.println("recording stopped"); }
      else                  { recorder_arm();    Serial.println("recording started"); }
      break;
    case 'l': recorder_print_listing(); break;
    case 'd': {                       // dump the newest clip, base64
      char name[64];
      if (recorder_newest_clip(name, sizeof(name))) recorder_dump_base64(name);
      else Serial.println("no clips yet");
      break;
    }
    case '?':
      Serial.println("s status  r record on/off  l list clips  d dump newest clip");
      break;
    default: break;
  }
}

static void wifi_connect() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(MC_HOSTNAME);
  // Modem sleep OFF, and this was measured rather than assumed. With it on,
  // the board answered a ping in 306-1244 ms and HTTP would not complete at
  // all: the radio parks between beacons, and on a weak link it misses them.
  // It also saves nothing in the case that matters -- streaming keeps the
  // radio busy continuously. The cost is a few tens of milliamps at idle.
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.printf("[net] joining \"%s\"", WIFI_SSID);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();

  wifi_up = WiFi.status() == WL_CONNECTED;
  if (!wifi_up) {
    Serial.println("[net] no join. Check SSID/password in src/secrets.h --");
    Serial.println("[net] the S3 has no 5 GHz radio, so a 5 GHz-only SSID will never appear.");
    return;
  }

  Serial.printf("[net] %s  rssi %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());

  if (MDNS.begin(MC_HOSTNAME)) {
    MDNS.addService("http", "tcp", MC_HTTP_PORT);
    Serial.printf("[net] http://%s.local/\n", MC_HOSTNAME);
  }

  // Clips are named by wall-clock time when there is one. Not fatal if NTP is
  // unreachable -- the recorder falls back to a counter.
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
}

void setup() {
  // GPIO3 is the flashlight. Kill it FIRST and leave it dead: this board ends
  // up sealed inside a mask whose cover vents leak light both ways, and there
  // is no reason for it ever to come on.
  pinMode(PIN_FLASH_LED, OUTPUT);
  digitalWrite(PIN_FLASH_LED, LOW);

  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 2000) delay(10);

  Serial.println("\n\n=== mask-cam ===");
  Serial.printf("built %s %s\n", __DATE__, __TIME__);
  Serial.printf("psram %u bytes\n", (unsigned)ESP.getPsramSize());

  if (!capture_begin()) {
    Serial.println("!! camera did not start. Flash the selftest environment.");
    // No reboot loop: a board that reboots forever is a board you cannot talk
    // to. Sit here so the serial console still says what happened.
    while (true) delay(1000);
  }

  if (recorder_begin()) {
    recorder_start_writer();
    recorder_start_housekeeper();
    // Armed here, and the capture pump starts before the network below, so
    // the first frame is on the card seconds after power -- not twenty
    // seconds later when the join finishes. On a cold start there is no clock
    // yet, so that first clip is named "noclock"; its sequence number still
    // places it correctly against everything else on the card.
    if (MC_RECORD_ON_BOOT && recorder_arm())
      Serial.println("[rec] armed on boot");
  } else {
    Serial.println("!! no microSD. Streaming will work; recording will not.");
  }

  // The pump goes BEFORE the network, and this is the whole point of arming on
  // boot. Joining a WiFi network takes twenty seconds when it works and twenty
  // seconds when it does not, and no frame exists until the pump is running --
  // so starting it after the join threw away exactly the moment that recording
  // on boot is meant to catch. Nothing here needs an IP address.
  capture_start_pump();

  wifi_connect();

  if (!web_begin())
    Serial.println("!! http server did not start");

  Serial.println("ready.  ? for the console commands\n");
}

void loop() {
  static uint32_t last_beat = 0, last_net = 0;

  // WiFi drops happen, and this thing is behind a screwed-down cover. Notice,
  // and rejoin, without taking the camera or the recorder down with it.
  if (millis() - last_net > 10000) {
    last_net = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[net] link lost, reconnecting");
      WiFi.reconnect();
    }
  }

  while (Serial.available()) console(Serial.read());

  if (millis() - last_beat > 30000) {
    last_beat = millis();
    CapStats c; capture_stats(&c);
    RecStats s; recorder_stats(&s);
    Serial.printf("[%lus] %ux%u %.1f fps | %s | card %llu MB free | %.0f C | heap %u\n",
                  (unsigned long)(millis() / 1000), c.width, c.height, c.fps_actual,
                  s.armed ? s.clip : "idle",
                  (unsigned long long)s.card_free_mb,
                  temperatureRead(), (unsigned)ESP.getFreeHeap());
  }

  delay(200);
}
