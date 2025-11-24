"""Thinking configuration loader (durations, pause, cues, scripted behaviors)."""
import json
from pathlib import Path
from typing import Any, Dict, List
from utils.print_utils import cprint


DEFAULT_CONFIG: Dict[str, Any] = {
    "min_duration_seconds": 8.0,
    "max_duration_seconds": 10.0,
    "pause_seconds": 0.5,
    "max_cues": 12,
    "behaviors": [],
}

CONFIG_PATH = Path(__file__).resolve().parent.parent / "thinking_config.json"
LEGACY_BEHAVIORS_PATH = Path(__file__).resolve().parent.parent / "thinking_behaviors.json"

_CACHED_CONFIG: Dict[str, Any] = {}


def _safe_load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception as err:
        cprint(f"[ThinkingConfig] Failed to load {path.name}: {err}")
        return None


def _merge_config(base: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in loaded.items():
        if key in merged and value is not None:
            merged[key] = value
        elif key not in merged:
            merged[key] = value
    return merged


def get_thinking_config() -> Dict[str, Any]:
    """Load thinking config once (durations, pause, cues, behaviors)."""
    global _CACHED_CONFIG
    if _CACHED_CONFIG:
        return _CACHED_CONFIG

    config = dict(DEFAULT_CONFIG)

    # Load main config file if present
    loaded = _safe_load_json(CONFIG_PATH)
    if isinstance(loaded, dict):
        config = _merge_config(config, loaded)

    # Behaviors: prefer config file; fall back to legacy thinking_behaviors.json
    behaviors = config.get("behaviors") or []
    if not behaviors:
        legacy = _safe_load_json(LEGACY_BEHAVIORS_PATH)
        if isinstance(legacy, list):
            behaviors = legacy
    if isinstance(behaviors, list):
        cleaned: List[Dict[str, Any]] = []
        for entry in behaviors:
            if isinstance(entry, dict):
                cleaned.append(entry)
        config["behaviors"] = cleaned
    else:
        config["behaviors"] = []

    _CACHED_CONFIG = config
    return _CACHED_CONFIG
