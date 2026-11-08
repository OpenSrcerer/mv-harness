r"""Well-known locations (PLAN §3.3/§3.4). Stdlib only.

home()        %MVH_HOME% or %LOCALAPPDATA%\mvh   (models, hf, torch, numba, nltk, locks, bin, config.json)
repo_root()   the mv-harness checkout (src/mvh/io/paths.py -> 3 levels up), or %MVH_REPO%
config()      %LOCALAPPDATA%\mvh\config.json read with utf-8-sig ({} when absent or unreadable)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

__all__ = ["home", "repo_root", "config", "config_path", "models_dir", "locks_dir"]


def home() -> Path:
    h = os.environ.get("MVH_HOME")
    if h:
        return Path(h)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "mvh"


def repo_root() -> Path:
    r = os.environ.get("MVH_REPO")
    if r and (Path(r) / "src" / "mvh").is_dir():
        return Path(r)
    return Path(__file__).resolve().parents[3]


def config_path() -> Path:
    return home() / "config.json"


def config() -> dict[str, Any]:
    p = config_path()
    try:
        with open(p, encoding="utf-8-sig") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def models_dir() -> Path:
    m = os.environ.get("MVH_MODELS_DIR") or config().get("models")
    return Path(m) if m else home() / "models"


def locks_dir() -> Path:
    return home() / "locks"
