"""Measure what the camera + pose pipeline can actually sustain.

Usage:
    python -m crouch_detection.fps_probe [camera_index]

Answers whether raising [camera] fps in the config is worth anything:
first capture-only fps at several requested rates, then the full
capture + inference loop the viewer runs. Close the viewer first (only
one app can hold the camera), and run in your normal play lighting -
dim rooms force long exposures that cap fps regardless of settings.
"""

import sys
import time

import cv2

from crouch_detection import config

WARMUP_FRAMES = 15


def _open(index: int, width: int, height: int, fps: int):
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    for _ in range(WARMUP_FRAMES):
        cap.read()
    return cap


def measure_capture(index: int, fps_req: int, width=640, height=480, n=90):
    cap = _open(index, width, height, fps_req)
    if cap is None:
        print("  camera busy/unavailable - is the viewer still open?")
        return
    t0 = time.perf_counter()
    got = sum(1 for _ in range(n) if cap.read()[0])
    dt = time.perf_counter() - t0
    reported = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    print(f"  {width}x{height} requested {fps_req} fps: driver reports "
          f"{reported:.0f}, measured {got / dt:.1f}")


def measure_exposure(index: int, n=60):
    """Manual-exposure caps: can we stop dim light from dropping the fps?"""
    for exp in (-5, -6, -7):
        cap = _open(index, 640, 480, 30)
        if cap is None:
            print("  camera busy/unavailable")
            return
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)   # manual mode
        # exp is log2 seconds (DirectShow-native); V4L2 wants 100us units.
        cap.set(cv2.CAP_PROP_EXPOSURE,
                exp if sys.platform == "win32"
                else max(1, round((2.0 ** exp) * 10000)))
        for _ in range(WARMUP_FRAMES):
            cap.read()
        brightness = []
        t0 = time.perf_counter()
        for _ in range(n):
            ok, frame = cap.read()
            if ok:
                brightness.append(float(frame.mean()))
        dt = time.perf_counter() - t0
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)   # hand control back to auto
        cap.release()
        if not brightness:
            print(f"  exposure {exp}: no frames delivered")
            continue
        shutter_ms = 1000 * (2 ** exp)
        print(f"  exposure {exp} (~{shutter_ms:.0f} ms shutter): measured "
              f"{len(brightness) / dt:.1f} fps, mean brightness "
              f"{sum(brightness) / len(brightness):.0f}/255")


def measure_pipeline(index: int, n=90):
    """Full loop: capture + BGR->RGB + MediaPipe pose, like the viewer."""
    from crouch_detection import pose
    cap = _open(index, 640, 480, 60)
    if cap is None:
        print("  camera busy/unavailable")
        return
    tracker = pose.PoseTracker()
    infer_ms = []
    t0 = time.perf_counter()
    done = 0
    for _ in range(n):
        ok, frame = cap.read()
        if not ok:
            continue
        t1 = time.perf_counter()
        tracker.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                        int((t1 - t0) * 1000) + 1)
        infer_ms.append((time.perf_counter() - t1) * 1000)
        done += 1
    dt = time.perf_counter() - t0
    tracker.close()
    cap.release()
    infer_ms.sort()
    print(f"  end-to-end {done / dt:.1f} fps; pose inference median "
          f"{infer_ms[len(infer_ms) // 2]:.1f} ms, p90 "
          f"{infer_ms[int(len(infer_ms) * 0.9)]:.1f} ms")


def main() -> int:
    cfg = config.load()
    index = int(sys.argv[1]) if len(sys.argv) > 1 else cfg["camera"]["index"]
    print(f"Probing camera {index} (this takes ~20s)...")
    print("capture only:")
    measure_capture(index, 30)
    measure_capture(index, 60)
    measure_capture(index, 60, 320, 240)
    print("manual exposure caps (fps vs brightness trade):")
    measure_exposure(index)
    print("capture + pose inference (requesting 60 fps):")
    measure_pipeline(index)
    print("Reading the exposure rows: pick the LONGEST shutter that still "
          "reaches ~30 fps and set it as 'exposure = <value>' under "
          "[camera] in config/local.toml. Brightness down to ~50/255 "
          "usually still tracks fine - verify in the viewer (press c to "
          "see the camera feed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
