# firmware — the software half of mask-cam

The board is a **nulllab / emakefun ESP32-S3-CAM**, silkscreen `SP32S3 CAM V1.1`.
Everything here follows the same rule the CAD side runs on: **verify against the hardware,
not the datasheet.** What is written down was read off the part in hand.

Two environments:

| | what it is | when |
|---|---|---|
| **`mask-cam`** | the real thing — live MJPEG, AVI clips to microSD, web UI | default |
| **`selftest`** | four questions the board answers about itself, in 20 s | when in doubt |

---

## Confirmed against this board, 2026-08-20

| | | how |
|---|---|---|
| chip | ESP32-S3, rev v0.2, 2 cores @ 240 MHz | `esptool flash_id` |
| flash | **8 MB**, eFuse says **quad** | `esptool flash_id` |
| PSRAM | **8 MB octal** | `ESP.getPsramSize()` |
| sensor | **OV3660** — PID `0x3660` | `esp_camera_sensor_get()` |
| microSD | 32 GB SDHC, mounts **1-bit**, write round-trips | selftest |
| USB | the S3's **own** USB (`303a:1001`), no bridge chip | `lsusb` |
| SVGA frame | 21–69 kB, mean **25 kB** at quality 12 | 454-frame clip |
| sustained | **10.0 fps at 800×600 while recording**, <1 % dropped | 44 s + 10 min runs |
| clip size | ~8–16 MB per 60 s clip at SVGA/10 fps | the card |
| WiFi join | 4 of 4 boots, ~3 s each, with the camera already running | reboot trials |
| SD write | typically 40 ms, **worst 299 ms** | see "the queue" below |
| card life | ~0.27 MB/s at SVGA/10 fps → **~30 h** on 32 GB | measured |
| WiFi | joins, **−76 dBm** from the bench to the AP | `/health` |
| clock | NTP answers; clips name themselves `20260821-055559.avi` | the card |

The pin map is in `src/board_pins.h`, from the vendor's own repo,
[nulllaborg/esp32s3-cam](https://github.com/nulllaborg/esp32s3-cam). Two independent things
corroborate it: the flash and PSRAM sizes it claims match what the part reports, and the
GPIO3 flashlight it names is the LED the main README's cover section already warned leaks
out through the vent slots.

## Setting it up

```bash
cp src/secrets.h.example src/secrets.h     # then put your WiFi in it
$EDITOR src/secrets.h                      # gitignored; it never leaves this machine

~/.platformio/penv/bin/pio run -t upload             # the application
~/.platformio/penv/bin/pio run -e selftest -t upload # the bring-up checks
```

Then `http://mask-cam.local/` — live view, a record button, the clip list, and a health
readout. The stream is on port **81**; the page knows this.

**It records on its own.** The board arms itself as soon as the card mounts — before the
network, so the first frame is on the card seconds after power rather than twenty seconds
later — and keeps a **rolling window** by deleting the oldest clip when the card runs low.
Roughly **30 hours** at SVGA/10 fps. Nothing has to be pressed, and a power cut cannot
leave it streaming happily and recording nothing. Both behaviours are `#define`s in
`config.h` (`MC_RECORD_ON_BOOT`, `MC_DEFAULT_RING`), and the ring has a checkbox in the UI.

⚠️ **Ring mode destroys the oldest footage by design.** That is the point of it, but it is
worth saying out loud: anything you want to keep has to come off the card.

All of it was exercised against the board on 2026-08-21: the page, `/still` (800×600 JPEG),
`/stream` (multipart, 27 frames in 10 s), `/rec` on and off, `/files`, `/download` and
`/delete`, plus the path-traversal guards on the last two. A clip pulled over HTTP and the
same clip pulled over USB came back **byte-identical**, and ffprobe opens both.

`pio device monitor` needs a real terminal and dies without one, so:

```bash
~/.platformio/penv/bin/python tools/board.py log 25          # reset, print output
~/.platformio/penv/bin/python tools/board.py frame out.jpg   # grab a picture, LOOK at it
```

## Talking to it over USB

The board finishes up behind a screwed-down cover, and the day WiFi is the thing that broke
is the day you need another way in. Everything the web UI does, the USB console does:

| | |
|---|---|
| `s` | status — fps, clip, card, queue, temperature, link |
| `r` | start / stop recording |
| `l` | list the clips on the card |
| `d` | dump the newest clip as base64, to be decoded at the other end |
| `m` | recent motion events |
| `?` | this list |

## How it fits together

```
  OV3660 ──► capture pump (core 1) ──┬──► published frame ──► /stream, /still
                 10 fps              │
                                     └──► 4-slot PSRAM queue ──► writer (core 0) ──► AVI
```

Three decisions worth knowing:

**One pump, not two consumers.** The stream and the recorder both want frames from one
sensor. If each called `esp_camera_fb_get()` they would halve each other's rate and starve
each other unpredictably. A single task grabs at the target rate and publishes; everything
else reads the publication.

**The card gets its own task.** This was measured, not guessed. With the SD write on the
capture path, a 240 ms write spike showed up as a stutter in the live view and pulled the
sensor from 10.0 fps down to 7.7. Moving it behind a four-slot queue holds a steady 10.0.
When the queue fills, frames are **dropped and counted** rather than silently stretching
the frame interval — a recording that quietly runs slow is worse than one that admits it
lost four frames. `dropped` is on the health page for exactly this reason.

**Clips, not one long file, and each one kept real on the card.** AVI stores sizes it
cannot know until the file is finished, so the header goes down as zeroes and is patched
at close. Patched *only* at close, an interrupted clip is not truncated — it is **zero
bytes**, because nothing reaches the directory entry until then. Measured, not assumed:
two 0-byte files turned up on the card after resets, and the README used to claim a power
cut cost you the tail of a clip when it actually cost the whole minute.

So the header is patched and the file synced every **5 s** while recording. A clip cut
short by a power failure now plays up to the last sync: a simulated cut left a 7.4 MB file
that ffprobe reads as 506 frames / 50.6 s and ffmpeg decodes without a single error.
`AVIF_HASINDEX` is deliberately set only at close, so an interrupted clip never advertises
an index that was never written. Anything still smaller than a header is swept at boot —
an always-on camera behind a screwed-down cover would otherwise collect one dead file per
power blip forever.

**Every clip carries a sequence number.** `000700001_20260821-143808.avi` is boot 7, clip 1.
Ring mode has to answer "which is oldest" at all times, including the seconds after boot
when there is no clock yet, and neither obvious answer survives that — see the note in
`recorder.cpp`. One NVS write per boot, not per clip.

## Motion detection — Phase 1: it annotates, it does not gate

The ring records everything exactly as before. The detector only writes events
beside the footage, into `/motion.log`, each one naming the clip **and the offset
into it**. A wrong threshold therefore costs a wrong label, never footage — which
matters when the thing being tuned is behind a screwed-down cover.

```
GET /motion?n=40     recent events, newest first
GET /motion?clear=1  wipe the log
```
```json
{"t":"2026-08-21 15:51:04","clip":"001400000_20260821-155006.avi",
 "into":55,"blocks":3,"total":108,"lum":53}
```

**How it works, and why each piece is there:**

- **Decode at `JPG_SCALE_8X` only.** SVGA → 100×75, **39 ms measured on this board**
  (and 39 ms again under live streaming + recording, not just on the bench). The
  other scales cost ~310–340 ms because only 1/8 skips the IDCT — see
  "Benchmarks" below. At 2 Hz this is ~8 % of one core.
- **Straight to grayscale in the decode callback**, so the 1.44 MB RGB888 image is
  never materialised at all.
- **Count changed 8×8 blocks, never summed difference.** A 5 % brightness step and
  a person occupying 5 % of frame are *numerically identical* under sum-of-absolute-
  difference. Counting blocks separates them — and only a block count makes the
  next item possible.
- **Reject changes that are too global.** Above `mot_pct` (60 %) of blocks changed,
  it is lighting or the AEC, never a person. This is the single highest-value
  false-positive defence there is, and only two projects in the wild implement it.
- **A second, cheaper veto**: the OV3660's overall luminance register `0x56A1`,
  **0.65 ms** per read. Useless as a detector — it is one global number — which is
  exactly what makes it a lighting-change detector. Measured as a *percentage*,
  because the value is linear-domain and compresses into single digits in a dark
  room.
- **Rebaseline immediately** after any rejected change, or the lighting step trails
  into the next comparison as fake motion.
- **Two consecutive hits** (1 s at 2 Hz), a 15 s warm-up while AEC/AWB settle, and
  a 5 s cooldown so one person walking through is one event.

**Verified on the board, 2026-08-21:** the trigger path end-to-end (forced sensitive,
events logged with clip and offset, cooldown spacing them exactly 5 s apart); the
global rejector (a 2 % ceiling turned sensor noise into 14 rejections and no events);
and no effect on recording — still 10.0 fps, still 56 °C. Dropping JPEG quality from
12 to 30 changed **0 of 108 blocks**, so the 8×8 averaging at 1/8 scale is inherently
immune to compression artefacts.

**Not verified: whether it discriminates real motion.** That needs a person walking
past, and it is the entire point of Phase 1 — run it for a week, read `/motion.log`,
and tune `mot_diff` / `mot_min` / `mot_pct` live from the UI without reflashing.

⚠ Expect a **TV or monitor in frame to trigger constantly.** A screen is *genuine*
pixel motion; no frame-differencing detector rejects it. That needs region masking,
which Phase 1 does not have.

## Benchmarks — `pio run -e bench`

Two numbers this design hinged on, measured here rather than taken from the web.

**Decode cost.** It is a cliff, not a slope — only 1/8 skips the IDCT:

| scale | out | SVGA | UXGA |
|---|---|---|---|
| **1/8** | 100×75 | **39.4 ms** | 151.9 ms |
| 1/4 | 200×150 | 307.9 ms | 1226 ms |
| 1/2 | 400×300 | 341.3 ms | 1362 ms |
| 1/1 | 800×600 | 310.9 ms | 1241 ms |

So there is exactly one usable scale for detection, and it is cheap enough that no
JPEG-length prefilter is needed to avoid it.

**The OV3660's 4×4 zone map at `0x5691–0x56A0` is real** — it reads back correlating
**+0.968** with the decoded image's own zone means, and tracks a forced exposure sweep
monotonically in both directions. As far as the research found, no ESP32 project reads
it. **But it is not the free pre-gate it looks like:** 17 SCCB reads take **11.0 ms**,
not the sub-millisecond the datasheet arithmetic suggests, because SCCB runs at 100 kHz
and that is fixed in the prebuilt SDK. Sixteen numbers for 11 ms against 7 500 pixels
for 39 ms is a bad trade, so only the single overall register survives, as the veto
above.

*(The first stimulus tried was the GPIO3 flashlight. It moved neither the registers nor
the decoded image, so it tested the LED, not the sensor. Exposure is a stimulus that
cannot fail.)*

## Testing the ring

The card holds ~30 hours, so waiting for it to fill is not a test. The water marks are
overridable from the build — set the target just below what is actually free and the ring
runs in seconds:

```bash
FREE=$(curl -s http://mask-cam.local/health | python3 -c "import json,sys;print(json.load(sys.stdin)['card_free_mb'])")
PLATFORMIO_BUILD_FLAGS="-DMC_FREE_TARGET_MB=$((FREE-4)) -DMC_FREE_FLOOR_MB=$((FREE-40)) -DMC_CLIP_SECONDS=10" \
  ~/.platformio/penv/bin/pio run -e mask-cam -t upload
```

Done here on 2026-08-21: it settled into deleting exactly one clip per clip written, oldest
first, in strict sequence order, holding 10.0 fps throughout — and it deleted the previous
boot's clips before the current boot's, which is the ordering the sequence prefix exists
for. **Reflash without the flags afterwards.**

### ⚠ The radio is the bottleneck, not the board

At **−76 dBm** — the bench, one floor from the AP — the numbers are sobering:

| | |
|---|---|
| live stream | ~2.7 fps of the 10 the sensor is producing |
| clip download | **~25 kB/s**, so a 14 MB clip takes about nine minutes |

Nothing in the firmware is the limit here; the camera holds 10.0 fps throughout and the
card takes it. This is signal strength, and the mask is going to hang somewhere with a
metal-free but not necessarily closer line to the AP. If the stream matters more than the
resolution, drop the framesize — VGA or QVGA in the UI costs a quarter of the bytes. If
retrieval matters, pull the card; USB is ten times faster than this link.

## Things that will waste your time if you rediscover them

- **`board_build.arduino.memory_type = qio_opi`, and do not "tidy" it.** The flash is quad
  but the PSRAM is octal. Set it to `qio_qspi` and PSRAM comes back zero, the camera
  silently refuses any framesize above SVGA, and nothing says why.
- **`ARDUINO_USB_MODE=1` + `ARDUINO_USB_CDC_ON_BOOT=1` are load-bearing.** The USB-C goes
  to the S3's native USB. Without these, `Serial` goes to UART0 — which is not wired to
  anything you can see, so a perfectly working board looks dead.
- **The microSD has only CMD/CLK/DAT0 wired.** 1-bit is not a fallback, it is the only
  mode. `SD_MMC.begin()` with its 4-bit default fails for a reason that has nothing to do
  with the card.
- **`pio device monitor` needs a TTY** — `termios.error: Inappropriate ioctl for device` is
  the monitor failing, not the board. `tools/board.py` exists for this.
- **A capture that returns a buffer is not a capture that returns a picture.** A dead data
  line still hands back a structurally valid, entirely black JPEG. The selftest checks the
  SOI marker and a plausible length; your eyes check the rest.
- **The fallback clip counter used to restart at 1 on every boot** and overwrote
  `clip0001.avi` without a word. It now asks the card what already exists. If NTP answers,
  clips are named by wall-clock time and the question does not arise.
- **This IDF's `esp_http_server` has no `HTTPD_503_SERVICE_UNAVAILABLE`.** Set the status
  line by hand, or tell a viewer the mask is broken when it is merely busy.
- **`WiFi.setSleep(true)` makes the board effectively unreachable.** Modem sleep parks the
  radio between beacons; measured here, it turned a ping into **306–1244 ms** and HTTP
  would not complete at all. With it off the same link answers in ~117 ms. It also saves
  nothing in the case that matters, because streaming keeps the radio busy anyway. This
  was a deliberate choice for heat, and the measurement overruled it.
- **`HWCDC::write()` returns a SHORT count when the host stops reading, and every `Print`
  method throws that return value away.** This silently lost 16 kB out of the middle of a
  4 MB USB dump — producing a file that still opened and still played. Anything that
  pushes bulk data over USB has to loop on the return value; `serial_write_all()` does.
  `tools/board.py clip` checks the byte count against the size the board announced, and
  the board says `---ABORTED FILE---` rather than `---END FILE---` if it gave up.
- **Never order clips by wall-clock anything.** Ring mode deletes the oldest, so "which is
  oldest" must be answerable in the seconds after boot when there is no clock. By filename,
  two naming schemes coexist and `"20260821-…" < "clip0001.avi"` because `'2' < 'c'` — the
  ring eats the newest first. By mtime, every boot's first clip carries 1970 and is deleted
  first, and that is the moment the power came back. Both were tried; both were wrong. The
  sequence prefix is the fix, and it costs one NVS write per boot.
- **`File::flush()` is what makes a file exist.** Without it the size stays 0 in the
  directory entry no matter how many megabytes have been written, and a reset loses all of
  it. This is not an AVI quirk, it is FAT.
- Under WSL the board arrives over `usbipd`. A reset re-enumerates it, and the attachment
  can drop with it.

## Open

- ⚠ **The sensor is an OV3660, and the main README's optics section assumes an OV2640.**
  The 79° unvignetted cone was checked against "a stock OV2640 lens is 65–70°". That
  conclusion probably survives — OV3660 modules ship with similar glass — but it is now an
  assumption about a part we have no number for. One photograph through the finished
  aperture retires it. The OV3660 also reaches **QXGA 2048×1536**, a step above the UXGA
  the selftest uses and available in the UI.
- **Which way is up.** The sensor's orientation has not been checked against how the mask
  hangs. `vflip`/`hmirror` are one line in `capture_begin()` once the thing is mounted.
- **The "no clock" naming branch has never actually run.** Every reset available here keeps
  the RTC alive, so the first clip of each boot still gets a real timestamp. A cold start
  from dead battery should produce `…_noclock.avi`; that path is reasoned, not observed.
- **`paused_for_space` is untested.** It only fires if ring mode is on and housekeeping
  still cannot free room — a card full of something that is not clips. The resume path is
  written and not exercised.
- **Nothing has run on battery yet.** Streaming keeps the draw well above the DWEII boost's
  load-current threshold, which is the good case; what has not been tested is what happens
  to the queue and the card when the supply sags. Modem sleep is now off, which costs a
  few tens of milliamps at idle — worth revisiting if battery life disappoints, but not by
  simply turning it back on.
- **Signal.** −76 dBm on the bench already halves what the stream can carry. Where the mask
  actually hangs is now a networking question as well as a decorative one.
- **Heat.** 56 °C on the bench, in free air, on a desk. The bay is sealed apart from the
  cover's vent slots and the mask hangs vertically. The health page shows the die
  temperature; watch it once the cover is on.
