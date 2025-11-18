"""Behavior generator: translate action descriptions into Furhat API calls."""
from typing import Optional, Tuple, Dict, Any
from furhat_realtime_api import AsyncFurhatClient


class BehaviorGenerator:
    """Convert confidence levels and action descriptions into multimodal behaviors."""

    # Confidence tier to (verbal prefix, base gesture, expression, LED color)
    # CONFIDENCE_BEHAVIORS: Dict[str, Tuple[str, str, str, str]] = {
    #     "low": ("I'm not entirely sure, but", "slight head shake", "Oh", "yellow"),
    #     "medium": ("Let me think", "look straight", "Thoughtful", "blue"),
    #     "high": ("I'm confident that", "nod head", "BigSmile", "green"),
    # }
    CONFIDENCE_BEHAVIORS: Dict[str, Tuple[str, str, str, str]] = {
        "low": ("I'm not entirely sure, but", "slight head shake", "Oh", "yellow"),
        "medium": ("Let me think", "look straight", "Thoughtful", "blue"),
        "high": ("I'm confident that", "nod head", "BigSmile", "green"),
    }

    # Legacy tuple format (verbal prefix + base gesture)
    @staticmethod
    def _get_legacy_behavior(confidence: str) -> Tuple[str, str]:
        """Return the two-field legacy format (verbal prefix + gesture)."""
        full = BehaviorGenerator.CONFIDENCE_BEHAVIORS.get(
            confidence, ("Let me think", "look straight", "Oh", "blue")
        )
        return (full[0], full[1])

    def __init__(self, furhat_client: Optional[AsyncFurhatClient] = None):
        self.furhat = furhat_client
        self._thinking_mode = False
        self._pending_confidence: Optional[str] = None

    def get_confidence_behavior(self, confidence: str) -> Tuple[str, str]:
        """Return the verbal prefix and gesture for the given confidence tier."""
        if confidence not in self.CONFIDENCE_BEHAVIORS:
            confidence = "medium"
        return self._get_legacy_behavior(confidence)

    def get_full_confidence_behavior(self, confidence: str) -> Tuple[str, str, str, str]:
        """Return the full multimodal behavior tuple for the confidence tier."""
        if confidence not in self.CONFIDENCE_BEHAVIORS:
            confidence = "medium"
        return self.CONFIDENCE_BEHAVIORS[confidence]

    def set_thinking_mode(self, active: bool):
        """Flag that the robot is currently verbalizing visible thinking."""
        self._thinking_mode = active

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

    async def perform_thinking_behavior(self, sequence_index: int = 0):
        """Loop through gestures/expressions/LED cues during thinking."""
        if not self.furhat:
            return

        gesture_cycle = ["look straight", "slight head shake"]
        expression_cycle = ["Thoughtful", "Oh"]
        led_color = "#FFA500"

        gesture = gesture_cycle[sequence_index % len(gesture_cycle)]
        expression = expression_cycle[sequence_index % len(expression_cycle)]

        import asyncio
        await asyncio.gather(
            self.execute_gesture(gesture),
            self.execute_gesture_expression(expression),
            self.execute_led_color_hex(led_color),
            return_exceptions=True
        )

    async def execute_multimodal_behavior(self, confidence: str):
        """Perform the confidence-specific multimodal behavior."""
        if not self.furhat:
            return

        prefix, gesture, expression, led_color = self.get_full_confidence_behavior(confidence)

        import asyncio
        tasks = []

        tasks.append(self.execute_gesture(gesture))
        tasks.append(self.execute_gesture_expression(expression))
        tasks.append(self.execute_led_color(led_color))

        await asyncio.gather(*tasks, return_exceptions=True)

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

    @staticmethod
    def _estimate_confidence_from_words(word_count: int) -> str:
        """Heuristic: longer replies imply higher confidence."""
        if word_count < 25:
            return "low"
        if word_count < 60:
            return "medium"
        return "high"
