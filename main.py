import asyncio
import io
import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# 确保控制台能正确输出中文：优先使用 reconfigure，若不可用则包裹成 UTF-8 输出流
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
except Exception:
    pass

CONFIG_JSON_PATH = Path("config.json")
API_KEY_TXT_PATH = Path("api_key.txt")
SETTINGS_LOADED = False

# ==== 基础配置（直接在代码里调参，不依赖外部环境变量） ====
OPENAI_SETTINGS = {
    # 默认留空；运行时会从 config.json 或 api_key.txt 注入
    "api_key": "",
    "base_url": "https://api.openai.com",
    # 调度/判断是否需要思考的控制模型
    "controller_model": "gpt-4.1-mini",
    "controller_temperature": 0.2,
    # 主回答模型
    "reasoning_model": "gpt-4.1-mini",
    "reasoning_temperature": 0.4,
    # 思考模型（目前同一接口，未来可改接 Furhat 专用 thinking 模型）
    "thinking_model": "gpt-4.1-mini",
    "thinking_temperature": 0.2,
}

# 不同信心等级对应的前缀话术与模拟肢体动作
CONFIDENCE_BEHAVIORS: Dict[str, Tuple[str, str]] = {
    "low": ("我不太确定，不过", "轻微摇头"),
    "medium": ("看起来", "平视凝神"),
    "high": ("我很有把握地说", "点头示意"),
}

# 控制模型 Prompt，决定是否需要显示思考
CONTROLLER_SYSTEM_PROMPT = (
    "你是 Furhat 机器人的调度器，只能输出 JSON。"
    "请根据用户问题判断是否需要进入“可见思考”状态，并给出简短思维链。"
    "严格输出以下键："
    '{"need_thinking": true/false,'
    '"confidence": "low/medium/high",'
    '"thinking_notes": ["短句1","短句2"],'
    '"reasoning_hint": "给主回答模型的提示，可为空字符串",'
    '"answer": "当 need_thinking 为 false 时直接给出的最终回答"}。'
    "若 need_thinking 为 true，answer 必须是空字符串或省略。"
    "不要添加多余文本、注释或 Markdown。"
)

# 主回答 Prompt，约束行文风格
REASONING_SYSTEM_PROMPT = (
    "你是 Furhat 社交机器人，请用 2-3 句中文友好回答用户问题，"
    "不要泄露内部推理，只输出最终建议。"
)

# 思考层 Prompt
THINKING_SYSTEM_PROMPT = (
    "你是 Furhat 机器人的可见思考进程，需要在等待期间输出 2-4 句中文短语，"
    "每句少于 12 个字，描述“我在想…/我在对比…/我在确认…”等动作，"
    "语调自然，不给出最终答案，最后无需总结。"
)


def load_api_settings_from_files():
    """从 config.json 或 api_key.txt 注入密钥及可选配置。"""
    global SETTINGS_LOADED
    if SETTINGS_LOADED:
        return

    api_key = ""
    config_data: Dict[str, Any] = {}

    if CONFIG_JSON_PATH.exists():
        try:
            with CONFIG_JSON_PATH.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
                if isinstance(loaded, dict):
                    config_data = loaded
        except json.JSONDecodeError as err:
            raise RuntimeError(f"config.json 解析失败：{err}") from err

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

    if not api_key and API_KEY_TXT_PATH.exists():
        with API_KEY_TXT_PATH.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith("#"):
                    api_key = line
                    break

    if not api_key:
        raise RuntimeError(
            "未找到 API Key。请在 config.json 的 api_key 字段或 api_key.txt 中填写密钥。"
        )

    OPENAI_SETTINGS["api_key"] = api_key
    SETTINGS_LOADED = True


def cprint(text: str):
    """安全打印中文；若默认编码不支持则退回到手动写入。"""
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="ignore"))
            sys.stdout.flush()
        except Exception:
            pass


class ControllerModel:
    """调用控制模型，判断是否需要显示思考并给出提示。"""

    def __init__(self, question: str):
        load_api_settings_from_files()
        self.question = question
        self.api_key = OPENAI_SETTINGS["api_key"]
        if not self.api_key:
            raise RuntimeError("请在 OPENAI_SETTINGS['api_key'] 中填入合法的 API Key。")
        self.base_url = OPENAI_SETTINGS["base_url"].rstrip("/")
        self.model = OPENAI_SETTINGS.get("controller_model", OPENAI_SETTINGS["reasoning_model"])
        self.temperature = OPENAI_SETTINGS.get("controller_temperature", 0.2)

    def decide(self) -> Dict[str, Any]:
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
        candidate = text.strip()
        # 去除可能包裹的 ```json ``` 块
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            if candidate.lower().startswith("json"):
                candidate = candidate[4:]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as err:
            raise RuntimeError(f"控制模型返回的内容无法解析为 JSON：{candidate}") from err


class ChatGPTSentenceStreamer:
    """从 ChatGPT 接口流式获取句子级片段，可复用在主回答或思考通道。"""

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
            raise RuntimeError("请在 OPENAI_SETTINGS['api_key'] 中填入合法的 API Key。")
        self.base_url = OPENAI_SETTINGS["base_url"].rstrip("/")
        self.word_count = 0

    async def stream(self):
        """异步返回句子级别的流式片段。"""
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def producer():
            try:
                for clause in self._generate_clauses():
                    loop.call_soon_threadsafe(queue.put_nowait, clause)
            except Exception as exc:  # pragma: no cover
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


def build_thinking_prompt(question: str, notes: List[str]) -> str:
    filtered = [note for note in notes if note]
    joined = "\n".join(f"- {note}" for note in filtered) or "- 正在梳理可能的答案"
    return (
        f"用户问题：{question}\n"
        f"已有初步思维：\n{joined}\n"
        "按照系统提示生成可见思考短句。"
    )


def build_reasoning_prompt(question: str, hint: str) -> str:
    hint_part = f"\n可参考的初步思路：{hint}" if hint else ""
    return (
        f"用户问题：{question}"
        f"{hint_part}\n"
        "请用 2-3 句总结解决方案，不要输出链式推理。"
    )


def normalize_thinking_notes(notes: Any) -> List[str]:
    if isinstance(notes, list):
        return [str(item) for item in notes if item]
    if isinstance(notes, str) and notes.strip():
        return [notes.strip()]
    return []


def resolve_confidence(hint: Optional[str], word_count: int) -> str:
    if hint:
        key = hint.strip().lower()
        if key in CONFIDENCE_BEHAVIORS:
            return key
    return estimate_confidence_from_words(word_count)


def estimate_confidence_from_words(word_count: int) -> str:
    """根据累计词数粗略估计信心等级。"""
    if word_count < 25:
        return "low"
    if word_count < 60:
        return "medium"
    return "high"


class Orchestrator:
    """调度思考层与 ChatGPT 主回答，控制可见的状态切换。"""

    def __init__(self, question: str):
        self.question = question
        self.stop_thinking = asyncio.Event()
        self.controller = ControllerModel(question)
        self.decision: Dict[str, Any] = {}

    async def run(self):
        self.decision = self.controller.decide()
        need_thinking = bool(self.decision.get("need_thinking", False))
        confidence_hint = self.decision.get("confidence")
        cprint(f"参与者：{self.question}")

        if not need_thinking:
            await self._respond_directly(confidence_hint)
            return

        thinking_notes = normalize_thinking_notes(self.decision.get("thinking_notes"))
        reasoning_hint = self.decision.get("reasoning_hint", "")

        thinking_model = ChatGPTSentenceStreamer(
            user_content=build_thinking_prompt(self.question, thinking_notes),
            model=OPENAI_SETTINGS["thinking_model"],
            temperature=OPENAI_SETTINGS["thinking_temperature"],
            system_prompt=THINKING_SYSTEM_PROMPT,
        )
        reasoning_model = ChatGPTSentenceStreamer(
            user_content=build_reasoning_prompt(self.question, reasoning_hint),
            model=OPENAI_SETTINGS["reasoning_model"],
            temperature=OPENAI_SETTINGS["reasoning_temperature"],
            system_prompt=REASONING_SYSTEM_PROMPT,
        )

        thinking_task = asyncio.create_task(self._relay_thinking(thinking_model))
        try:
            await self._relay_answer(reasoning_model, confidence_hint)
        finally:
            self.stop_thinking.set()
            await thinking_task

    async def _respond_directly(self, confidence_hint: Optional[str]):
        answer = (self.decision.get("answer") or "").strip()
        if not answer:
            answer = "抱歉，我暂时无法给出答案。"
        confidence = confidence_hint if confidence_hint in CONFIDENCE_BEHAVIORS else "medium"
        prefix, gesture = CONFIDENCE_BEHAVIORS[confidence]
        cprint(
            "机器人直接进入回答模式 "
            f"(信心等级={confidence}, 对应动作={gesture})"
        )
        cprint(f"机器人：{prefix}{answer}")
        cprint(f"机器人（非语言动作）：{gesture}")

    async def _relay_thinking(self, thinking_model: ChatGPTSentenceStreamer):
        async for cue in thinking_model.stream():
            if self.stop_thinking.is_set():
                break
            cprint(f"机器人（思考中）：{cue}")

    async def _relay_answer(
        self,
        reasoning_model: ChatGPTSentenceStreamer,
        confidence_hint: Optional[str],
    ):
        prefix = ""
        gesture = ""
        first_clause = True

        async for clause in reasoning_model.stream():
            if first_clause:
                self.stop_thinking.set()
                confidence_level = resolve_confidence(confidence_hint, reasoning_model.word_count)
                prefix, gesture = CONFIDENCE_BEHAVIORS[confidence_level]
                cprint(
                    "机器人切换为回答模式 "
                    f"(信心等级={confidence_level}, 对应动作={gesture})"
                )
                first_clause = False

            cprint(f"机器人：{prefix}{clause}")
        if gesture:
            cprint(f"机器人（非语言动作）：{gesture}")


def main():
    question = input("请向机器人提问：") or "你如何展示思考过程？"
    load_api_settings_from_files()
    orchestrator = Orchestrator(question)
    try:
        asyncio.run(orchestrator.run())
    except RuntimeError as err:
        cprint(f"配置错误：{err}")
    except requests.HTTPError as err:
        cprint(f"OpenAI 接口错误：{err.response.text}")
    except Exception as err:  # pragma: no cover
        cprint(f"未预期的错误：{err}")


if __name__ == "__main__":
    main()
