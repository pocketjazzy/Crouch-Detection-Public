"""Load config/default.toml, overlaid with config/local.toml if present."""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

if getattr(sys, "frozen", False):
    # PyInstaller build: config/ and models/ sit next to the exe so users
    # can edit/inspect them and the model download persists.
    REPO_ROOT = Path(sys.executable).resolve().parent
else:
    REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load() -> dict:
    with open(CONFIG_DIR / "default.toml", "rb") as f:
        cfg = tomllib.load(f)
    local = CONFIG_DIR / "local.toml"
    if local.exists():
        with open(local, "rb") as f:
            cfg = _deep_merge(cfg, tomllib.load(f))
    return cfg


def update_local(overrides: dict) -> None:
    """Deep-merge overrides into config/local.toml (created if missing)."""
    local = CONFIG_DIR / "local.toml"
    current = {}
    if local.exists():
        with open(local, "rb") as f:
            current = tomllib.load(f)
    merged = _deep_merge(current, overrides)
    local.write_text(
        "# Machine-local overrides (git-ignored). Written by calibration;\n"
        "# hand-edits are preserved on rewrite.\n\n" + _to_toml(merged),
        encoding="utf-8")


def _fmt_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{v}"'
    return str(v)


def _to_toml(table: dict, prefix: str = "") -> str:
    """Serialize a dict of scalars and nested dicts (the only shapes our
    config uses) to TOML."""
    lines = []
    scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
    subtables = {k: v for k, v in table.items() if isinstance(v, dict)}
    if prefix and (scalars or not subtables):
        lines.append(f"[{prefix}]")
    for key, value in scalars.items():
        lines.append(f"{key} = {_fmt_value(value)}")
    if lines:
        lines.append("")
    for key, value in subtables.items():
        lines.append(_to_toml(value, f"{prefix}.{key}" if prefix else key))
    return "\n".join(lines)
