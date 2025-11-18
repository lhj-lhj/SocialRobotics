"""编排器：组织思考和回答流程"""
import asyncio
import json
from typing import Any, Dict, Optional, List

from utils.streamer import ChatGPTSentenceStreamer
from utils.config import OPENAI_SETTINGS
from utils.session_logger import SessionLogger
from plan.controller import ControllerModel
from plan.behavior_generator import BehaviorGenerator
from plan.prompts import (
    THINKING_SYSTEM_PROMPT,
    REASONING_SYSTEM_PROMPT,
    build_thinking_prompt,
    build_reasoning_prompt,
)

# Visible thinking configuration
MAX_THINKING_CUES = 3
THINKING_DURATION_SECONDS = 10.0
THINKING_PAUSE_SECONDS = 0.5
THINKING_FALLBACK_LINES = [
    "Let me think this through.",
    "I'm weighing a couple of options.",
    "Checking what I already know.",
    "Almost ready with an answer.",
    "Considering how this fits your question.",
]


def normalize_thinking_notes(notes: Any) -> List[str]:
    """规范化思考笔记"""
    if isinstance(notes, list):
        return [str(item) for item in notes if item]
    if isinstance(notes, str) and notes.strip():
        return [notes.strip()]
    return []

def _is_meaningful_thinking_cue(text: str) -> bool:
    """过滤掉仅包含标点或空白的 token"""
    stripped = text.strip()
    stripped = stripped.strip(".!?…")
    return bool(stripped)


class Orchestrator:
    """调度思考层与 ChatGPT 主回答，控制可见的状态切换"""

    def __init__(
        self,
        question: str,
        behavior_generator: Optional[BehaviorGenerator] = None,
        furhat_client=None,
        session_logger: Optional[SessionLogger] = None,
    ):
        self.question = question
        self.controller = ControllerModel(question)
        self.behavior_generator = behavior_generator or BehaviorGenerator()
        self.furhat_client = furhat_client  # Furhat 客户端，用于发送文本
        self.decision: Dict[str, Any] = {}
        self.current_answer_text = ""
        self.thinking_window_done = asyncio.Event()
        self.logger = session_logger or SessionLogger()

    async def run(self):
        """运行编排流程"""
        self.logger.log("UserQuestion", self.question)
        self.decision = self.controller.decide()
        self.logger.log_block(
            "ControllerDecision",
            json.dumps(self.decision, ensure_ascii=False, indent=2)
        )
        need_thinking = bool(self.decision.get("need_thinking", False))
        confidence_hint = self.decision.get("confidence")
        self.thinking_window_done.clear()

        if not need_thinking:
            self.thinking_window_done.set()
            await self._respond_directly(confidence_hint)
            return

        # 需要思考的情况
        thinking_notes = normalize_thinking_notes(self.decision.get("thinking_notes"))
        reasoning_hint = self.decision.get("reasoning_hint", "")
        self.behavior_generator.set_thinking_mode(True)

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
            await thinking_task

    async def _respond_directly(self, confidence_hint: Optional[str]):
        """直接回答（不需要思考）"""
        answer = (self.decision.get("answer") or "").strip()
        if not answer:
            answer = "I'm sorry, I can't provide an answer at the moment."
        
        confidence = (
            confidence_hint
            if confidence_hint in self.behavior_generator.CONFIDENCE_BEHAVIORS
            else "medium"
        )
        prefix, gesture_description = self.behavior_generator.get_confidence_behavior(confidence)
        full_answer = f"{prefix} {answer}".strip()

        self.logger.log(
            "DirectResponse",
            f"confidence={confidence}, gesture={gesture_description}"
        )
        self.logger.log("RobotOutput", full_answer)

        # 发送文本到 Furhat（只发送一次完整答案）
        # 动作会在 on_speak_start 事件中根据文本内容自动执行
        if self.furhat_client:
            await self.furhat_client.request_speak_text(full_answer)
        
        self.current_answer_text = full_answer

    async def _relay_thinking(self, thinking_model: ChatGPTSentenceStreamer):
        """中继思考过程"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + THINKING_DURATION_SECONDS
        emitted = 0
        fallback_idx = 0

        async def emit_line(text: str, index: int):
            self.logger.log("ThinkingCue", f"#{index + 1}: {text}")
            if self.furhat_client:
                await self.furhat_client.request_speak_text(text)
            if self.behavior_generator:
                await self.behavior_generator.perform_thinking_behavior(index)

        try:
            async for cue in thinking_model.stream():
                if loop.time() >= deadline or emitted >= MAX_THINKING_CUES:
                    break
                if not _is_meaningful_thinking_cue(cue):
                    continue

                await emit_line(cue, emitted)
                emitted += 1
                if loop.time() >= deadline or emitted >= MAX_THINKING_CUES:
                    break
                await asyncio.sleep(THINKING_PAUSE_SECONDS)

            while loop.time() < deadline and emitted < MAX_THINKING_CUES:
                filler = THINKING_FALLBACK_LINES[fallback_idx % len(THINKING_FALLBACK_LINES)]
                fallback_idx += 1
                await emit_line(filler, emitted)
                emitted += 1
                if loop.time() >= deadline or emitted >= MAX_THINKING_CUES:
                    break
                await asyncio.sleep(THINKING_PAUSE_SECONDS)
        finally:
            self.behavior_generator.set_thinking_mode(False)
            self.thinking_window_done.set()
            self.logger.log("ThinkingPhase", "finished")

    async def _relay_answer(
        self,
        reasoning_model: ChatGPTSentenceStreamer,
        confidence_hint: Optional[str],
    ):
        """中继回答过程"""
        prefix = ""
        gesture_description = ""
        first_clause = True
        answer_parts = []
        full_answer_parts = []

        # 先收集所有句子
        async for clause in reasoning_model.stream():
            if first_clause:
                await self.thinking_window_done.wait()
                confidence_level = self.behavior_generator.resolve_confidence(
                    confidence_hint, reasoning_model.word_count
                )
                prefix, gesture_description = self.behavior_generator.get_confidence_behavior(confidence_level)
                self.logger.log(
                    "AnswerMode",
                    f"confidence={confidence_level}, gesture={gesture_description}"
                )
                
                # 动作会在 on_speak_start 事件中根据文本内容自动执行，这里不需要手动执行
                first_clause = False

            answer_parts.append(clause)
            full_clause = f"{prefix} {clause}".strip() if prefix else clause
            full_answer_parts.append(clause)
            self.logger.log("AnswerClause", full_clause)
        
        # 合并所有句子，一次性发送到 Furhat（避免每个句子都触发事件）
        if full_answer_parts:
            full_answer = f"{prefix} {' '.join(full_answer_parts)}".strip() if prefix else " ".join(full_answer_parts)
            self.current_answer_text = full_answer
            self.logger.log("RobotOutput", full_answer)
            
            # 只在最后发送一次完整答案
            if self.furhat_client:
                await self.furhat_client.request_speak_text(full_answer)
        
        if gesture_description:
            self.logger.log("RobotGesture", gesture_description)

