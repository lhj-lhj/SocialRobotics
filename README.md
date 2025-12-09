# Furhat Visible Thinking: Code Map & Usage

This repository runs a two-stage pipeline for the Furhat robot:
- **Controller** decides whether to show visible thinking, suggests short thinking notes, confidence, and (optionally) a final answer.
- **Thinking stream** emits short cues/behaviors while “thinking”.
- **Reasoning stream** outputs the final answer and post-answer prompt (“Do you have another question?”).
- **Replay-only** mode can serve stored answers from `my_trials.json` without calling models; stored thinking cues are skipped by default.

## Code Structure (where things live)
- `main.py` — entry point; CLI flags (`--replay-only`, `--test`), spins up the Furhat bridge.
- `connection/furhat_bridge.py` — connects to Furhat, handles ASR/speech events, suppresses input while the robot speaks.
- `plan/orchestrator.py` — coordinates controller → thinking stream → final answer; optional replay-only and direct-response delay.
- `plan/controller.py` — calls LLM with `CONTROLLER_SYSTEM_PROMPT` (see `plan/prompts.py`); parses JSON decision.
- `plan/prompts.py` — system prompts and prompt builders.
- `plan/behavior_generator.py` — maps confidence to gesture/expression (LED removed), handles optional `look_at` and `utterance` during thinking.
- `plan/thinking_config.py` / `thinking_config.json` — timing and scripted thinking behaviors (no LED fields).
- `utils/trial_memory.py` — loads `my_trials.json`, fuzzy matches questions (threshold 0.6), returns stored answers.
- `my_trials.json` — your recorded QA pairs (see format below).

## Run
```bash
python3 main.py                 # normal: controller + thinking + reasoning
python3 main.py --replay-only   # prefer answers from my_trials.json; if no close match, fall back to models
python3 main.py --test          # local test without Furhat
```

Prereqs: Python 3.8+, `requests`. Put API key in `config.json` (`"api_key"`) or `api_key.txt` (root). `config.json` overrides defaults in `utils/config.py`.

## Config Quick Reference
- `config.json` — API key, base URL, model names/temps for controller/thinking/reasoning.
- `thinking_config.json` — `min/max_duration_seconds`, `pause_seconds`, `max_cues`, `direct_response_delay_seconds`, and `behaviors` (array of `{gesture, expression, look_at?, utterance?}`).
- `plan/prompts.py` — edit prompts if you need to change tone/format.
- LEDs are fully removed; ignore any `led` fields.

## `my_trials.json` Format (for replay)
List of objects:
```json
{
  "question": "What is your name?",
  "answer": "I'm Elizabeth. Do you have another question?",
  "thinking_cues": ["Recalling my name", "Preparing a short reply"],
  "decision": {"need_thinking": false, "confidence": "medium"},
  "final_confidence": "medium"
}
```
Matching is fuzzy (0.6), so paraphrased questions hit the same answer. In `--replay-only`, thinking cues are ignored by default.

## Experiment Guide
### A) With visible thinking (default)
1. Run `python3 main.py`.
2. Tweak `thinking_config.json` to set pace (`pause_seconds`, `min/max_duration_seconds`, `max_cues`).
3. Add behaviors if desired:
   ```json
   { "gesture": "look straight", "expression": "Thoughtful", "utterance": "Let me think..." },
   { "gesture": "nod head", "expression": "Thoughtful", "look_at": { "x": 0.2, "y": 0.0, "z": 1.0 } }
   ```
4. Optional: set `"direct_response_delay_seconds": 1.0` to delay immediate answers when no thinking is needed.

### B) Without thinking cues (replay answers)
1. Populate `my_trials.json` with your QA pairs.
2. Run `python3 main.py --replay-only`.
3. If no match is found, the robot says it has no stored answer and asks for a prepared question.
4. To bypass trials entirely and force model calls, run `python3 main.py --no-trials`.

## Notes on ASR / Interruptions
- ASR keeps running, but while the robot speaks we ignore incoming audio (`robot_speaking` guard). After speech ends, user input is processed.
- If you need barge-in, adjust `connection/furhat_bridge.py` to handle input during speech and/or change `stop_robot_start` back to `True`.

## Recent Changes
- LEDs removed entirely.
- Replay-only path with fuzzy matching.
- Direct-response delay option.
- Continuous invitation (“Do you have another question?”) instead of 5-question cap.
- ASR ignores input while speaking to avoid cancels.
