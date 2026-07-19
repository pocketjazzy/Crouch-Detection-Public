# Crouch-Detection Roadmap

**PROJECT COMPLETE — v1.0 (2026-07-19).** Physical crouch drives Time
Crisis 2 in MAME end-to-end: tracking, per-player calibration, settings
menu, key injection, portable exe. Remaining unchecked items below are
optional future work.

## Milestones

- [x] **M0 — Scaffold** *(2026-07-16)*
  Repo, docs, `pyproject.toml`, package skeleton, camera smoke test
  (`python -m crouch_detection.smoke_test`).

- [x] **M1 — Skeleton view** *(validated 2026-07-16)*
  MediaPipe Pose overlay on the live feed; live readout of hip / shoulder
  normalized heights. The pose model (~6 MB) auto-downloads to `models/` on
  first run. Measured on the iC800 setup: shoulders 0.39–0.40 standing,
  0.65–0.72 crouched; hips leave frame unless ~4–5 ft from the camera.

- [x] **M2 — Crouch state machine** *(validated 2026-07-17)*
  Threshold + hysteresis + One-Euro smoothing + debounce (`logic.py`).
  Threshold lines + smoothed signal drawn on the preview; big STANDING /
  CROUCHED / NO PERSON banner; wireframe-on-black display (`c` toggles the
  camera feed). Validation surfaced the static-threshold problem (a shorter
  player read as always-crouched) → calibration pulled forward from M5.

- [x] **M3 — Key injection (first playable)** *(VALIDATED in TC2/MAME
  2026-07-19)*
  `keyout.py` — SendInput scan codes (keyboard) + mouse events; honors
  the menu's key pick, hold-while polarity, and rebinding live; F8
  arm/disarm via GetAsyncKeyState (global — works while MAME has focus);
  starts DISARMED; releases on tracking loss / calibration / menu /
  disarm / exit; HUD shows OUTPUT state.
  **MAME must run with `-keyboardprovider dinput`** — measured on this
  setup: `rawinput` (default) drops injected input, and `win32`
  unexpectedly did too; `dinput` works.

- [ ] **M4 — Config UI** *(core done 2026-07-18)*
  DONE: in-window settings menu (`M` key, arrow navigation): auto-exposure
  toggle (applies to the camera live), output key/button picker, hold-while
  STANDING/CROUCHED reversal, trigger-joint selector, mirror + camera-feed
  toggles — all persisted to `local.toml` immediately (`menu.py`).
  2026-07-19: Camera menu row cycles indices 0-7, skipping ones that
  deliver no frames (live preview identifies the device); hotkey legend
  drawn top-right (M/N/C/F8). VALIDATED in the portable exe with two
  identical iC800s plugged in — cycled and switched correctly.
  REMAINING: draggable threshold line, per-player profiles, free-form
  key capture.

- [ ] **M5 — Auto-calibration (dynamic body height)** *(core done 2026-07-17)*
  DONE: guided two-pose calibration (`n` key) — 5s countdown + standing
  capture, 3s countdown + crouched capture; thresholds placed at 35% / 60%
  of the player's measured stand→crouch gap (`calibrate.py`); persisted to
  git-ignored `config/local.toml`. Shallow-crouch / no-person captures are
  rejected. REMAINING: named per-player profiles; continuous drift
  re-calibration if needed.

- [x] **M4.5 — Portable Windows build** *(VALIDATED 2026-07-19)*
  `build_exe.ps1`: PyInstaller onedir (`--collect-all mediapipe`);
  frozen-aware paths put `config/` + `models/` next to the exe; zip
  `dist\CrouchDetection` to carry. local.toml deliberately not bundled
  (per-machine calibration), so first run on each install: `M` → auto
  exposure off (if dim room), `n` → calibrate. The runnable app is in
  `dist\`, NOT `build\` (PyInstaller scratch).

- [ ] **M6 — Linux / Steam Deck**
  `uinput` virtual-keyboard backend, udev permissions, packaging
  (PyInstaller / Flatpak).

## Parking lot

- **Player lock-on for busy rooms** — `num_poses` is 1: MediaPipe tracks the
  most prominent person and is sticky frame-to-frame, but re-acquisition
  after occlusion can grab a bystander. Fix idea: track N poses, pick by
  largest shoulder width + proximity to last player position. Status: OPEN.

- **Gamepad emulation** instead of keyboard (ViGEm / uinput gamepad) — useful
  beyond MAME. Status: OPEN.
- **Two-player** — TC2 link-play runs one player per PC, so one app instance
  per PC already covers it; a single-PC two-player mode (two cameras, two
  keys) is unexplored. Status: OPEN.
- **License** — repo currently has none (all rights reserved by default).
  Decide before publicizing. Status: OPEN.

## Design decisions

- **Stack: Python + MediaPipe + OpenCV** — one codebase for Windows and Steam
  Deck (x86_64), robust CPU pose tracking, fastest path to playable. Chosen
  over C#/.NET (Steam Deck port would be a rewrite) and Rust (immature pose /
  UI ecosystem). *(2026-07-16)*
- **Trigger joint default: shoulders** *(changed 2026-07-16)* — hips leave
  the frame unless the player stands ~4–5 ft back, too far to see the screen
  comfortably; shoulders stay visible standing or crouched at close range.
  Hips remain configurable, plus an `auto` mode (hips when visible, else
  shoulders) with per-joint threshold pairs.
- **Fail-safe default: release key** — in Time Crisis, released pedal =
  crouched behind cover = safe.
