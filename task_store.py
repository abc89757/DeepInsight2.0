from __future__ import annotations

from typing import Any, Dict


# 过渡期内存任务表。task_runner 仍然写这里，系统库负责持久化历史任务。
TASK_STORE: Dict[str, Dict[str, Any]] = {}
