"""SQL 审计节点。

这个文件定义只读 SQL 审计 ToolNode，用来在执行前拦截写操作、多语句和明显危险关键字。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from graph.nodes.base import ToolNode


class AuditSQLNode(ToolNode):
    """检查 SQL 是否安全可执行的工具节点。"""

    name = "audit_sql"
    title = "审计 SQL"
    description = "检查 SQL 是否只读、安全且没有多语句风险。"
    dangerous_patterns = [
        r"\binsert\b",
        r"\bupdate\b",
        r"\bdelete\b",
        r"\bdrop\b",
        r"\balter\b",
        r"\btruncate\b",
        r"\bcreate\b",
        r"\breplace\b",
        r"\bgrant\b",
        r"\brevoke\b",
        r"\bcall\b",
        r"\bexec\b",
        r"\bexecute\b",
        r"\bload_file\b",
        r"\boutfile\b",
        r"\bdumpfile\b",
    ]

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """审计当前 SQL，并决定通过还是打回 SQL 工程师。

        输入:
            state: 当前图状态；需要包含 `sql`，可选包含 `sql_attempts` 和 `max_sql_attempts`。
        输出:
            包含 `audit_passed` 和 `audit_message` 的状态更新；如果超过最大重试次数则抛出异常。
        """
        audit_result = self.audit(state["sql"])
        if not audit_result["passed"]:
            max_attempts = int(state.get("max_sql_attempts") or 3)
            attempts = int(state.get("sql_attempts") or 0)
            if attempts >= max_attempts:
                raise ValueError(f"SQL 审计在 {attempts} 次尝试后仍未通过：{audit_result['message']}")
            return {
                "audit_passed": False,
                "audit_message": str(audit_result["message"]),
            }
        return {
            "audit_passed": True,
            "audit_message": str(audit_result["message"]),
        }

    def audit(self, sql: str) -> Dict[str, object]:
        """执行静态 SQL 安全检查。

        输入:
            sql: 待检查的 SQL 字符串。
        输出:
            包含 `passed` 布尔值和 `message` 文本的审计结果。
        """
        cleaned = (sql or "").strip()
        lowered = cleaned.lower()

        if not cleaned:
            return {"passed": False, "message": "SQL 为空"}

        if not (lowered.startswith("select") or lowered.startswith("with")):
            return {"passed": False, "message": "只允许 SELECT / WITH 查询"}

        without_tail_semicolon = cleaned[:-1] if cleaned.endswith(";") else cleaned
        if ";" in without_tail_semicolon:
            return {"passed": False, "message": "不允许一次执行多条 SQL"}

        for pattern in self.dangerous_patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return {"passed": False, "message": f"检测到危险关键字：{pattern}"}

        return {
            "passed": True,
            "message": "SQL 审计通过：查询只读，未发现明显危险关键字。",
        }

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成任务步骤中展示的 SQL 审计摘要。

        输入:
            output: `run` 返回的状态更新。
        输出:
            人类可读的审计摘要。
        """
        return output.get("audit_message") or "SQL 审计通过。"
