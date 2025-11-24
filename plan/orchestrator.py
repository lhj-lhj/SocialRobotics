"""Orchestrator: coordinate thinking and answering flows."""
import asyncio
from typing import Any, Dict, Optional, List

from utils.streamer import ChatGPTSentenceStreamer
from utils.print_utils import cprint
from utils.config import OPENAI_SETTINGS
from plan.controller import ControllerModel
from plan.behavior_generator import BehaviorGenerator
from plan.thinking_config import get_thinking_config
from plan.prompts import (
    THINKING_SYSTEM_PROMPT,
    REASONING_SYSTEM_PROMPT,
    build_thinking_prompt,
    build_reasoning_prompt,
)

# Visible thinking configuration
THINKING_CONFIG = get_thinking_config()
MAX_THINKING_CUES = int(THINKING_CONFIG.get("max_cues", 12) or 12)
THINKING_DURATION_SECONDS = float(THINKING_CONFIG.get("max_duration_seconds", 10.0) or 10.0)
THINKING_PAUSE_SECONDS = float(THINKING_CONFIG.get("pause_seconds", 0.5) or 0.5)
MIN_THINKING_DURATION_SECONDS = float(
    THINKING_CONFIG.get("min_duration_seconds", 8.0) or 8.0
)  # Ensure thinking lasts at least this long

CONFIDENCE_TONE_GUIDANCE = {
    "low": "Sound tentative and gentle, acknowledging uncertainty briefly.",
    "medium": "Use a thoughtful, balanced tone that shows measured confidence.",
    "high": "Respond with warm, natural confidence without sounding scripted.",
}


def normalize_thinking_notes(notes: Any) -> List[str]:
    """Normalize thinking notes so the list is safe to iterate."""
    if isinstance(notes, list):
        return [str(item) for item in notes if item]
    if isinstance(notes, str) and notes.strip():
        return [notes.strip()]
    return []

def normalize_behavior_plan(plan: Any) -> List[Dict[str, str]]:
    """Normalize controller-provided behavior plan entries."""
    normalized: List[Dict[str, str]] = []
    if isinstance(plan, list):
        for entry in plan:
            if not isinstance(entry, dict):
                continue
            gesture = str(entry.get("gesture", "")).strip()
            expression = str(entry.get("expression", "")).strip()
            led = str(entry.get("led", "")).strip()
            reason = str(entry.get("reason", "")).strip()
            if not (gesture or expression or led):
                continue
            normalized.append(
                {
                    "gesture": gesture,
                    "expression": expression,
                    "led": led,
                    "reason": reason,
                }
            )
    return normalized


def _is_meaningful_thinking_cue(text: str) -> bool:
    """Filter out tokens that contain only punctuation or whitespace."""
    stripped = text.strip()
    stripped = stripped.strip(".!?…")
    return bool(stripped)


class Orchestrator:
    """Coordinate the controller, thinking stream, and final answer."""

    def __init__(
        self, 
        question: str, 
        behavior_generator: Optional[BehaviorGenerator] = None,
        furhat_client = None
    ):
        self.question = question
        self.controller = ControllerModel(question)
        self.behavior_generator = behavior_generator or BehaviorGenerator()
        self.furhat_client = furhat_client  # Furhat client used to send speech
        self.decision: Dict[str, Any] = {}
        self.current_answer_text = ""
        self.thinking_window_done = asyncio.Event()

    async def run(self):
        """Execute the full pipeline."""
        self.decision = self.controller.decide()
        need_thinking = bool(self.decision.get("need_thinking", False))
        confidence_hint = self.decision.get("confidence")
        cprint(f"User: {self.question}")
        self.thinking_window_done.clear()

        if not need_thinking:
            self.thinking_window_done.set()
            await self._respond_directly(confidence_hint)
            return

        thinking_notes = normalize_thinking_notes(self.decision.get("thinking_notes"))
        reasoning_hint = self.decision.get("reasoning_hint", "")
        behavior_plan = normalize_behavior_plan(self.decision.get("thinking_behavior_plan"))
        tone_instruction = CONFIDENCE_TONE_GUIDANCE.get(confidence_hint, "")
        self.behavior_generator.set_thinking_mode(True)

        thinking_model = ChatGPTSentenceStreamer(
            user_content=build_thinking_prompt(self.question, thinking_notes),
            model=OPENAI_SETTINGS["thinking_model"],
            temperature=OPENAI_SETTINGS["thinking_temperature"],
            system_prompt=THINKING_SYSTEM_PROMPT,
        )
        reasoning_model = ChatGPTSentenceStreamer(
            user_content=build_reasoning_prompt(
                self.question,
                reasoning_hint,
                tone_instruction=tone_instruction,
            ),
            model=OPENAI_SETTINGS["reasoning_model"],
            temperature=OPENAI_SETTINGS["reasoning_temperature"],
            system_prompt=REASONING_SYSTEM_PROMPT,
        )

        thinking_task = asyncio.create_task(
            self._relay_thinking(thinking_model, thinking_notes, behavior_plan)
        )
        try:
            await self._relay_answer(reasoning_model, confidence_hint)
        finally:
            await thinking_task

    async def _respond_directly(self, confidence_hint: Optional[str]):
        """Handle situations where no thinking window is required."""
        answer = (self.decision.get("answer") or "").strip()
        if not answer:
            answer = "I'm sorry, I can't provide an answer at the moment."
        
        confidence = confidence_hint if confidence_hint in self.behavior_generator.CONFIDENCE_BEHAVIORS else "medium"
        _, gesture_description = self.behavior_generator.get_confidence_behavior(confidence)
        self.behavior_generator.set_pending_confidence(confidence)
        full_answer = answer.strip()
        
        cprint(f"Robot directly responds (confidence={confidence}, gesture={gesture_description})")
        cprint(f"Robot: {full_answer}")
        
        # Send a single utterance to Furhat; gestures are inferred via events
        if self.furhat_client:
            await self.furhat_client.request_speak_text(full_answer)
        
        self.current_answer_text = full_answer

    async def _relay_thinking(
        self,
        thinking_model: ChatGPTSentenceStreamer,
        thinking_notes: List[str],
        behavior_plan: List[Dict[str, str]],
    ):
        """Relay thinking: emit controller notes first, then the thinking model."""
        loop = asyncio.get_running_loop()
        start_time = loop.time()
        deadline = start_time + THINKING_DURATION_SECONDS
        emitted = 0

        async def emit_line(text: str, index: int):
            cprint(f"Robot (thinking): {text}")
            if self.behavior_generator:
                instruction = None
                if behavior_plan:
                    instruction = behavior_plan[index % len(behavior_plan)]
                await self.behavior_generator.perform_thinking_behavior(
                    index, instruction=instruction
                )

        try:
            for note in thinking_notes:
                if loop.time() >= deadline or emitted >= MAX_THINKING_CUES:
                    break
                cleaned = note.strip()
                if not cleaned:
                    continue
                await emit_line(cleaned, emitted)
                emitted += 1
                if loop.time() >= deadline or emitted >= MAX_THINKING_CUES:
                    break
                await asyncio.sleep(THINKING_PAUSE_SECONDS)

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
        finally:
            # Enforce a minimum thinking duration
            min_duration = min(MIN_THINKING_DURATION_SECONDS, THINKING_DURATION_SECONDS)
            elapsed = loop.time() - start_time
            if elapsed < min_duration:
                await asyncio.sleep(min_duration - elapsed)
            self.behavior_generator.set_thinking_mode(False)
            self.thinking_window_done.set()

    async def _relay_answer(
        self,
        reasoning_model: ChatGPTSentenceStreamer,
        confidence_hint: Optional[str],
    ):
        """Relay the streamed answer."""
        gesture_description = ""
        first_clause = True
        full_answer_parts = []

        # Collect all sentences first
        async for clause in reasoning_model.stream():
            if first_clause:
                await self.thinking_window_done.wait()
                confidence_level = self.behavior_generator.resolve_confidence(
                    confidence_hint, reasoning_model.word_count
                )
                _, gesture_description = self.behavior_generator.get_confidence_behavior(confidence_level)
                self.behavior_generator.set_pending_confidence(confidence_level)
                cprint(f"Robot switches to answer mode (confidence={confidence_level}, gesture={gesture_description})")
                
                # Gestures are dispatched by the bridge when speech starts
                first_clause = False

            cprint(f"Robot: {clause}")
            full_answer_parts.append(clause)
        
        # Send a single combined utterance to Furhat to avoid repeated triggers
        if full_answer_parts:
            full_answer = " ".join(full_answer_parts).strip()
            self.current_answer_text = full_answer
            
            # Only send once at the end
            if self.furhat_client:
                await self.furhat_client.request_speak_text(full_answer)
        
        if gesture_description:
            cprint(f"Robot (non-verbal gesture): {gesture_description}")
