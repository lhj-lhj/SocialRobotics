"""打印工具，支持中文输出"""
import sys
import io

# 确保控制台能正确输出中文
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
    """安全打印中文，支持 end 参数"""
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

