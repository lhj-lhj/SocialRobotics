# Project Structure

## Modular Layout

The project follows a modular layout with clearly separated responsibilities:

```
SocialRobotics/
├── main.py                 # Entry point (enables/disables planning)
├── config.json             # Configuration
├── plan/                   # Planning module
│   ├── __init__.py
│   ├── controller.py       # 1. Confidence controller
│   ├── behavior_generator.py  # 2. Gesture + behavior generator
│   ├── orchestrator.py     # 3. Visible thinking orchestrator
│   └── prompts.py          # Prompt definitions
├── connection/             # Robot bridge for debugging
│   ├── __init__.py
│   └── furhat_bridge.py    # Furhat bridge
└── utils/                  # Shared utilities
    ├── __init__.py
    ├── config.py           # Config loader
    ├── streamer.py         # Streaming helper
    └── print_utils.py      # Printing helper
```

## Module Responsibilities

### 1. `main.py` – Entry point
- Enables or bypasses the planning module
- Handles startup logic
- Parses CLI arguments

### 2. `plan/` – Planning module
**controller.py**: 
- Determines confidence level
- Decides whether visible thinking is required
- Produces thinking notes and hints for the reasoning model

**behavior_generator.py**:
- Maps confidence into speech prefixes, gestures, and LED colors
- Issues concrete Furhat API calls
- Handles multimodal coordination

**orchestrator.py**:
- Orchestrates thinking vs. answering
- Coordinates controller, thinking, and reasoning models
- Manages visible-thinking windows

**prompts.py**:
- Stores all system prompts and builders

### 3. `connection/` – Connection module
**furhat_bridge.py**:
- Maintains the Furhat websocket connection
- Handles hear/speak/partial events
- Passes user text to the planner
- Provides debugging hooks

### 4. `utils/` – Utilities
**config.py**: 
- Loads configuration with priority for config.json
- Manages API keys

**streamer.py**:
- Streams sentence-level chunks from OpenAI-compatible APIs

**print_utils.py**:
- UTF-8 safe printing helper

## Usage

### Run the main program
```bash
python main.py --host 192.168.1.114 --auth_key YOUR_KEY
```

### Skip the planning module (connection-only debugging)
```bash
python main.py --no-plan --host 192.168.1.114
```

## Workflow

1. **User speaks** → `connection/furhat_bridge.py` receives ASR events  
2. **Input handling** → `plan/orchestrator.py` is invoked  
3. **Confidence control** → `plan/controller.py` decides thinking needs and tier  
4. **Behavior generation** → `plan/behavior_generator.py` converts commands to API calls  
5. **Speech/gestures** → Furhat executes the actions  
6. **Visible thinking** → `plan/orchestrator.py` manages thinking cues

## Configuration

`config.json` supports:
- `api_key`: OpenAI API key
- `base_url`: API base URL
- `controller_model`: controller model id
- `reasoning_model`: reasoning model id
- `thinking_model`: thinking model id
- Temperature settings for each model

