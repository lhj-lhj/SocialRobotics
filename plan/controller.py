"""控制模块：判断信任程度和是否需要思考"""
import json
import requests
from typing import Any, Dict

from utils.config import load_api_settings_from_files, OPENAI_SETTINGS
from plan.prompts import CONTROLLER_SYSTEM_PROMPT


class ControllerModel:
    """调用控制模型，判断是否需要显示思考并给出提示"""

    def __init__(self, question: str):
        load_api_settings_from_files()
        self.question = question
        self.api_key = OPENAI_SETTINGS["api_key"]
        if not self.api_key:
            raise RuntimeError("请在配置中填入合法的 API Key")
        self.base_url = OPENAI_SETTINGS["base_url"].rstrip("/")
        self.model = OPENAI_SETTINGS.get("controller_model", OPENAI_SETTINGS["reasoning_model"])
        self.temperature = OPENAI_SETTINGS.get("controller_temperature", 0.2)

    def decide(self) -> Dict[str, Any]:
        """决策是否需要思考，并返回信心等级等信息"""
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": CONTROLLER_SYSTEM_PROMPT},
                {"role": "user", "content": self.question},
            ],
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        return self._parse_json(content)

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        """解析控制模型返回的 JSON"""
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            if candidate.lower().startswith("json"):
                candidate = candidate[4:]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as err:
            raise RuntimeError(f"控制模型返回的内容无法解析为 JSON：{candidate}") from err

