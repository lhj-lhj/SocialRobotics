"""Furhat connection bridge."""
import asyncio
import signal
from typing import Optional
from furhat_realtime_api import AsyncFurhatClient, Events

from plan.orchestrator import Orchestrator
from plan.behavior_generator import BehaviorGenerator
from utils.print_utils import cprint


class FurhatBridge:
    """Bridge between the local planner and the Furhat robot."""

    def __init__(self, host: str = "192.168.1.114", auth_key: Optional[str] = None, replay_only: bool = False, use_trial_memory: bool = True):
        self.host = host
        self.auth_key = auth_key
        # Opening line: self-intro + task framing
        self.conversation_starter = (
            "I am Elizabeth, a robot that shows visible thinking. I will answer your moral "
            "dilemma questions: I will think first, then give a conclusion and a brief reason."
        )
        self.stop_event: Optional[asyncio.Event] = None
        self.shutting_down = False
        self.replay_only = replay_only
        self.use_trial_memory = use_trial_memory
        # When replaying stored trials, skip thinking behaviors if requested (default true for replay-only)
        self.skip_replay_thinking = replay_only
        self.disable_multimodal = replay_only  # disable gestures/expressions in replay-only mode
        
        # Connect to Furhat
        self.furhat = AsyncFurhatClient(host, auth_key=auth_key)
        
        # Share the Furhat client with the behavior generator
        self.behavior_generator = BehaviorGenerator(
            furhat_client=self.furhat,
            disable_multimodal=self.disable_multimodal,
        )
        
        # Conversation history
        self.dialog_history = []
        self.current_user_utt: Optional[str] = None
        self.orchestrator_task: Optional[asyncio.Task] = None

    def setup_signal_handlers(self):
        """Install signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            # Signal 2 = SIGINT (Ctrl+C), signal 15 = SIGTERM
            signal_name = "SIGINT" if signum == 2 else f"SIGTERM ({signum})"
            cprint(f"\nReceived {signal_name}, shutting down gracefully...")
            # Ask the main loop to exit
            if self.stop_event is not None:
                self.stop_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)

    async def shutdown(self):
        """Shut down gracefully."""
        if self.shutting_down:
            return
        
        self.shutting_down = True
        cprint("Shutting down...")
        
        try:
            # Cancel any pending orchestrator task
            self.cancel_request()
            # Stop listening/speaking
            await self.furhat.request_listen_stop()
            await self.furhat.request_speak_stop()
        except Exception as e:
            cprint(f"Error during shutdown: {e}")
        
        if self.stop_event is not None:
            self.stop_event.set()

    def commit_user(self):
        """Store the latest user utterance in the dialogue history."""
        if self.current_user_utt is None:
            return
        self.dialog_history.append({"role": "user", "content": self.current_user_utt})
        self.current_user_utt = None

    def commit_robot(self, message: str):
        """Store the robot reply in the dialogue history."""
        self.dialog_history.append({"role": "assistant", "content": message})

    def cancel_request(self):
        """Cancel the current orchestrator task if it is still running."""
        self.current_user_utt = None
        if self.orchestrator_task and not self.orchestrator_task.done():
            cprint("[System] Cancelling request...")
            self.orchestrator_task.cancel()

    async def on_hear_start(self, event):
        """Handle the start of a user utterance."""
        if not self.shutting_down:
            cprint("\n[User] Started speaking...")
            self.cancel_request()

    async def on_hear_end(self, event):
        """Handle the end of a user utterance."""
        if self.shutting_down:
            return
        
        # Ignore new input if a previous request is still active
        if self.orchestrator_task and not self.orchestrator_task.done():
            cprint("[System] Previous request still processing, ignoring new input")
            return
        
        user_text = event.get("text", "").strip()
        if not user_text:
            return
        
        cprint(f"[User] Speech content: {user_text}")
        self.current_user_utt = user_text
        self.orchestrator_task = asyncio.create_task(self._process_user_input(user_text))

    async def on_hear_partial(self, event):
        """Handle partial ASR hypotheses."""
        if not self.shutting_down:
            partial_text = event.get("text", "")
            cprint(f"[User] Recognizing: {partial_text}", end='\r')

    async def on_speak_start(self, event):
        """Handle robot speech start and trigger multimodal behaviors."""
        if not self.shutting_down:
            robot_text = event.get("text", "")
            if self.behavior_generator.is_in_thinking_mode():
                cprint(f"[Robot][thinking] Speaking: {robot_text}")
                return

            cprint(f"[Robot] Started speaking: {robot_text}")
            self.commit_user()

            # Infer confidence based on the spoken prefix and fire behaviors
            confidence = self.behavior_generator.infer_confidence_from_text(robot_text)
            prefix, gesture, expression = self.behavior_generator.get_full_confidence_behavior(confidence)
            cprint(f"[System] Inferred confidence: {confidence}")
            cprint(f"[System] Multimodal behaviors: gesture={gesture}, expression={expression}")

            # Execute gestures + expression concurrently (LEDs disabled)
            if self.behavior_generator.furhat:
                await self.behavior_generator.execute_multimodal_behavior(confidence)

    async def on_speak_end(self, event):
        """Handle robot speech end events."""
        if not self.shutting_down:
            robot_text = event.get("text", "")
            aborted = event.get("aborted", False)
            if self.behavior_generator.is_in_thinking_mode():
                if aborted:
                    cprint(f"[Robot][thinking] Speech interrupted: {robot_text}")
                return
            if aborted:
                cprint(f"[Robot] Speech interrupted: {robot_text}")
            self.commit_robot(robot_text)
            # Allow the next input to be processed
            self.orchestrator_task = None

    async def _process_user_input(self, user_text: str):
        """Pass user text to the orchestrator."""
        try:
            # Provide the Furhat client so the orchestrator can send speech
            orchestrator = Orchestrator(
                user_text, 
                behavior_generator=self.behavior_generator,
                furhat_client=self.furhat,
                replay_only=self.replay_only,
                skip_replay_thinking=self.skip_replay_thinking,
                use_trial_memory=self.use_trial_memory,
            )
            await orchestrator.run()
            # Clear the task upon completion
            self.orchestrator_task = None
                
        except asyncio.CancelledError:
            cprint("[System] Request cancelled")
            self.orchestrator_task = None
        except Exception as e:
            cprint(f"\n❌ Error processing user input: {e}")
            import traceback
            traceback.print_exc()
            self.orchestrator_task = None

    async def run(self):
        """Main dialogue loop."""
        self.stop_event = asyncio.Event()
        self.setup_signal_handlers()
        cprint("Starting dialogue...")
        cprint("Press Ctrl+C to stop gracefully")
        
        try:
            await self.furhat.connect()
        except Exception as e:
            cprint(f"Failed to connect to Furhat ({self.host}): {e}")
            return

        # Register event handlers
        self.furhat.add_handler(Events.response_hear_start, self.on_hear_start)
        self.furhat.add_handler(Events.response_hear_end, self.on_hear_end)
        self.furhat.add_handler(Events.response_hear_partial, self.on_hear_partial)
        self.furhat.add_handler(Events.response_speak_start, self.on_speak_start)
        self.furhat.add_handler(Events.response_speak_end, self.on_speak_end)

        # Look at the user
        await self.furhat.request_attend_user()

        # Deliver the greeting
        await self.furhat.request_speak_text(self.conversation_starter)

        # Start listening with partial hypotheses enabled
        await self.furhat.request_listen_start(
            concat=True,  # merge ASR chunks into one utterance
            partial=True,  # allow partial ASR results for live view
            stop_no_speech=False,
            stop_user_end=False,
            stop_robot_start=True,  # pause ASR while robot speaks
            resume_robot_end=True,  # resume ASR after robot finishes
            end_speech_timeout=2.5  # allow longer pause for long questions
        )

        # Wait for shutdown signal
        await self.stop_event.wait()

        # Begin shutdown
        cprint("Shutting down...")
        await self.shutdown()
        
        # Disconnect
        try:
            await self.furhat.disconnect()
            cprint("Disconnected from Furhat")
        except Exception as e:
            cprint(f"Error disconnecting: {e}")
