# Crouch-Detection

Play Time Crisis by actually crouching.

The app watches you through a webcam. While you are standing, it holds a
key down (Left Alt by default). When you crouch, it lets go of the key.
In Time Crisis, Left Alt is the pedal — so standing up in real life makes
your character stand up and shoot, and ducking behind your real furniture
makes your character duck behind cover.

You see yourself as a green stick figure on a black screen, with a big
STANDING or CROUCHED label so you always know what the app thinks you're
doing.

## Setting it up

**Easiest way (no install):** download the zip from the Releases page,
unzip it anywhere, and run `CrouchDetection.exe`.

**From source** (needs Python 3.9–3.12):

```powershell
cd Crouch-Detection
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m crouch_detection.viewer
```

## First time you use it

1. Place the webcam where it can see your upper body in your play spot.
2. Press `n` and follow the countdowns: stand still, then crouch and
   hold. Takes about 13 seconds, and teaches the app YOUR standing and
   crouching heights. Each player should do this once.
3. If the picture gets choppy in a dark room, press `M` and turn
   **Auto exposure** off.
4. Start your game. For MAME, add this to how you launch it (without it,
   MAME ignores the app's key presses):

   ```
   -keyboardprovider dinput -lowlatency
   ```

5. Press `F8` to switch the key output on. Play!

## Keys

| Key | What it does |
|---|---|
| `F8` | Turns the key output on/off. Works even while the game has focus. |
| `n` | Calibrate a new player (stand + crouch countdowns). |
| `M` | Opens the settings menu. |
| `c` | Shows/hides the real camera picture behind the stick figure. |
| `ESC` / `q` | Close the menu / cancel calibration / quit. |

## The settings menu (press M)

Arrow keys pick a row; Left/Right or Enter changes it. Everything saves
automatically.

- **Camera** — have more than one camera? Cycle until you see the right
  one.
- **Auto exposure** — ON adapts to the room but can get choppy in the
  dark. OFF keeps the picture smooth in dim light.
- **Hold key/button** — which key (or mouse button) gets held. Left_Alt
  is for Time Crisis.
- **Hold while** — STANDING is for Time Crisis (its pedal works
  backwards). Pick CROUCHED for normal games where a key makes you
  crouch.
- **Trigger joint** — which part of your body makes the call. Shoulders
  (default) works even when you're close to the camera.
- **Mirror preview** — flips the picture so it behaves like a mirror.
- **Show camera feed** — same as pressing `c`.

## Good to know

- If the app loses sight of you, it releases the key. In Time Crisis
  that means your character ducks to safety.
- Any ordinary USB webcam works. Plug it into the computer directly,
  not into a hub, if you can.
- To build the exe yourself: `.\build_exe.ps1` — the finished app lands
  in `dist\CrouchDetection\`.
