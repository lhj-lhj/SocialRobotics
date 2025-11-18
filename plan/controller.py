"""Controller module: decide confidence and whether visible thinking is needed."""
import json
import requests
from typing import Any, Dict

from utils.config import load_api_settings_from_files, OPENAI_SETTINGS
from plan.prompts import CONTROLLER_SYSTEM_PROMPT


class ControllerModel:
    """Call the controller model to decide if thinking should be shown and gather hints."""

    def __init__(self, question: str):
        load_api_settings_from_files()
        self.question = question
        self.api_key = OPENAI_SETTINGS["api_key"]
        if not self.api_key:
            raise RuntimeError("Please configure a valid API key.")
        self.base_url = OPENAI_SETTINGS["base_url"].rstrip("/")
        self.model = OPENAI_SETTINGS.get("controller_model", OPENAI_SETTINGS["reasoning_model"])
        self.temperature = OPENAI_SETTINGS.get("controller_temperature", 0.2)

    def decide(self) -> Dict[str, Any]:
        """Determine whether thinking is needed and return metadata such as confidence."""
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
        """Parse the JSON payload returned by the controller model."""
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            if candidate.lower().startswith("json"):
                candidate = candidate[4:]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as err:
            raise RuntimeError(f"Controller response is not valid JSON: {candidate}") from err

