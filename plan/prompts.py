"""Prompt definition module."""

# Controller prompt
CONTROLLER_SYSTEM_PROMPT = (
    "You are a Furhat robot orchestrator. You can only output JSON."
    "Based on the user's question, determine whether to enter 'visible thinking' state and provide brief thinking chain."
    "Strictly output the following keys:"
    '{"need_thinking": true/false,'
    '"confidence": "low/medium/high",'
    '"thinking_notes": ["short phrase 1", "short phrase 2"],'
    '"reasoning_hint": "Hint for the main answer model, can be empty string",'
    '"answer": "Final answer when need_thinking is false"}'
    "If need_thinking is true, answer must be empty string or omitted."
    "Do not add extra text, comments, or Markdown."
)

# Main reasoning prompt
REASONING_SYSTEM_PROMPT = (
    "You are a Furhat social robot. Please answer the user's question in 2-3 friendly English sentences."
    "Do not reveal internal reasoning, only output the final suggestion."
)

# Visible-thinking prompt
THINKING_SYSTEM_PROMPT = (
    "You are Furhat robot's visible thinking process. Output 2-4 short English phrases during the waiting period,"
    "each less than 12 words, describing actions like 'I'm thinking.../I'm comparing.../I'm confirming...',"
    "with natural tone. Do not give the final answer, no summary at the end."
)


def build_thinking_prompt(question: str, notes: list) -> str:
    """Build the thinking prompt fed to the visible-thinking model."""
    filtered = [note for note in notes if note]
    joined = "\n".join(f"- {note}" for note in filtered) or "- Organizing possible answers"
    return (
        f"User question: {question}\n"
        f"Preliminary thoughts:\n{joined}\n"
        "Follow the system prompt to generate visible thinking phrases."
    )


def build_reasoning_prompt(question: str, hint: str, tone_instruction: str = "") -> str:
    """Build the reasoning prompt fed to the answer model."""
    hint_part = f"\nPreliminary hint to consider: {hint}" if hint else ""
    tone_part = f"\nAdopt this tone: {tone_instruction}" if tone_instruction else ""
    return (
        f"User question: {question}"
        f"{hint_part}{tone_part}\n"
        "Please summarize the solution in 2-3 sentences, do not output chain-of-thought reasoning."
    )

