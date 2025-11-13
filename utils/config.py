"""配置加载模块"""
import json
import os
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv

CONFIG_JSON_PATH = Path("config.json")
API_KEY_TXT_PATH = Path("api_key.txt")
SETTINGS_LOADED = False

# ==== 基础配置 ====
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
    """从 config.json 或 api_key.txt 或 .env 加载配置"""
    global SETTINGS_LOADED
    if SETTINGS_LOADED:
        return

    api_key = ""
    config_data: Dict[str, Any] = {}

    # 优先从 config.json 加载
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 查找当前目录和上一级目录的 config.json
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
            print(f"警告：config.json 解析失败：{err}")

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

    # 如果没有从 config.json 获取到，尝试 api_key.txt
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

    # 如果还没有，尝试从 .env 加载
    if not api_key:
        env_path = os.path.join(Path(script_dir).parent, '.env')
        if not os.path.exists(env_path):
            env_path = os.path.join(Path(script_dir).parent.parent, '.env')
        load_dotenv(env_path, override=True)
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "未找到 API Key。请在 config.json 的 api_key 字段、api_key.txt 或 .env 文件中的 OPENAI_API_KEY 填写密钥。"
        )

    OPENAI_SETTINGS["api_key"] = api_key
    SETTINGS_LOADED = True

