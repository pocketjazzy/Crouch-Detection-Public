"""MediaPipe pose tracking: model auto-download + a thin landmarker wrapper."""

import urllib.request
from pathlib import Path

import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from crouch_detection.config import REPO_ROOT

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task")
MODEL_PATH = REPO_ROOT / "models" / "pose_landmarker_lite.task"

# BlazePose 33-landmark topology indices.
NOSE = 0
LEFT_EAR, RIGHT_EAR = 7, 8
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_HIP, RIGHT_HIP = 23, 24
FACE_LANDMARKS = frozenset(range(11))   # nose, eyes, ears, mouth

# Torso + limbs; face mesh omitted.
CONNECTIONS = [
    (11, 12), (23, 24), (11, 23), (12, 24),                       # torso box
    (11, 13), (13, 15), (12, 14), (14, 16),                       # arms
    (15, 17), (15, 19), (15, 21), (16, 18), (16, 20), (16, 22),   # hands
    (23, 25), (25, 27), (24, 26), (26, 28),                       # legs
    (27, 29), (29, 31), (27, 31), (28, 30), (30, 32), (28, 32),   # feet
]

VISIBILITY_MIN = 0.5


def ensure_model() -> Path:
    if not MODEL_PATH.exists():
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading pose model (~6 MB) to {MODEL_PATH} ...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("Download complete.")
    return MODEL_PATH


class PoseTracker:
    """Video-mode pose landmarker: 33 normalized landmarks for one person."""

    def __init__(self) -> None:
        options = vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(
                model_asset_path=str(ensure_model())),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

    def process(self, frame_rgb, timestamp_ms: int):
        """Returns the landmark list for the tracked person, or None."""
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        return result.pose_landmarks[0] if result.pose_landmarks else None

    def close(self) -> None:
        self._landmarker.close()


def midpoint_y(landmarks, left: int, right: int):
    """Normalized y (0=top, 1=bottom) of a joint pair's midpoint, or None
    if either side is barely visible."""
    a, b = landmarks[left], landmarks[right]
    if min(a.visibility, b.visibility) < VISIBILITY_MIN:
        return None
    return (a.y + b.y) / 2.0
