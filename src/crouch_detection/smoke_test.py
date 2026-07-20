"""M0 camera smoke test: show the live webcam feed with an FPS counter.

Usage:
    python -m crouch_detection.smoke_test [camera_index]
    python -m crouch_detection.smoke_test --scan

--scan probes indices 0-7 and reports which ones deliver frames (virtual
cameras like EOS Webcam Utility open "successfully" too, so eyeball the
live view to confirm you picked the physical one).

Press ESC or q in the preview window to quit.
"""

import sys
import time

import cv2

# CAP_DSHOW opens much faster than the MSMF default on Windows.
BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


def _quiet_opencv() -> None:
    """Probing camera indices that don't exist is harmless but extremely
    noisy on Linux (V4L2/FFmpeg print warnings per missing device)."""
    try:
        from cv2.utils import logging as cvlog
        cvlog.setLogLevel(cvlog.LOG_LEVEL_SILENT)
    except Exception:
        pass


def scan() -> int:
    _quiet_opencv()
    found = []
    for index in range(8):
        cap = cv2.VideoCapture(index, BACKEND)
        if cap.isOpened() and cap.read()[0]:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"  index {index}: {width}x{height}")
            found.append(index)
        cap.release()
    if not found:
        print("No cameras delivered frames.")
        return 1
    print(f"Working indices: {found} — view one with: "
          f"python -m crouch_detection.smoke_test <index>")
    return 0


def main() -> int:
    if "--scan" in sys.argv[1:]:
        return scan()
    index = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    cap = cv2.VideoCapture(index, BACKEND)
    if not cap.isOpened():
        print(f"Could not open camera index {index}; try 0, 1, 2, ...")
        return 1

    # MJPG @ 640x480x30: low-latency target mode for pose tracking.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera {index} open at {width}x{height}")

    fps = 0.0
    prev = time.perf_counter()
    while True:
        ok, frame = cap.read()
        if not ok:
            print("Frame grab failed; camera unplugged or in use elsewhere?")
            return 1

        now = time.perf_counter()
        fps = 0.9 * fps + 0.1 / max(now - prev, 1e-6)
        prev = now

        cv2.putText(frame, f"{fps:5.1f} fps  (ESC to quit)", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("Crouch-Detection M0 smoke test", frame)

        if cv2.waitKey(1) & 0xFF in (27, ord("q")):
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
