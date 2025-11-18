"""Configuration loader."""
import json
import os
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv

CONFIG_JSON_PATH = Path("config.json")
API_KEY_TXT_PATH = Path("api_key.txt")
SETTINGS_LOADED = False

# ==== Base configuration (overridden by config files) ====
OPENAI_SETTINGS: Dict[str, Any] = {
    "api_key": "",
    "base_url": "https://api.openai.com",
    "controller_model": "gpt-4.1-mini",
    "controller_temperature": 0.2,
    "reasoning_model": "gpt-4.1-mini",
    "reasoning_temperature": 0.4,
    "thinking_model": "gpt-4.1-mini",
    "thinking_temperature": 0.2,
}


def load_api_settings_from_files():
    """Load API settings from config.json, api_key.txt, or .env files."""
    global SETTINGS_LOADED
    if SETTINGS_LOADED:
        return

    api_key = ""
    config_data: Dict[str, Any] = {}

    # Prefer config.json from project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Look for config.json in current and parent directories
    config_path = Path(script_dir).parent / CONFIG_JSON_PATH
    if not config_path.exists():
        config_path = Path(script_dir).parent.parent / CONFIG_JSON_PATH

    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
                if isinstance(loaded, dict):
                    config_data = loaded
        except json.JSONDecodeError as err:
            print(f"Warning: failed to parse config.json: {err}")

    if config_data:
        for field in [
            "api_key",
            "base_url",
            "controller_model",
            "controller_temperature",
            "reasoning_model",
            "reasoning_temperature",
            "thinking_model",
            "thinking_temperature",
        ]:
            if field in config_data and config_data[field]:
                OPENAI_SETTINGS[field] = config_data[field]
        api_key = str(config_data.get("api_key", "")).strip()

    # Fall back to api_key.txt if needed
    if not api_key:
        api_key_path = Path(script_dir).parent / API_KEY_TXT_PATH
        if not api_key_path.exists():
            api_key_path = Path(script_dir).parent.parent / API_KEY_TXT_PATH
        if api_key_path.exists():
            with api_key_path.open("r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        api_key = line
                        break

    # Finally, try .env files
    if not api_key:
        env_path = os.path.join(Path(script_dir).parent, '.env')
        if not os.path.exists(env_path):
            env_path = os.path.join(Path(script_dir).parent.parent, '.env')
        load_dotenv(env_path, override=True)
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "API key not found. Please populate config.json (api_key), api_key.txt, or .env (OPENAI_API_KEY)."
        )

    OPENAI_SETTINGS["api_key"] = api_key
    SETTINGS_LOADED = True

