"""Guided two-pose player calibration.

Flow (started by a hotkey in the viewer): a 5s countdown lets the player
take their spot, a short capture samples the STANDING pose, a 3s countdown
cues the crouch, a capture samples the CROUCHED pose, then per-joint
hysteresis thresholds are derived from the player's measured gap:

    stand_above  = stand + STAND_FRACTION  * (crouch - stand)
    crouch_below = stand + CROUCH_FRACTION * (crouch - stand)

Both poses are measured rather than guessed from body proportions, so any
player height works without tuned constants.
"""

import statistics

# Band placed near mid-gap: triggers early in the motion both ways while
# keeping ~10% of the player's gap as hysteresis against flapping.
STAND_FRACTION = 0.45
CROUCH_FRACTION = 0.55
MIN_GAP = 0.08        # normalized y; smaller means the crouch wasn't real
MIN_SAMPLES = 10

STAND_COUNTDOWN_S = 5.0
CROUCH_COUNTDOWN_S = 5.0
CAPTURE_S = 1.5

WHITE = (255, 255, 255)
RED = (0, 0, 255)

# (phase, duration, on-screen message, message color BGR)
_PHASES = [
    ("countdown_stand", STAND_COUNTDOWN_S,
     "NEW PLAYER CALIBRATION - STAND STILL", WHITE),
    ("capture_stand", CAPTURE_S, "HOLD POSITION", WHITE),
    ("countdown_crouch", CROUCH_COUNTDOWN_S, "NOW CROUCH!", RED),
    ("capture_crouch", CAPTURE_S, "HOLD POSITION", WHITE),
]


class Calibrator:
    """State machine driven by the viewer: feed per-frame joint measurements
    via update(); when it deactivates, exactly one of .result / .error is set.

    .result maps joint name -> {"crouch_below": .., "stand_above": ..} for
    every joint that was reliably visible in BOTH poses (shoulders required,
    hips included when available).
    """

    def __init__(self) -> None:
        self.active = False
        self.phase = None
        self.message = ""
        self.color = WHITE
        self.countdown = None   # int seconds remaining during countdowns
        self.result = None
        self.error = None
        self._phase_index = 0
        self._phase_end = 0.0
        self._samples = {}

    def start(self, now: float) -> None:
        self.active = True
        self.result = None
        self.error = None
        self._samples = {"stand": {"shoulders": [], "hips": []},
                         "crouch": {"shoulders": [], "hips": []}}
        self._phase_index = -1
        self._advance(now)

    def cancel(self) -> None:
        self.active = False
        self.phase = None
        self.countdown = None

    def update(self, measurements: dict, now: float) -> None:
        """measurements: joint name -> normalized y or None for this frame."""
        if not self.active:
            return
        if now >= self._phase_end:
            self._advance(now)
            if not self.active:
                return

        remaining = self._phase_end - now
        self.countdown = (int(remaining) + 1
                          if self.phase.startswith("countdown") else None)
        if self.phase == "capture_stand":
            self._sample("stand", measurements)
        elif self.phase == "capture_crouch":
            self._sample("crouch", measurements)

    def _advance(self, now: float) -> None:
        self._phase_index += 1
        if self._phase_index >= len(_PHASES):
            self._finish()
            return
        self.phase, duration, self.message, self.color = \
            _PHASES[self._phase_index]
        self._phase_end = now + duration

    def _sample(self, pose_name: str, measurements: dict) -> None:
        for joint, y in measurements.items():
            if y is not None:
                self._samples[pose_name][joint].append(y)

    def _finish(self) -> None:
        self.cancel()
        result = {}
        for joint in ("shoulders", "hips"):
            stand = self._samples["stand"][joint]
            crouch = self._samples["crouch"][joint]
            if len(stand) < MIN_SAMPLES or len(crouch) < MIN_SAMPLES:
                continue
            stand_y = statistics.median(stand)
            crouch_y = statistics.median(crouch)
            gap = crouch_y - stand_y
            if gap < MIN_GAP:
                continue
            result[joint] = {
                "stand_above": round(stand_y + STAND_FRACTION * gap, 3),
                "crouch_below": round(stand_y + CROUCH_FRACTION * gap, 3),
            }
        if "shoulders" in result:
            self.result = result
        else:
            self.error = ("Calibration failed: shoulders not visible or "
                          "crouch too shallow - press n to retry")
