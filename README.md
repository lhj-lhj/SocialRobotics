# Visible Thinking Furhat Prototype

This project runs a **controller → thinking stream → final answer** pipeline for a Furhat robot, letting it show lightweight “thinking” cues before speaking. It now also supports a replay-only mode that serves stored answers without calling the models.

## What’s New (Dec 2025)
- Removed all LED usage (thinking + answering); prompts no longer mention LED.
- Replay-only mode (`--replay-only`) pulls answers from `my_trials.json`; stored thinking cues are skipped by default.
- Optional direct-response delay via `direct_response_delay_seconds` in `thinking_config.json`.
- ASR stays on while the robot speaks, but input is ignored during speech to avoid accidental cancels.
- After each answer, the robot simply asks, “Do you have another question?” (no 5-question cap).

## Architecture
1) **Controller (`plan/controller.py`)**  
   - Calls an LLM with `CONTROLLER_SYSTEM_PROMPT` (in `plan/prompts.py`) to decide `need_thinking`, `confidence`, short `thinking_notes`, optional `reasoning_hint`, and (when skipping thinking) a final `answer`.
2) **Thinking stream**  
   - If `need_thinking=true`, `plan/orchestrator.py` streams short cues using `THINKING_SYSTEM_PROMPT` and `build_thinking_prompt`. Behaviors/gestures come from `thinking_config.json` or controller-provided plans.
3) **Reasoning stream**  
   - Streams the final answer using `REASONING_SYSTEM_PROMPT` and `build_reasoning_prompt`. Thinking stops when the first answer clause arrives.
4) **Behaviors (`plan/behavior_generator.py`)**  
   - Maps confidence to gesture/expression (LEDs removed). Supports optional `look_at` targets during thinking. You can add `utterance` in behavior steps to speak short “Let me think…” lines.
5) **Replay memory (`utils/trial_memory.py`)**  
   - Loads `my_trials.json` and fuzzy-matches questions (threshold 0.6) to reuse stored answers.

## Run It
```bash
python3 main.py              # thinking behavior 
python3 main.py --replay-only  # no thinking behavior  
```





Requirements: Python 3.8+, `requests`. Put your API key in `config.json` (`"api_key"`) or `api_key.txt`. `config.json` overrides defaults in `utils/config.py`.

## Experiment Guide: With vs Without Thinking
- **With thinking (default)**: run `python3 main.py`. The controller decides when to show thinking. Tweak `thinking_config.json` to adjust pace (`pause_seconds`, `min/max_duration_seconds`, `max_cues`) and scripted behaviors (`behaviors` with `gesture`/`expression`/`look_at`/`utterance`).
- **Without thinking cues (replay)**: run `python3 main.py --replay-only`. Answers come from `my_trials.json`; thinking cues/behaviors are ignored. If no record matches, the bot says it has no stored answer and asks for a prepared question.
- **Direct-response delay**: add `"direct_response_delay_seconds": 1.0` (example) in `thinking_config.json` to pause before speaking when no thinking window is shown.

## `my_trials.json` (Recorded Answers)
- Structure: list of objects with `question`, `answer`, optional `thinking_cues`, `decision`, `final_confidence`.
- Matching is fuzzy (0.6); similar wording maps to the same stored answer.
- Example entry:
  ```json
  {
    "question": "What is your name?",
    "answer": "I'm Elizabeth. Do you have another question?",
    "thinking_cues": ["Recalling my name", "Preparing a short reply"],
    "decision": {"need_thinking": false, "confidence": "medium"}
  }
  ```

## Key Configs
| Setting | File | Notes |
| --- | --- | --- |
| API/base/model temps | `config.json` or `api_key.txt` | Overrides `utils/config.py` defaults. |
| Controller prompt | `plan/prompts.py` (`CONTROLLER_SYSTEM_PROMPT`) | Emits strict JSON (no LED). |
| Thinking/answer prompts | `plan/prompts.py` (`THINKING_SYSTEM_PROMPT`, `REASONING_SYSTEM_PROMPT`) | Keep thinking short; answers concise. |
| Thinking behavior script | `thinking_config.json` | `behaviors` array; omit LED fields; can add `look_at` and `utterance`. |
| Direct answer delay | `thinking_config.json` (`direct_response_delay_seconds`) | Delay before immediate replies. |
| Replay only | `--replay-only` flag | Uses `my_trials.json`; skips stored thinking cues. |

## Notes on Input Handling
- ASR runs continuously, but input is ignored while the robot is speaking (prevents cancels). Once speech ends, new user input is processed.
- If you need to allow barge-in, re-enable handling in `connection/furhat_bridge.py` (`on_hear_start`/`on_hear_end`) and adjust `stop_robot_start`.

