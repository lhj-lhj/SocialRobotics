# Visible Thinking Furhat Prototype

This project demonstrates a **controller → thinking stream → final answer** pipeline that lets a Furhat robot expose lightweight “thinking” cues before speaking, while also mapping confidence levels to verbal and nonverbal behaviors. All logic lives in `main.py`.

## Architecture

1. **Controller Model (`ControllerModel`)**  
   - A lightweight ChatGPT call produces strict JSON describing whether visible thinking is required, the confidence tier, 2‑4 short “thought snippets,” an optional reasoning hint, and (when no thinking is needed) the final answer.  
   - Offloading this decision keeps interactions snappy—simple questions bypass the thinking layer, complex ones get richer behaviors.

2. **Thinking Model (`ChatGPTSentenceStreamer`)**  
   - When the controller asks for visible thinking, we build a prompt using the user question plus those thought snippets.  
   - The model streams 2‑4 short phrases (≤12 words) that imitate human deliberation; you can later replace the `cprint` output with Furhat speech/gestures.

3. **Reasoning Model (`ChatGPTSentenceStreamer`)**  
   - A second stream delivers the actual answer. As soon as the first clause arrives we stop the thinking stream, look up the confidence → behavior mapping, and continue printing the answer with the appropriate prefix/gesture metadata.

4. **Output & Encoding**  
   - `cprint` normalizes UTF‑8 output so Windows/WSL terminals behave.  
   - If the controller already gave a final answer, the orchestrator skips the thinking stage entirely and immediately emits the answer plus gestures.

## Running the Prototype

1. Requirements: Python 3.8+ and `requests` (`pip install requests` if needed).  
2. Provide your OpenAI key in either `config.json` or `api_key.txt` at the repo root:  
   - Editing `config.json` is recommended—set the `"api_key"` value to your `sk-...` key (other fields are optional overrides).  
   - Alternatively, place the key on the first non-comment line of `api_key.txt`. If both files contain keys, `config.json` wins.  
   - Both files are listed in `.gitignore`, so secrets stay local.  
3. Run:
   ```bash
   python3 main.py
   ```
   Ask any question and you’ll see Furhat spend ~10 seconds speaking short thinking cues (with gestures) before handing over to the final answer stream whenever the controller requests visible thinking.

## Key Configuration Points

| Setting | Location | Notes |
| --- | --- | --- |
| `OPENAI_SETTINGS` | `main.py:24` | Runtime values are overridden by `config.json` / `api_key.txt`. |
| `CONTROLLER_SYSTEM_PROMPT` | `main.py:43` | Forces the controller model to emit clean JSON decisions. |
| `THINKING_SYSTEM_PROMPT` | `plan/prompts.py` | Constrains the visible-thinking stream to short, natural phrases. |
| `REASONING_SYSTEM_PROMPT` | `plan/prompts.py` | Keeps final answers short, friendly, and rationale-free. |
| `CONFIDENCE_BEHAVIORS` | `plan/behavior_generator.py` | Maps confidence tiers to speech prefixes and gesture placeholders. |
| `MAX_THINKING_CUES` | `plan/orchestrator.py` | Upper bound on visible-thinking phrases (prevents endless “...” tokens). |

## Customization Ideas

- **Hook into the actual Furhat SDK** by swapping `cprint` inside `_relay_thinking`, `_relay_answer`, and `_respond_directly` with TTS/gesture/motor commands.  
- **Use different models per stage** by editing `controller_model`, `thinking_model`, and `reasoning_model` in `config.json`—they don’t need to be the same endpoint.  
- **Extend controller policy** by adding new JSON fields (e.g., scenario tags) and parsing them inside `ControllerModel.decide()`.  
- **Improve confidence estimation** with model logprobs or external scorers; the current fallback is purely length-based.

## Troubleshooting

- **“Configuration error: API key not found”** → No key detected in either file; double-check spelling and JSON syntax.  
- **Controller returns invalid JSON** → Prompt may have been edited; tighten `CONTROLLER_SYSTEM_PROMPT` or add more robust parsing.  
- **Thinking never triggers (or always triggers)** → Adjust the controller temperature/prompt to bias when `need_thinking` flips.  
- **Windows terminal shows garbled text** → The script already forces UTF‑8, but you can also run PowerShell/WSL or execute `chcp 65001`.

## Project Structure

```
Social Robotics/
├── main.py                # Controller + thinking + reasoning pipeline
├── config.json            # Local settings (ignored by git)
├── api_key.txt            # Optional plain-text key (ignored by git)
├── realtime-api-examples/ # OpenAI samples (unchanged)
└── README.md
```

Feel free to extend this prototype for user studies. You can log the controller JSON, thinking cues, and final answers inside `Orchestrator` if you need structured datasets for downstream analysis.



Furhat表情大全（用于找到可能与thinking behaviour相关的表情）：
When your robot is running, you can go to http://<ROBOT_IP>:9000/ where you will find a playground. Here, you can test out the different requests you can send using the websocket API. This lets you easily test and understand what the different methods do.
If you want to access the same playground but use it for your virtual furhat, you go to http://192.168.1.110:9000/.



Furhat API：
https://docs.furhat.io/realtime-api/intro