"""Behavior generator: translate action descriptions into Furhat API calls."""
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from furhat_realtime_api import AsyncFurhatClient
from utils.print_utils import cprint
from plan.thinking_config import get_thinking_config


class BehaviorGenerator:
    """Convert confidence levels and action descriptions into multimodal behaviors."""

    # Confidence tier to (verbal prefix, base gesture, expression) — LED removed globally
    CONFIDENCE_BEHAVIORS: Dict[str, Tuple[str, str, str]] = {
        "low": ("I'm not entirely sure, but", "slight head shake", "Oh"),
        "medium": ("Let me think", "look straight", "Thoughtful"),
        "high": ("I'm confident that", "nod head", "BigSmile"),
    }

    # Legacy tuple format (verbal prefix + base gesture)
    @staticmethod
    def _get_legacy_behavior(confidence: str) -> Tuple[str, str]:
        """Return the two-field legacy format (verbal prefix + gesture)."""
        full = BehaviorGenerator.CONFIDENCE_BEHAVIORS.get(
            confidence, ("Let me think", "look straight", "Oh")
        )
        return (full[0], full[1])

    def __init__(self, furhat_client: Optional[AsyncFurhatClient] = None, disable_multimodal: bool = False):
        self.furhat = furhat_client
        self.disable_multimodal = disable_multimodal
        self._thinking_mode = False
        self._pending_confidence: Optional[str] = None
        self._thinking_script: List[Dict[str, Any]] = self._load_thinking_script()
        self._spoken_thinking_steps: set[int] = set()

    def get_confidence_behavior(self, confidence: str) -> Tuple[str, str]:
        """Return the verbal prefix and gesture for the given confidence tier."""
        if confidence not in self.CONFIDENCE_BEHAVIORS:
            confidence = "medium"
        return self._get_legacy_behavior(confidence)

    def get_full_confidence_behavior(self, confidence: str) -> Tuple[str, str, str]:
        """Return the full multimodal behavior tuple for the confidence tier."""
        if confidence not in self.CONFIDENCE_BEHAVIORS:
            confidence = "medium"
        return self.CONFIDENCE_BEHAVIORS[confidence]

    @staticmethod
    def _normalize_location_target(value: Any) -> Optional[Dict[str, float]]:
        """Extract an {x,y,z} dict if provided."""
        if isinstance(value, dict):
            try:
                return {
                    "x": float(value["x"]),
                    "y": float(value["y"]),
                    "z": float(value["z"]),
                }
            except (KeyError, TypeError, ValueError):
                return None
        return None

    def set_thinking_mode(self, active: bool):
        """Flag that the robot is currently verbalizing visible thinking."""
        self._thinking_mode = active
        if not active:
            # Reset per-thinking-window state
            self._spoken_thinking_steps.clear()

    def is_in_thinking_mode(self) -> bool:
        return self._thinking_mode

    def set_pending_confidence(self, confidence: str):
        """Store the resolved confidence for the next utterance."""
        if confidence in self.CONFIDENCE_BEHAVIORS:
            self._pending_confidence = confidence
        else:
            self._pending_confidence = "medium"

    def consume_pending_confidence(self) -> Optional[str]:
        """Return and clear the stored confidence value."""
        value = self._pending_confidence
        self._pending_confidence = None
        return value

    async def perform_thinking_behavior(
        self,
        sequence_index: int = 0,
        instruction: Optional[Dict[str, Any]] = None,
    ):
        """Loop through gestures/expressions during thinking (LED disabled)."""
        if not self.furhat:
            return

        if instruction:
            merged = dict(instruction)
            # If the controller plan lacks some fields, optionally fill from scripted step
            if self._thinking_script:
                script_step = self._thinking_script[sequence_index % len(self._thinking_script)]
                for key in ("gesture", "expression", "led", "led_color", "led_hex", "utterance", "speech", "look_at"):
                    if key not in merged and key in script_step:
                        merged[key] = script_step[key]
            cprint(f"[Thinking] Using controller plan (merged): {merged}")
            await self._apply_behavior_instruction(merged)
            return

        # If a scripted thinking sequence is present, cycle through it
        if self._thinking_script:
            step_index = sequence_index % len(self._thinking_script)
            step = self._thinking_script[step_index]
            cprint(f"[Thinking] Using scripted step: {step}")
            await self._apply_behavior_instruction(step, step_index=step_index)
            return

        gesture_cycle = ["look straight", "slight head shake"]
        expression_cycle = ["Thoughtful", "Oh"]

        gesture = gesture_cycle[sequence_index % len(gesture_cycle)]
        expression = expression_cycle[sequence_index % len(expression_cycle)]

        import asyncio
        await asyncio.gather(
            self.execute_gesture(gesture),
            self.execute_gesture_expression(expression),
            return_exceptions=True
        )

    async def _apply_behavior_instruction(self, instruction: Dict[str, Any], step_index: Optional[int] = None):
        """Execute gestures/expressions/look targets defined by the controller."""
        tasks = []
        gesture = instruction.get("gesture")
        expression = instruction.get("expression")
        # LED changes are disabled globally; ignore any LED fields in instructions
        led = None
        look_at = self._normalize_location_target(
            instruction.get("look_at") or instruction.get("location") or instruction.get("target")
        )
        utterance = instruction.get("utterance") or instruction.get("speech")
        speak_allowed = True
        if step_index is not None:
            # Only speak once per step per thinking window
            if step_index in self._spoken_thinking_steps:
                speak_allowed = False

        if gesture:
            tasks.append(self.execute_gesture(gesture))
        if expression:
            tasks.append(self.execute_gesture_expression(expression))
        if look_at:
            tasks.append(self.execute_attend_location(look_at["x"], look_at["y"], look_at["z"]))

        if tasks:
            import asyncio
            await asyncio.gather(*tasks, return_exceptions=True)

        # Optional utterance during thinking
        if utterance and self.furhat and speak_allowed:
            try:
                await self.furhat.request_speak_text(str(utterance))
                cprint(f"[Thinking] Instruction utterance: {utterance}")
                if step_index is not None:
                    self._spoken_thinking_steps.add(step_index)
            except Exception as e:
                cprint(f"[Thinking] Failed to speak instruction utterance: {e}")

    async def execute_multimodal_behavior(self, confidence: str):
        """Perform the confidence-specific multimodal behavior."""
        if not self.furhat or self.disable_multimodal:
            return

        prefix, gesture, expression = self.get_full_confidence_behavior(confidence)

        import asyncio
        tasks = []

        tasks.append(self.execute_gesture(gesture))
        tasks.append(self.execute_gesture_expression(expression))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def execute_attend_location(self, x: float, y: float, z: float):
        """Move gaze/head to a specific point in meters relative to the robot."""
        if not self.furhat:
            return
        try:
            await self.furhat.request_attend_location(x, y, z)
            print(f"[Multimodal] Attend location: x={x}, y={y}, z={z}")
        except Exception as e:
            print(f"Failed to attend to location ({x}, {y}, {z}): {e}")

    async def execute_gesture(self, gesture_description: str):
        """Map a gesture description to a Furhat action call."""
        if not self.furhat:
            return

        gesture_map = {
            "slight head shake": self._shake_head_slightly,
            "look straight": self._look_straight,
            "nod head": self._nod_head,
        }

        gesture_func = gesture_map.get(gesture_description)
        if gesture_func:
            try:
                await gesture_func()
            except Exception as e:
                print(f"Failed to execute gesture {gesture_description}: {e}")

    async def execute_gesture_expression(self, expression: str):
        """Trigger a facial/gesture expression such as BigSmile or Thoughtful."""
        if not self.furhat:
            return
        try:
            await self.furhat.request_gesture_start(
                name=expression,
                intensity=0.7,
                duration=1.0
            )
            print(f"[Multimodal] Gesture expression: {expression}")
        except Exception as e:
            print(f"Failed to execute gesture expression {expression}: {e}")

    async def execute_led_color(self, color: str):
        """Set LED color using a friendly color name."""
        if not self.furhat:
            return
        try:
            color_map = {
                "red": "#FF0000",
                "green": "#00FF00",
                "blue": "#0066FF",
                "yellow": "#FFC800",
                "purple": "#9600FF",
                "white": "#FFFFFF",
            }

            hex_color = color_map.get(color.lower(), "#0066FF")
            await self.furhat.request_led_set(color=hex_color)
            print(f"[Multimodal] LED color: {color} ({hex_color})")
        except Exception as e:
            print(f"Failed to set LED color {color}: {e}")

    async def execute_led_color_hex(self, hex_color: str):
        """Set LED color directly from a hex code."""
        if not self.furhat:
            return
        try:
            await self.furhat.request_led_set(color=hex_color)
            print(f"[Multimodal] LED color: {hex_color}")
        except Exception as e:
            print(f"Failed to set LED color {hex_color}: {e}")

    async def _shake_head_slightly(self):
        """Trigger Furhat's Shake gesture with a lower intensity."""
        if not self.furhat:
            return
        try:
            await self.furhat.request_gesture_start(
                name="Shake",  
                intensity=0.5,
                duration=0.8
            )
            print("[Multimodal] Gesture: Shake")
        except Exception as e:
            print(f"Failed to run Shake gesture: {e}")

    async def _look_straight(self):
        """Ask Furhat to attend to the user (neutral gaze)."""
        if not self.furhat:
            return
        try:
            await self.furhat.request_attend_user()
            print("[Multimodal] Gesture: attend user")
        except Exception as e:
            print(f"Failed to attend to user: {e}")

    async def _nod_head(self):
        """Trigger the Nod gesture with moderate intensity."""
        if not self.furhat:
            return
        try:
            await self.furhat.request_gesture_start(
                name="Nod",  
                intensity=0.7,
                duration=0.6
            )
            print("[Multimodal] Gesture: Nod")
        except Exception as e:
            print(f"Failed to run Nod gesture: {e}")

    def resolve_confidence(self, hint: Optional[str], word_count: int) -> str:
        """Resolve confidence using the hint or fall back to heuristics."""
        if hint and hint.strip().lower() in self.CONFIDENCE_BEHAVIORS:
            return hint.strip().lower()
        return self._estimate_confidence_from_words(word_count)

    def infer_confidence_from_text(self, text: str) -> str:
        """Infer confidence level based on the spoken text or a stored hint."""
        pending = self.consume_pending_confidence()
        if pending:
            return pending
        text_lower = text.lower()
        if "i'm not entirely sure" in text_lower or "i'm not sure" in text_lower:
            return "low"
        elif "i'm confident" in text_lower or "i'm certain" in text_lower:
            return "high"
        elif "let me think" in text_lower or "i think" in text_lower:
            return "medium"
        return "medium"

    def _load_thinking_script(self) -> List[Dict[str, Any]]:
        """Load scripted thinking behaviors from config (with legacy fallback)."""
        config = get_thinking_config()
        behaviors = config.get("behaviors") or []
        if isinstance(behaviors, list):
            cleaned: List[Dict[str, Any]] = []
            for entry in behaviors:
                if isinstance(entry, dict):
                    cleaned.append(entry)
            return cleaned

        # Legacy fallback to thinking_behaviors.json if config malformed
        script_path = Path(__file__).resolve().parent.parent / "thinking_behaviors.json"
        if not script_path.exists():
            return []
        try:
            with script_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, list):
                cleaned = []
                for entry in data:
                    if isinstance(entry, dict):
                        cleaned.append(entry)
                return cleaned
        except Exception as e:
            cprint(f"Failed to load thinking_behaviors.json: {e}")
        return []

    @staticmethod
    def _estimate_confidence_from_words(word_count: int) -> str:
        """Heuristic: longer replies imply higher confidence."""
        if word_count < 25:
            return "low"
        if word_count < 60:
            return "medium"
        return "high"
