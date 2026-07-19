# Crouch-Detection

Turn a webcam into a crouch pedal. The app tracks your body with a webcam,
detects when you physically crouch, and holds/releases a keyboard key
accordingly — so light-gun games like **Time Crisis** (via MAME) can be played
standing up, ducking behind real furniture to take cover.

## Why the logic is inverted

In Time Crisis the character is **crouched behind cover by default** and the
pedal (mapped to **Left Alt** in MAME) makes them stand up to shoot. Humans are
standing by default, so this app reverses the mapping:

| You (physical)              | App output          | Game character |
|-----------------------------|---------------------|----------------|
| Standing                    | **holds Left Alt**  | stands, shoots |
| Crouched (below threshold)  | **releases Alt**    | ducks to cover |

Key and polarity are configurable, so other games work too.

## How it works

```
webcam ──> OpenCV capture ──> MediaPipe Pose (33 landmarks)
              │                     │
              │                     v
              │        trigger joint (hips / shoulders / head)
              │                     │
              │            One-Euro smoothing
              │                     │
              │      hysteresis + debounce state machine
              │            STANDING <──> CROUCHED
              │                     │
              v                     v
      preview window        key injection
   (skeleton + threshold   (SendInput scan codes on Windows,
    line + state readout)      uinput on Linux)
```

Safety/comfort details:

- **Hysteresis** — separate crouch-below / stand-above thresholds so hovering
  at the line never machine-guns the key.
- **Fail-safe** — if tracking is lost, the key is released (in Time Crisis,
  crouched = safe behind cover).
- **Arm/disarm hotkey** — configure and test without keystrokes firing into
  whatever window has focus.

## Status

Detection, per-player calibration (`n`), settings menu (`M`), and key
injection (`F8` to arm) are implemented; MAME validation is the current
step. See [ROADMAP.md](ROADMAP.md).

## Quick start (Windows)

Requires Python 3.9–3.12 (MediaPipe does not yet ship 3.13 wheels).

```powershell
cd Crouch-Detection
py -3.11 -m venv .venv          # or: python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .

# M0 smoke test: shows the live camera feed with an FPS counter
python -m crouch_detection.smoke_test        # optional arg: camera index
```

Press `ESC` or `q` to quit the preview window.

## Portable exe (no Python needed)

From the repo root, in the Python environment that runs the viewer:

```powershell
.\build_exe.ps1
```

Output is `dist\CrouchDetection\` — a self-contained folder with
`CrouchDetection.exe`; zip it and run it on any Windows machine, no Python
required. `config\default.toml` and the pose model sit next to the exe
(editable / downloaded once); calibration (`n`) writes `config\local.toml`
there too, so each machine keeps its own thresholds.

## Hardware

Developed against an **Inland iC800 HD** webcam, but any UVC webcam works.
Target capture mode is 640×480 @ 30fps MJPG (low latency beats resolution for
pose tracking).

## MAME integration notes

- **Launch MAME with `-keyboardprovider dinput`.** Validated 2026-07-19 on
  MAME 0.287 / Time Crisis 2: the default `rawinput` provider drops
  injected input (no source device), and `win32` also failed on this
  setup; `dinput` accepts it.
- For less input lag, add `-lowlatency` too (MAME draws the frame after
  polling input instead of before).
- Injection uses **scan codes** (`KEYEVENTF_SCANCODE`), which is what
  DirectInput-era apps actually read. Left Alt = scan code `0x38`.
