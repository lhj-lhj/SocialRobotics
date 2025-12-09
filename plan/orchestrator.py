"""Orchestrator: coordinate thinking and answering flows."""
import asyncio
from typing import Any, Dict, Optional, List

from utils.streamer import ChatGPTSentenceStreamer
from utils.print_utils import cprint
from utils.config import OPENAI_SETTINGS
from plan.controller import ControllerModel
from plan.behavior_generator import BehaviorGenerator
from plan.thinking_config import get_thinking_config
from utils.trial_memory import TrialMemory
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
DIRECT_RESPONSE_DELAY_SECONDS = float(
    THINKING_CONFIG.get("direct_response_delay_seconds", 0.0) or 0.0
)  # Optional delay before speaking when no thinking is needed
PERSIST_TRIALS = False  # Do not auto-record; rely on fixed my_trials.json

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
            look_at = None
            target = entry.get("look_at") or entry.get("location") or entry.get("target")
            if isinstance(target, dict):
                try:
                    look_at = {
                        "x": float(target["x"]),
                        "y": float(target["y"]),
                        "z": float(target["z"]),
                    }
                except (KeyError, TypeError, ValueError):
                    look_at = None

            if not (gesture or expression or led or look_at):
                continue
            item: Dict[str, Any] = {
                "gesture": gesture,
                "expression": expression,
                "led": led,
                "reason": reason,
            }
            if look_at:
                item["look_at"] = look_at
            normalized.append(item)
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
        furhat_client = None,
        trial_memory: Optional[TrialMemory] = None,
        replay_only: bool = False,
        skip_replay_thinking: bool = False,
        use_trial_memory: bool = True,
    ):
        self.question = question
        self.controller = ControllerModel(question)
        self.behavior_generator = behavior_generator or BehaviorGenerator()
        self.furhat_client = furhat_client  # Furhat client used to send speech
        self.trial_memory = trial_memory or TrialMemory()
        self.replay_only = replay_only
        self.skip_replay_thinking = skip_replay_thinking or replay_only
        self.use_trial_memory = use_trial_memory
        self.decision: Dict[str, Any] = {}
        self.current_answer_text = ""
        self.thinking_cues_emitted: List[str] = []
        self.resolved_confidence: Optional[str] = None
        self.thinking_window_done = asyncio.Event()

    async def run(self):
        """Execute the full pipeline."""
        self.thinking_cues_emitted = []
        self.resolved_confidence = None
        self.thinking_window_done.clear()
        cprint(f"User: {self.question}")

        cached = self.trial_memory.get(self.question) if self.use_trial_memory else None
        if cached:
            cprint("Replaying recorded response for repeated question (no new model calls)")
            await self._replay_cached_trial(cached, skip_thinking=self.skip_replay_thinking)
            return
        if self.replay_only and not cached:
            cprint("Replay-only mode: no stored answer found, falling back to model")

        self.decision = self.controller.decide()
        need_thinking = bool(self.decision.get("need_thinking", False))
        confidence_hint = self.decision.get("confidence")

        if not need_thinking:
            self.thinking_window_done.set()
            await self._respond_directly(confidence_hint)
            self._persist_trial_record()
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
        self._persist_trial_record()

    def _append_follow_up(self, answer: str, user_has_more: Optional[bool] = None) -> str:
        """Add a short guidance line to prompt the next question or close."""
        if user_has_more is False:
            tail = "Thanks for chatting. That's all for today."
        else:
            tail = "Do you have another question?"
        return f"{answer} {tail}".strip()

    async def _respond_no_record(self):
        """Respond when replay-only mode has no stored answer."""
        full_answer = self._append_follow_up(
            "I don't have a stored answer for that yet. Please ask one of the prepared questions."
        )
        cprint(f"Robot: {full_answer}")
        if self.furhat_client:
            await self.furhat_client.request_speak_text(full_answer)
        self.current_answer_text = full_answer
        self.thinking_window_done.set()

    async def _respond_directly(self, confidence_hint: Optional[str]):
        """Handle situations where no thinking window is required."""
        answer = (self.decision.get("answer") or "").strip()
        if not answer:
            answer = "I'm sorry, I can't provide an answer at the moment."

        if DIRECT_RESPONSE_DELAY_SECONDS > 0:
            await asyncio.sleep(DIRECT_RESPONSE_DELAY_SECONDS)
        
        confidence = confidence_hint if confidence_hint in self.behavior_generator.CONFIDENCE_BEHAVIORS else "medium"
        _, gesture_description = self.behavior_generator.get_confidence_behavior(confidence)
        self.behavior_generator.set_pending_confidence(confidence)
        full_answer = self._append_follow_up(answer.strip())
        self.resolved_confidence = confidence
        
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
                self.thinking_cues_emitted.append(cleaned)
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

                self.thinking_cues_emitted.append(cue)
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
                self.resolved_confidence = confidence_level
                _, gesture_description = self.behavior_generator.get_confidence_behavior(confidence_level)
                self.behavior_generator.set_pending_confidence(confidence_level)
                cprint(f"Robot switches to answer mode (confidence={confidence_level}, gesture={gesture_description})")
                
                # Gestures are dispatched by the bridge when speech starts
                first_clause = False

            cprint(f"Robot: {clause}")
            full_answer_parts.append(clause)
        
        # Send a single combined utterance to Furhat to avoid repeated triggers
        if full_answer_parts:
            full_answer = self._append_follow_up(" ".join(full_answer_parts).strip())
            self.current_answer_text = full_answer
            
            # Only send once at the end
            if self.furhat_client:
                await self.furhat_client.request_speak_text(full_answer)
        
        if gesture_description:
            cprint(f"Robot (non-verbal gesture): {gesture_description}")

    async def _replay_cached_trial(self, record: Dict[str, Any], skip_thinking: bool = False):
        """Replay a stored trial without calling models again."""
        self.decision = record.get("decision") if isinstance(record.get("decision"), dict) else {}
        answer = str(record.get("answer", "")).strip()
        thinking_cues = []
        for cue in record.get("thinking_cues") or []:
            text = str(cue).strip()
            if text:
                thinking_cues.append(text)
        self.thinking_cues_emitted = thinking_cues

        final_confidence = str(record.get("final_confidence", "")).strip()
        if not final_confidence:
            raw_conf = self.decision.get("confidence")
            if isinstance(raw_conf, str) and raw_conf.strip():
                final_confidence = raw_conf.strip()

        behavior_plan = normalize_behavior_plan(self.decision.get("thinking_behavior_plan"))
        need_thinking = bool(self.decision.get("need_thinking", bool(thinking_cues))) and not skip_thinking

        if need_thinking and thinking_cues:
            self.behavior_generator.set_thinking_mode(True)
            loop = asyncio.get_running_loop()
            start_time = loop.time()
            for idx, cue in enumerate(thinking_cues):
                cprint(f"Robot (thinking): {cue}")
                if self.behavior_generator:
                    instruction = behavior_plan[idx % len(behavior_plan)] if behavior_plan else None
                    await self.behavior_generator.perform_thinking_behavior(idx, instruction=instruction)
                if idx < len(thinking_cues) - 1:
                    await asyncio.sleep(THINKING_PAUSE_SECONDS)

            min_duration = min(MIN_THINKING_DURATION_SECONDS, THINKING_DURATION_SECONDS)
            elapsed = loop.time() - start_time
            if elapsed < min_duration:
                await asyncio.sleep(min_duration - elapsed)
            self.behavior_generator.set_thinking_mode(False)
            self.thinking_window_done.set()
        else:
            if DIRECT_RESPONSE_DELAY_SECONDS > 0:
                await asyncio.sleep(DIRECT_RESPONSE_DELAY_SECONDS)
            self.thinking_window_done.set()

        confidence = final_confidence if final_confidence in self.behavior_generator.CONFIDENCE_BEHAVIORS else "medium"
        self.resolved_confidence = confidence
        _, gesture_description = self.behavior_generator.get_confidence_behavior(confidence)
        self.behavior_generator.set_pending_confidence(confidence)
        cprint(f"Robot switches to answer mode (confidence={confidence}, gesture={gesture_description})")
        cprint(f"Robot: {answer}")
        if self.furhat_client:
            await self.furhat_client.request_speak_text(answer)
        if gesture_description:
            cprint(f"Robot (non-verbal gesture): {gesture_description}")
        self.current_answer_text = answer

    def _persist_trial_record(self):
        """Save the latest run so repeated questions reuse the same flow."""
        if not PERSIST_TRIALS or not self.use_trial_memory:
            return
        if not self.current_answer_text:
            return
        record = {
            "question": self.question,
            "answer": self.current_answer_text,
            "thinking_cues": self.thinking_cues_emitted,
            "decision": self.decision,
            "final_confidence": self.resolved_confidence,
        }
        try:
            self.trial_memory.save_record(record)
        except Exception as err:
            cprint(f"[TrialMemory] Failed to persist record: {err}")
