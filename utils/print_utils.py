"""Printing helpers that handle UTF-8 output safely."""
import sys
import io

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


def cprint(text: str, end: str = "\n"):
    """Print text safely with UTF-8 fallback."""
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

