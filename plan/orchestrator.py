"""编排器：组织思考和回答流程"""
import asyncio
from typing import Any, Dict, Optional, List

from utils.streamer import ChatGPTSentenceStreamer
from utils.print_utils import cprint
from utils.config import OPENAI_SETTINGS
from plan.controller import ControllerModel
from plan.behavior_generator import BehaviorGenerator
from plan.prompts import (
    THINKING_SYSTEM_PROMPT,
    REASONING_SYSTEM_PROMPT,
    build_thinking_prompt,
    build_reasoning_prompt,
)


def normalize_thinking_notes(notes: Any) -> List[str]:
    """规范化思考笔记"""
    if isinstance(notes, list):
        return [str(item) for item in notes if item]
    if isinstance(notes, str) and notes.strip():
        return [notes.strip()]
    return []


class Orchestrator:
    """调度思考层与 ChatGPT 主回答，控制可见的状态切换"""

    def __init__(
        self, 
        question: str, 
        behavior_generator: Optional[BehaviorGenerator] = None,
        furhat_client = None
    ):
        self.question = question
        self.stop_thinking = asyncio.Event()
        self.controller = ControllerModel(question)
        self.behavior_generator = behavior_generator or BehaviorGenerator()
        self.furhat_client = furhat_client  # Furhat 客户端，用于发送文本
        self.decision: Dict[str, Any] = {}
        self.current_answer_text = ""

    async def run(self):
        """运行编排流程"""
        self.decision = self.controller.decide()
        need_thinking = bool(self.decision.get("need_thinking", False))
        confidence_hint = self.decision.get("confidence")
        cprint(f"User: {self.question}")

        if not need_thinking:
            await self._respond_directly(confidence_hint)
            return

        # 需要思考的情况
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
        """直接回答（不需要思考）"""
        answer = (self.decision.get("answer") or "").strip()
        if not answer:
            answer = "I'm sorry, I can't provide an answer at the moment."
        
        confidence = confidence_hint if confidence_hint in self.behavior_generator.CONFIDENCE_BEHAVIORS else "medium"
        prefix, gesture_description = self.behavior_generator.get_confidence_behavior(confidence)
        full_answer = f"{prefix} {answer}".strip()
        
        cprint(f"Robot directly responds (confidence={confidence}, gesture={gesture_description})")
        cprint(f"Robot: {full_answer}")
        
        # 发送文本到 Furhat（只发送一次完整答案）
        # 动作会在 on_speak_start 事件中根据文本内容自动执行
        if self.furhat_client:
            await self.furhat_client.request_speak_text(full_answer)
        
        self.current_answer_text = full_answer

    async def _relay_thinking(self, thinking_model: ChatGPTSentenceStreamer):
        """中继思考过程"""
        thinking_texts = []
        async for cue in thinking_model.stream():
            if self.stop_thinking.is_set():
                break
            cprint(f"Robot (thinking): {cue}")
            thinking_texts.append(cue)
            # 可以选择性地将思考过程发送到 Furhat
            # 但通常思考过程只显示，不语音输出

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
                self.stop_thinking.set()
                confidence_level = self.behavior_generator.resolve_confidence(
                    confidence_hint, reasoning_model.word_count
                )
                prefix, gesture_description = self.behavior_generator.get_confidence_behavior(confidence_level)
                cprint(f"Robot switches to answer mode (confidence={confidence_level}, gesture={gesture_description})")
                
                # 动作会在 on_speak_start 事件中根据文本内容自动执行，这里不需要手动执行
                first_clause = False

            answer_parts.append(clause)
            full_clause = f"{prefix} {clause}".strip() if prefix else clause
            full_answer_parts.append(clause)
            cprint(f"Robot: {full_clause}")
        
        # 合并所有句子，一次性发送到 Furhat（避免每个句子都触发事件）
        if full_answer_parts:
            full_answer = f"{prefix} {' '.join(full_answer_parts)}".strip() if prefix else " ".join(full_answer_parts)
            self.current_answer_text = full_answer
            
            # 只在最后发送一次完整答案
            if self.furhat_client:
                await self.furhat_client.request_speak_text(full_answer)
        
        if gesture_description:
            cprint(f"Robot (non-verbal gesture): {gesture_description}")

