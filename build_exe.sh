#!/usr/bin/env bash
# Build a portable Linux folder (PyInstaller onedir). Run from the repo
# root, inside the venv that runs the viewer:   bash build_exe.sh
# Output: dist/CrouchDetection/CrouchDetection
#
# Glibc note: the result runs on systems with glibc >= the build machine's,
# so build on the OLDEST distro you want to support (Ubuntu 22.04 covers
# most; a Steam Deck build runs fine on the Deck itself).
set -e

python -m pip show pyinstaller >/dev/null 2>&1 || python -m pip install pyinstaller

python -m PyInstaller --noconfirm --clean --onedir --name CrouchDetection \
    --paths src \
    --collect-all mediapipe \
    src/crouch_detection/main.py

# Config and pose model live NEXT TO the binary (frozen-aware paths).
# local.toml is intentionally not copied: calibration is per-machine.
mkdir -p dist/CrouchDetection/config
cp config/default.toml dist/CrouchDetection/config/
if [ -f models/pose_landmarker_lite.task ]; then
    mkdir -p dist/CrouchDetection/models
    cp models/pose_landmarker_lite.task dist/CrouchDetection/models/
    echo "Bundled the pose model (first run needs no internet)."
else
    echo "No local pose model found - it will download on first run."
fi

echo ""
echo "Done: dist/CrouchDetection/CrouchDetection"
echo "Share it with: tar czf CrouchDetection-linux-x64.tar.gz -C dist CrouchDetection"
