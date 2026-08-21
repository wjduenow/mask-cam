#!/usr/bin/env python3
"""Talk to the mask-cam board without a TTY.

`pio device monitor` wants a real terminal and dies with "Inappropriate ioctl
for device" when it does not get one, which makes it useless from a script or
an agent session.  These two subcommands cover what that monitor was for:

    python tools/board.py log            reset the board, print what it says
    python tools/board.py frame out.jpg  ask for a frame, decode it, save it
    python tools/board.py clip out.avi   pull the newest recording off the card

`frame` is the one that matters.  Every check in the self-test MEASURES a
frame -- length, dimensions, JPEG markers -- and a lens still wearing its
protective film passes all of them.  Only looking at the picture tells you the
camera can see.

Run with PlatformIO's interpreter, which already has pyserial:

    ~/.platformio/penv/bin/python firmware/tools/board.py frame /tmp/f.jpg
"""

import argparse
import base64
import sys
import time

import serial  # from PlatformIO's venv

PORT = "/dev/ttyACM0"  # the S3's own USB (303a:1001), not a bridge chip
BAUD = 115200          # ignored by native USB CDC, but pyserial wants a number


def open_port(port, reset):
    s = serial.Serial(port, BAUD, timeout=0.5)
    if reset:
        # RTS asserted pulls EN low on the USB-serial-JTAG peripheral. This is
        # the same hard reset esptool performs, minus the DTR dance that would
        # drop the chip into the download stub.
        s.setDTR(False)
        s.setRTS(True)
        time.sleep(0.2)
        s.setRTS(False)
        time.sleep(0.05)
    # DTR high tells the firmware a host is attached, which is what its
    # `while (!Serial)` in setup() is waiting on.
    s.setDTR(True)
    time.sleep(0.2)
    s.reset_input_buffer()
    return s


def cmd_log(args):
    s = open_port(args.port, reset=not args.no_reset)
    t0 = time.time()
    while time.time() - t0 < args.seconds:
        d = s.read(4096)
        if d:
            sys.stdout.write(d.decode("utf-8", "replace"))
            sys.stdout.flush()
    s.close()
    return 0


def _collect(s, end_marker, abort_marker, timeout):
    """Read until the device says it is done. Returns (text, aborted)."""
    buf, t0 = b"", time.time()
    while time.time() - t0 < timeout:
        d = s.read(65536)
        if d:
            buf += d
            t0 = time.time()          # idle timeout, not a total deadline:
                                      # a 14 MB clip takes longer than 30 s
        if end_marker in buf or abort_marker in buf:
            break
    txt = buf.decode("utf-8", "replace")
    return txt, abort_marker.decode() in txt


def cmd_clip(args):
    s = open_port(args.port, reset=False)
    s.write(b"d")
    txt, aborted = _collect(s, b"---END FILE---", b"---ABORTED FILE---", args.timeout)
    s.close()

    i = txt.find("---BEGIN FILE")
    j = max(txt.find("---END FILE---"), txt.find("---ABORTED FILE---"))
    if i < 0 or j < 0:
        print("no file markers in the reply. Is a clip on the card? ('l' to list)")
        print("last 500 bytes:\n" + txt[-500:])
        return 1

    header = txt[i:txt.find("\n", i)]
    declared = int(header.split()[-1].rstrip("-"))
    data = base64.b64decode("".join(txt[txt.find("\n", i) + 1:j].split()))
    with open(args.out, "wb") as f:
        f.write(data)

    print(header)
    print("%d bytes -> %s" % (len(data), args.out))

    # The device announces the size it is about to send. Check it. USB CDC
    # drops bytes when the host cannot keep up, and a clip that is 16 kB short
    # in the middle still opens, still plays, and is quietly wrong.
    if aborted:
        print("DUMP ABORTED by the board -- the host stopped reading")
        return 1
    if len(data) != declared:
        print("SIZE MISMATCH: declared %d, got %d (%+d)"
              % (declared, len(data), len(data) - declared))
        return 1
    print("size matches the card. Play it, or: ffprobe %s" % args.out)
    return 0


def cmd_frame(args):
    # No reset by default: resetting restarts the self-test and the sensor then
    # needs to find its exposure all over again. Talk to the running firmware.
    s = open_port(args.port, reset=args.reset)

    # Auto-exposure needs a few frames to settle, or you photograph the
    # sensor's first guess rather than the room.
    time.sleep(args.settle)
    s.reset_input_buffer()

    s.write(b"p")
    buf, t0 = b"", time.time()
    while time.time() - t0 < args.timeout:
        d = s.read(8192)
        if d:
            buf += d
        if b"---END JPEG---" in buf:
            break
    s.close()

    txt = buf.decode("utf-8", "replace")
    i, j = txt.find("---BEGIN JPEG"), txt.find("---END JPEG---")
    if i < 0 or j < 0:
        print("no frame markers in the reply. Is the self-test firmware running?")
        print("last 500 bytes:\n" + txt[-500:])
        return 1

    header = txt[i:txt.find("\n", i)]
    img = base64.b64decode("".join(txt[txt.find("\n", i) + 1:j].split()))
    with open(args.out, "wb") as f:
        f.write(img)

    # A JPEG that does not end in EOI was truncated in transit; say so rather
    # than leaving a half file that some viewers will happily show.
    ok = img[:2] == b"\xff\xd8" and img[-2:] == b"\xff\xd9"
    print(header)
    print("%d bytes -> %s" % (len(img), args.out))
    print("SOI/EOI %s" % ("ok" if ok else "TRUNCATED -- raise --timeout"))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", default=PORT)
    sub = p.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("log", help="reset the board and print its output")
    lg.add_argument("seconds", nargs="?", type=float, default=25.0)
    lg.add_argument("--no-reset", action="store_true",
                    help="attach to the running firmware instead of restarting it")
    lg.set_defaults(func=cmd_log)

    fr = sub.add_parser("frame", help="capture a frame and save it")
    fr.add_argument("out")
    fr.add_argument("--reset", action="store_true")
    fr.add_argument("--settle", type=float, default=2.0,
                    help="seconds to let auto-exposure settle first")
    fr.add_argument("--timeout", type=float, default=30.0)
    fr.set_defaults(func=cmd_frame)

    cl = sub.add_parser("clip", help="pull the newest recording off the card")
    cl.add_argument("out")
    cl.add_argument("--timeout", type=float, default=20.0,
                    help="seconds of SILENCE before giving up, not a total deadline")
    cl.set_defaults(func=cmd_clip)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
