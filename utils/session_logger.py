"""简单的会话日志记录器：将调试输出写入固定文件"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# 计算项目根目录
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = ROOT_DIR / "logs"
DEFAULT_LOG_PATH = DEFAULT_LOG_DIR / "session_log.txt"


class SessionLogger:
    """负责把可视化思考 / 回答 / 行为步骤写入单个日志文件"""

    def __init__(self, log_path: Optional[str] = None, auto_reset: bool = True):
        self.log_path = Path(log_path) if log_path else DEFAULT_LOG_PATH
        self.auto_reset = auto_reset
        self._ensure_parent()
        if self.auto_reset:
            self.reset()

    def _ensure_parent(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def reset(self):
        """清空日志文件（覆盖旧内容）"""
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("")

    def log(self, label: str, message: str):
        """写入一条带时间戳的日志"""
        timestamp = datetime.now().isoformat(timespec="seconds")
        entry = f"[{timestamp}] {label}: {message}\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(entry)

    def log_block(self, label: str, block: str):
        """写入多行内容，方便保存 JSON 或分段文本"""
        timestamp = datetime.now().isoformat(timespec="seconds")
        header = f"[{timestamp}] {label}:\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(header)
            f.write(block.rstrip() + "\n")



