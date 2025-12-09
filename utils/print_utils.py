"""Printing helpers that handle UTF-8 output safely."""
import sys
import io
from datetime import datetime
from pathlib import Path

# Ensure the console can emit UTF-8 text
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
except Exception:
    pass


LOG_FILE_PATH = Path(__file__).resolve().parent.parent / "terminal.txt"


def _log_to_file(text: str):
    """Append timestamped text to terminal log file."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE_PATH.open("a", encoding="utf-8") as fp:
            fp.write(f"[{timestamp}] {text}\n")
    except Exception:
        # Logging must never break console output
        pass


def cprint(text: str, end: str = "\n"):
    """Print text safely with UTF-8 fallback and mirror to terminal log."""
    try:
        print(text, end=end)
        if end != "\n":
            sys.stdout.flush()
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((text + end).encode("utf-8", errors="ignore"))
            sys.stdout.flush()
        except Exception:
            pass

    # Mirror to log file with a timestamp (only when ending a line)
    if end == "\n":
        _log_to_file(text)
