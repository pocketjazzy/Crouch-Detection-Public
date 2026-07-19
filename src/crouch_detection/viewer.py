"""Viewer: skeleton overlay + crouch state machine + settings menu.

Usage:
    python -m crouch_detection.viewer [camera_index]

Camera index defaults to config. Keys:
    m    settings menu (arrows navigate, Left/Right or Enter change)
    n    calibrate a new player (stand countdown, then crouch countdown)
    c    toggle camera feed behind the wireframe
    F8   arm/disarm the key output (GLOBAL - works while the game has focus)
    ESC  close menu / cancel calibration / quit (q also quits)

The output starts DISARMED so setup can't spray keys into other windows;
arm it with F8 once the game is running. The key releases automatically
on tracking loss, during calibration, while the menu is open, on disarm,
and on exit.
"""

import math
import sys
import time
from types import SimpleNamespace

import cv2
import numpy as np

from crouch_detection import calibrate, config, keyout, logic, menu, pose

FONT = cv2.FONT_HERSHEY_SIMPLEX
STATE_COLORS = {
    logic.State.STANDING: (0, 220, 0),
    logic.State.CROUCHED: (0, 165, 255),
    logic.State.NO_PERSON: (0, 0, 255),
}
LEVEL_TICK_PX = 60

OUTPUT_KEY_CHOICES = ["Left_Alt", "Left_Ctrl", "Left_Shift", "Space",
                      "Z", "X", "Mouse_Left", "Mouse_Right", "Mouse_Middle"]
MAX_CAMERA_SCAN = 8   # cycle over indices 0..7, same space as --scan
# Names used before 2026-07-19; map stale configs to the current names.
LEGACY_KEY_NAMES = {
    "alt_l": "Left_Alt", "ctrl_l": "Left_Ctrl", "shift_l": "Left_Shift",
    "space": "Space", "z": "Z", "x": "X", "mouse_left": "Mouse_Left",
    "mouse_right": "Mouse_Right", "mouse_middle": "Mouse_Middle",
}
TRIGGER_CHOICES = ["shoulders", "hips", "auto"]


def apply_exposure(cap, cam_cfg: dict) -> None:
    if cam_cfg.get("auto_exposure", True):
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
    else:
        # Cap the shutter so auto-exposure can't drop the frame rate in
        # dim rooms (log2 seconds on DirectShow: -5 ~= 1/32 s).
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        cap.set(cv2.CAP_PROP_EXPOSURE, cam_cfg.get("exposure", -5))


def open_camera(cam_cfg: dict, index: int) -> cv2.VideoCapture:
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_cfg["width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_cfg["height"])
        cap.set(cv2.CAP_PROP_FPS, cam_cfg["fps"])
        apply_exposure(cap, cam_cfg)
    return cap


def measure(landmarks) -> dict:
    """Both candidate joints' normalized midpoint y (None when not visible)."""
    if not landmarks:
        return {"shoulders": None, "hips": None}
    return {
        "shoulders": pose.midpoint_y(landmarks, pose.LEFT_SHOULDER,
                                     pose.RIGHT_SHOULDER),
        "hips": pose.midpoint_y(landmarks, pose.LEFT_HIP, pose.RIGHT_HIP),
    }


def pick_joint(measurements: dict, trigger: str):
    """(joint_name, normalized_y_or_None) for the configured trigger."""
    if trigger in ("hips", "shoulders"):
        return trigger, measurements[trigger]
    # auto: hips when visible (classic signal), else shoulders (always in
    # frame even close to the camera).
    if measurements["hips"] is not None:
        return "hips", measurements["hips"]
    return "shoulders", measurements["shoulders"]


def draw_skeleton(frame, landmarks) -> None:
    h, w = frame.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h), lm.visibility) for lm in landmarks]
    for a, b in pose.CONNECTIONS:
        if pts[a][2] > pose.VISIBILITY_MIN and pts[b][2] > pose.VISIBILITY_MIN:
            cv2.line(frame, pts[a][:2], pts[b][:2], (0, 255, 0), 2)
    for i, (x, y, vis) in enumerate(pts):
        if i not in pose.FACE_LANDMARKS and vis > pose.VISIBILITY_MIN:
            cv2.circle(frame, (x, y), 3, (0, 200, 255), -1)
    draw_head(frame, pts)


def draw_head(frame, pts) -> None:
    """Stylized head: neck line from the shoulder midpoint up to a green
    circle (sized from ear spacing; nose fallback when ears aren't seen)."""
    l_sh, r_sh = pts[pose.LEFT_SHOULDER], pts[pose.RIGHT_SHOULDER]
    if min(l_sh[2], r_sh[2]) <= pose.VISIBILITY_MIN:
        return
    neck_base = ((l_sh[0] + r_sh[0]) // 2, (l_sh[1] + r_sh[1]) // 2)
    l_ear, r_ear = pts[pose.LEFT_EAR], pts[pose.RIGHT_EAR]
    nose = pts[pose.NOSE]
    if min(l_ear[2], r_ear[2]) > pose.VISIBILITY_MIN:
        cx = (l_ear[0] + r_ear[0]) // 2
        cy = (l_ear[1] + r_ear[1]) // 2
        radius = int(0.6 * math.hypot(l_ear[0] - r_ear[0],
                                      l_ear[1] - r_ear[1]))
    elif nose[2] > pose.VISIBILITY_MIN:
        radius = int(0.2 * math.hypot(l_sh[0] - r_sh[0], l_sh[1] - r_sh[1]))
        cx, cy = nose[0], nose[1] - radius // 4
    else:
        return
    radius = max(radius, 6)
    cv2.circle(frame, (cx, cy), radius, (0, 255, 0), 2)
    cv2.line(frame, neck_base, (cx, cy + radius), (0, 255, 0), 2)


def draw_level(frame, y_norm: float, color, label: str,
               thickness: int = 1) -> None:
    """Short tick at each side of the window instead of a full-width line."""
    h, w = frame.shape[:2]
    y = int(y_norm * h)
    cv2.line(frame, (0, y), (LEVEL_TICK_PX, y), color, thickness)
    cv2.line(frame, (w - LEVEL_TICK_PX, y), (w, y), color, thickness)
    (tw, _), _ = cv2.getTextSize(label, FONT, 0.55, 2)
    cv2.putText(frame, label, (w - tw - 4, max(y - 6, 16)),
                FONT, 0.55, color, 2)


def draw_centered(frame, text: str, y: int, scale: float, color,
                  thickness: int = 2) -> None:
    (tw, _), _ = cv2.getTextSize(text, FONT, scale, thickness)
    cv2.putText(frame, text, ((frame.shape[1] - tw) // 2, y),
                FONT, scale, color, thickness)


def draw_hotkeys(frame, arm_name: str) -> None:
    """Hotkey legend, right-aligned in the top-right corner."""
    lines = ["M = menu", "N = calibrate", "C = camera view",
             f"{arm_name} = arm/disarm"]
    w = frame.shape[1]
    for i, text in enumerate(lines):
        (tw, _), _ = cv2.getTextSize(text, FONT, 0.45, 1)
        cv2.putText(frame, text, (w - tw - 6, 20 + i * 18),
                    FONT, 0.45, (150, 150, 150), 1)


def _cycle(choices, current, direction):
    try:
        i = choices.index(current)
    except ValueError:
        i = -1
    return choices[(i + direction) % len(choices)]


def build_menu(cfg: dict, state: SimpleNamespace) -> menu.SettingsMenu:
    cam_cfg = cfg["camera"]
    out_cfg = cfg.setdefault("output", {})
    det_cfg = cfg["detection"]

    def persist(section: str, key: str, value) -> None:
        config.update_local({section: {key: value}})

    def auto_exposure_value() -> str:
        if cam_cfg.get("auto_exposure", True):
            return "ON (adaptive)"
        return f"OFF (shutter locked {cam_cfg.get('exposure', -5)})"

    def auto_exposure_change(_direction) -> None:
        cam_cfg["auto_exposure"] = not cam_cfg.get("auto_exposure", True)
        apply_exposure(state.cap, cam_cfg)
        persist("camera", "auto_exposure", cam_cfg["auto_exposure"])

    def camera_value() -> str:
        return f"index {state.cam_index}"

    def camera_change(direction) -> None:
        """Cycle to the next camera index that actually delivers frames;
        the live preview shows which device it is."""
        old = state.cam_index
        state.cap.release()
        for step in range(1, MAX_CAMERA_SCAN):
            idx = (old + direction * step) % MAX_CAMERA_SCAN
            cap = open_camera(cam_cfg, idx)
            if cap.isOpened() and cap.read()[0]:
                state.cap = cap
                state.cam_index = idx
                cam_cfg["index"] = idx
                persist("camera", "index", idx)
                return
            cap.release()
        state.cap = open_camera(cam_cfg, old)   # only this one works

    def key_value() -> str:
        raw = out_cfg.get("key", "Left_Alt")
        return LEGACY_KEY_NAMES.get(raw, raw)

    def key_change(direction) -> None:
        state.output.release()
        out_cfg["key"] = _cycle(OUTPUT_KEY_CHOICES, key_value(), direction)
        state.output = keyout.Output(out_cfg["key"])
        persist("output", "key", out_cfg["key"])

    def press_when_value() -> str:
        if out_cfg.get("press_when", "standing") == "standing":
            return "STANDING (Time Crisis)"
        return "CROUCHED (normal games)"

    def press_when_change(_direction) -> None:
        now = out_cfg.get("press_when", "standing")
        out_cfg["press_when"] = "crouched" if now == "standing" else "standing"
        persist("output", "press_when", out_cfg["press_when"])

    def trigger_value() -> str:
        return state.trigger

    def trigger_change(direction) -> None:
        state.trigger = _cycle(TRIGGER_CHOICES, state.trigger, direction)
        det_cfg["trigger_joint"] = state.trigger
        persist("detection", "trigger_joint", state.trigger)

    def mirror_change(_direction) -> None:
        state.mirror = not state.mirror
        persist("ui", "mirror", state.mirror)

    def show_camera_change(_direction) -> None:
        state.show_camera = not state.show_camera
        persist("ui", "show_camera", state.show_camera)

    return menu.SettingsMenu([
        menu.MenuItem("Camera", camera_value, camera_change),
        menu.MenuItem("Auto exposure", auto_exposure_value,
                      auto_exposure_change),
        menu.MenuItem("Hold key/button", key_value, key_change),
        menu.MenuItem("Hold while", press_when_value, press_when_change),
        menu.MenuItem("Trigger joint", trigger_value, trigger_change),
        menu.MenuItem("Mirror preview", lambda: "ON" if state.mirror
                      else "OFF", mirror_change),
        menu.MenuItem("Show camera feed", lambda: "ON" if state.show_camera
                      else "OFF", show_camera_change),
    ])


def main() -> int:
    cfg = config.load()
    index = int(sys.argv[1]) if len(sys.argv) > 1 else cfg["camera"]["index"]
    det_cfg = cfg["detection"]

    cap = open_camera(cfg["camera"], index)
    if not cap.isOpened():
        print(f"Could not open camera index {index}. "
              f"Find one with: python -m crouch_detection.smoke_test --scan")
        return 1

    out_cfg = cfg.setdefault("output", {})
    key_name = LEGACY_KEY_NAMES.get(out_cfg.get("key", "Left_Alt"),
                                    out_cfg.get("key", "Left_Alt"))
    state = SimpleNamespace(
        cap=cap,
        cam_index=index,
        mirror=cfg.get("ui", {}).get("mirror", True),
        show_camera=cfg.get("ui", {}).get("show_camera", False),
        trigger=det_cfg.get("trigger_joint", "shoulders"),
        output=keyout.Output(key_name),
        armed=False,
    )
    settings = build_menu(cfg, state)
    arm_name = out_cfg.get("arm_hotkey", "f8").upper()
    arm_hotkey = keyout.GlobalHotkey(keyout.hotkey_vk(arm_name))
    tracker = pose.PoseTracker()
    detector = logic.CrouchDetector(det_cfg)
    calibrator = calibrate.Calibrator()
    status_msg = ""
    status_until = 0.0
    complete_until = 0.0
    fps = 0.0
    prev = time.perf_counter()
    t0 = prev
    while True:
        ok, frame = state.cap.read()
        if not ok:
            print("Frame grab failed; camera unplugged or in use elsewhere?")
            return 1
        if state.mirror:
            frame = cv2.flip(frame, 1)

        now = time.perf_counter()
        landmarks = tracker.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                                    int((now - t0) * 1000))
        measurements = measure(landmarks)
        joint, raw_y = pick_joint(measurements, state.trigger)
        state_now = detector.update(joint if raw_y is not None else None,
                                    raw_y, now)

        calibrator.update(measurements, now)
        if calibrator.result:
            for cal_joint, thresholds in calibrator.result.items():
                det_cfg.setdefault(cal_joint, {}).update(thresholds)
            config.update_local({"detection": calibrator.result})
            sa = calibrator.result["shoulders"]["stand_above"]
            cb = calibrator.result["shoulders"]["crouch_below"]
            joints = " + ".join(calibrator.result)
            status_msg = (f"{joints}: stand above {sa:.2f}, "
                          f"crouch below {cb:.2f} - saved to local.toml")
            status_until = now + 6.0
            complete_until = now + 4.0
            calibrator.result = None
        elif calibrator.error:
            status_msg = calibrator.error
            status_until = now + 5.0
            calibrator.error = None

        # Key output: hold while in the configured state, armed, and not
        # mid-calibration/menu. Everything else releases (fail-safe).
        if arm_hotkey.poll():
            state.armed = not state.armed
            if not state.armed:
                state.output.release()
        target = (logic.State.STANDING
                  if out_cfg.get("press_when", "standing") == "standing"
                  else logic.State.CROUCHED)
        state.output.set(state.armed and not calibrator.active
                         and not settings.open and state_now == target)

        fps = 0.9 * fps + 0.1 / max(now - prev, 1e-6)
        prev = now

        # Detection ran on the real frame; draw on it or on a black canvas.
        if not state.show_camera:
            frame = np.zeros_like(frame)
        if landmarks:
            draw_skeleton(frame, landmarks)

        # Threshold lines for the joint actually driving the decision.
        shown_joint = detector.active_joint or (
            "hips" if state.trigger == "hips" else "shoulders")
        crouch_below, stand_above = detector.thresholds(shown_joint)
        draw_level(frame, crouch_below, (0, 0, 255),
                   f"crouch below {crouch_below:.2f}")
        draw_level(frame, stand_above, (0, 220, 0),
                   f"stand above {stand_above:.2f}")

        # The smoothed signal the state machine sees.
        if detector.filtered_y is not None:
            draw_level(frame, detector.filtered_y, (255, 200, 0),
                       f"{shown_joint} {detector.filtered_y:.3f}",
                       thickness=3)

        if calibrator.active:
            draw_centered(frame, calibrator.message, 46, 0.8, calibrator.color)
            if calibrator.countdown is not None:
                draw_centered(frame, str(calibrator.countdown),
                              frame.shape[0] // 2, 5.0, calibrator.color, 6)
        elif now < complete_until:
            draw_centered(frame, "CALIBRATION COMPLETE!", 46, 1.0,
                          (0, 255, 255), 3)
        else:
            draw_centered(frame, state_now.value, 46, 1.2,
                          STATE_COLORS[state_now], 3)

        if now < status_until:
            draw_centered(frame, status_msg, frame.shape[0] - 16, 0.6,
                          (255, 255, 0))

        cv2.putText(frame, f"{fps:5.1f} fps", (10, 30),
                    FONT, 0.8, (0, 255, 0), 2)
        draw_hotkeys(frame, arm_name)
        if state.armed:
            held = state.output.down
            cv2.putText(frame,
                        f"{state.output.name}: {'HELD' if held else 'up'}"
                        f"  [{arm_name} disarms]",
                        (10, 56), FONT, 0.6,
                        (0, 220, 0) if held else (0, 200, 255), 2)
        else:
            cv2.putText(frame, f"OUTPUT OFF - {arm_name} arms",
                        (10, 56), FONT, 0.6, (140, 140, 140), 2)
        settings.draw(frame)
        cv2.imshow("Crouch-Detection", frame)

        key = cv2.waitKeyEx(1)
        if settings.handle_key(key):
            continue
        if key == menu.KEY_ESC:
            if calibrator.active:
                calibrator.cancel()
                status_msg = "Calibration cancelled"
                status_until = now + 3.0
            else:
                break
        elif key == ord("q"):
            break
        elif key == ord("m"):
            settings.open = True
        elif key == ord("n"):
            calibrator.start(now)
        elif key == ord("c"):
            state.show_camera = not state.show_camera

    state.output.release()
    tracker.close()
    state.cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
