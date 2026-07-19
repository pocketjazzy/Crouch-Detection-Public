# Build a portable Windows folder for Crouch-Detection (PyInstaller onedir).
# Run from the repo root, inside the same Python env that runs the viewer:
#   .\build_exe.ps1
# Output: dist\CrouchDetection\CrouchDetection.exe
# Portable: zip the dist\CrouchDetection folder and carry it anywhere -
# no Python needed on the target machine.

$ErrorActionPreference = "Stop"

# Probe for PyInstaller. PowerShell 5 + ErrorActionPreference Stop turns
# native stderr into a terminating error when redirected, so relax it
# around the probe (an ImportError here is expected, not fatal).
$ErrorActionPreference = "Continue"
python -c "import PyInstaller" 2>&1 | Out-Null
$havePyInstaller = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"

if (-not $havePyInstaller) {
    Write-Host "Installing PyInstaller into this environment..."
    python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
}

# --collect-all mediapipe: bundles its model graphs (.binarypb) and DLLs,
# which plain dependency analysis misses.
python -m PyInstaller --noconfirm --clean --onedir --name CrouchDetection `
    --paths src `
    --collect-all mediapipe `
    src\crouch_detection\main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# Config and pose model live NEXT TO the exe (frozen-aware paths in
# config.py). local.toml is intentionally NOT copied: calibration is
# per-machine, so a fresh install starts clean and calibrates with n.
New-Item -ItemType Directory -Force dist\CrouchDetection\config | Out-Null
Copy-Item config\default.toml dist\CrouchDetection\config\
if (Test-Path models\pose_landmarker_lite.task) {
    New-Item -ItemType Directory -Force dist\CrouchDetection\models | Out-Null
    Copy-Item models\pose_landmarker_lite.task dist\CrouchDetection\models\
    Write-Host "Bundled the pose model (first run needs no internet)."
} else {
    Write-Host "No local pose model found - the exe will download it on first run."
}

Write-Host ""
Write-Host "Done: dist\CrouchDetection\CrouchDetection.exe"
Write-Host "To make it portable: Compress-Archive dist\CrouchDetection CrouchDetection.zip"
