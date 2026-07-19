"""Crouch decision logic: One-Euro smoothing + hysteresis + debounce.

Coordinate convention: normalized y, 0.0 = top of frame, 1.0 = bottom.
"Sinking below the crouch line" therefore means y INCREASING past
crouch_below; "rising above the stand line" means y decreasing past
stand_above. crouch_below > stand_above, and the gap between them is the
hysteresis band that stops flicker when hovering at the threshold.
"""

import math
from enum import Enum


class OneEuroFilter:
    """Adaptive low-pass: smooth when still, low-lag when moving fast."""

    def __init__(self, min_cutoff: float = 2.0, beta: float = 0.6,
                 d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self._prev_t = None
        self._prev_x = None
        self._prev_dx = 0.0

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    @property
    def velocity(self) -> float:
        """Filtered derivative of the signal, units/second."""
        return self._prev_dx

    def __call__(self, x: float, t: float) -> float:
        if self._prev_t is None:
            self._prev_t, self._prev_x = t, x
            return x
        dt = max(t - self._prev_t, 1e-6)
        dx = (x - self._prev_x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._prev_dx
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._prev_x
        self._prev_t, self._prev_x, self._prev_dx = t, x_hat, dx_hat
        return x_hat


class State(Enum):
    NO_PERSON = "NO PERSON"
    STANDING = "STANDING"
    CROUCHED = "CROUCHED"


class CrouchDetector:
    """Tracks STANDING / CROUCHED / NO_PERSON from a joint's normalized y.

    Expects the [detection] config table: per-joint threshold sub-tables
    (crouch_below / stand_above), debounce_frames, lost_tracking_ms, and an
    optional [detection.filter] table with One-Euro parameters.
    """

    def __init__(self, det_cfg: dict) -> None:
        self._cfg = det_cfg
        filt = det_cfg.get("filter", {})
        self._filter = OneEuroFilter(filt.get("min_cutoff", 2.0),
                                     filt.get("beta", 0.6))
        self._debounce_frames = det_cfg.get("debounce_frames", 2)
        self._lost_s = det_cfg.get("lost_tracking_ms", 500) / 1000.0
        self._lookahead_s = det_cfg.get("lookahead_ms", 100) / 1000.0
        # Velocity below this (normalized units/s) doesn't count toward the
        # prediction: postural sway is ~0.1/s, a real crouch ~1.0/s. Without
        # it, sway noise while hovering mid-band leaks through the lookahead
        # and flaps the state (23 flips/10s in simulation; 0 with it).
        self._deadband = det_cfg.get("lookahead_deadband", 0.25)
        self.state = State.NO_PERSON
        self.filtered_y = None
        self.decision_y = None
        self.active_joint = None
        self._candidate = None
        self._candidate_count = 0
        self._last_seen = None

    def thresholds(self, joint: str):
        table = self._cfg[joint]
        return table["crouch_below"], table["stand_above"]

    def update(self, joint, y, now: float) -> State:
        """Feed one measurement (joint name + normalized y, or None when the
        joint wasn't visible this frame) at time `now` (seconds)."""
        if y is None:
            lost = (self._last_seen is None
                    or now - self._last_seen > self._lost_s)
            if lost and self.state != State.NO_PERSON:
                self._commit(State.NO_PERSON)
            if lost:
                self._filter.reset()
                self.filtered_y = None
                self.decision_y = None
                self.active_joint = None
            return self.state

        if joint != self.active_joint:
            # Joint switch (auto mode) jumps y discontinuously; don't smear.
            self._filter.reset()
            self.active_joint = joint
        self._last_seen = now
        self.filtered_y = self._filter(y, now)
        # Predictive lookahead: judge thresholds on where the signal will
        # be in lookahead_s, so fast moves fire the transition early. Only
        # velocity beyond the sway deadband counts, so holding still (or
        # hovering mid-band) behaves exactly like no lookahead.
        v = self._filter.velocity
        v_eff = math.copysign(max(0.0, abs(v) - self._deadband), v)
        self.decision_y = self.filtered_y + v_eff * self._lookahead_s

        crouch_below, stand_above = self.thresholds(joint)
        if self.state == State.NO_PERSON:
            # First acquisition inside the hysteresis band counts as CROUCHED
            # (the safe/behind-cover state for Time Crisis).
            candidate = (State.STANDING if self.decision_y <= stand_above
                         else State.CROUCHED)
        elif self.state == State.STANDING and self.decision_y >= crouch_below:
            candidate = State.CROUCHED
        elif self.state == State.CROUCHED and self.decision_y <= stand_above:
            candidate = State.STANDING
        else:
            candidate = self.state

        if candidate == self.state:
            self._candidate = None
            self._candidate_count = 0
        elif candidate == self._candidate:
            self._candidate_count += 1
            if self._candidate_count >= self._debounce_frames:
                self._commit(candidate)
        else:
            self._candidate = candidate
            self._candidate_count = 1
            if self._debounce_frames <= 1:
                self._commit(candidate)
        return self.state

    def _commit(self, state: State) -> None:
        self.state = state
        self._candidate = None
        self._candidate_count = 0
