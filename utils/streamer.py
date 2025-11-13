"""流式处理模块"""
import asyncio
import json
import threading
from typing import List, Optional, Tuple
import requests

from utils.config import load_api_settings_from_files, OPENAI_SETTINGS


class ChatGPTSentenceStreamer:
    """从 ChatGPT 接口流式获取句子级片段"""

    def __init__(
        self,
        user_content: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        system_prompt: str = "",
    ):
        load_api_settings_from_files()
        self.user_content = user_content
        self.model = model or OPENAI_SETTINGS["reasoning_model"]
        default_temp = OPENAI_SETTINGS["reasoning_temperature"]
        self.temperature = temperature if temperature is not None else default_temp
        self.system_prompt = system_prompt
        self.api_key = OPENAI_SETTINGS["api_key"]
        if not self.api_key:
            raise RuntimeError("请在配置中填入合法的 API Key")
        self.base_url = OPENAI_SETTINGS["base_url"].rstrip("/")
        self.word_count = 0

    async def stream(self):
        """异步返回句子级别的流式片段"""
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def producer():
            try:
                for clause in self._generate_clauses():
                    loop.call_soon_threadsafe(queue.put_nowait, clause)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = threading.Thread(target=producer, daemon=True)
        thread.start()

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield item

        thread.join()

    def _generate_clauses(self):
        buffer = ""
        for token in self._token_stream():
            buffer += token
            self.word_count = len(buffer.split())
            ready, buffer = self._pop_ready_clauses(buffer)
            for clause in ready:
                yield clause
        if buffer.strip():
            yield buffer.strip()

    def _token_stream(self):
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "stream": True,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self.user_content},
            ],
        }

        with requests.post(url, headers=headers, json=payload, stream=True, timeout=90) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data:"):
                    data = line.split("data:", 1)[1].strip()
                else:
                    data = line.strip()
                if not data:
                    continue
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield delta

    @staticmethod
    def _pop_ready_clauses(text: str) -> Tuple[List[str], str]:
        """按句子分割文本"""
        clauses: List[str] = []
        start = 0
        for idx, char in enumerate(text):
            if char in ".?!":
                clause = text[start : idx + 1].strip()
                if clause:
                    clauses.append(clause)
                start = idx + 1
        remainder = text[start:]
        return clauses, remainder

