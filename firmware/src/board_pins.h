// board_pins.h — the nulllab / emakefun ESP32-S3-CAM pin map, in one place.
//
// Source: https://github.com/nulllaborg/esp32s3-cam (the vendor's own repo for
// this exact board).  Corroborated by the board in hand: 8 MB flash and octal
// PSRAM match what esptool reports, and GPIO3 as the flashlight matches the
// LEDs the README's cover section says leak through the vents.
//
// Nothing here is guessed.  If a pin ever has to change, change it HERE — the
// bring-up self-test reads these same symbols, so a wrong pin shows up as a
// failed capture rather than as a silently dark image.
#pragma once

// --- camera (DVP, 8-bit) ---------------------------------------------------
#define CAM_PIN_PWDN   -1   // not brought out on this board
#define CAM_PIN_RESET  -1   // ditto: sensor resets from XCLK
#define CAM_PIN_XCLK   15
#define CAM_PIN_SIOD    4   // SCCB data  (I2C-ish)
#define CAM_PIN_SIOC    5   // SCCB clock

#define CAM_PIN_D7     16
#define CAM_PIN_D6     17
#define CAM_PIN_D5     18
#define CAM_PIN_D4     12
#define CAM_PIN_D3     10
#define CAM_PIN_D2      8
#define CAM_PIN_D1      9
#define CAM_PIN_D0     11

#define CAM_PIN_VSYNC   6
#define CAM_PIN_HREF    7
#define CAM_PIN_PCLK   13

// --- microSD, SD_MMC 1-bit mode -------------------------------------------
// Only CMD/CLK/DAT0 are wired, so 1-bit is not a fallback here, it is the
// only mode.  SD_MMC.begin(..., mode1bit=true).
#define SD_PIN_CMD     38
#define SD_PIN_CLK     39
#define SD_PIN_D0      40

// --- on-board LEDs ---------------------------------------------------------
// GPIO3 drives the white flashlight LEDs.  Inside a sealed mask these are
// pure liability: the README's cover section notes they leak out through the
// vent slots.  Firmware drives this LOW and leaves it there.
#define PIN_FLASH_LED   3
