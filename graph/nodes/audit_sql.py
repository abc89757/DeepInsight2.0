from __future__ import annotations

import re
from typing import Any, Dict, Optional

from graph.nodes.base import ToolNode


class AuditSQLNode(ToolNode):
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
        audit_result = self.audit(state["sql"])
        if not audit_result["passed"]:
            raise ValueError(f"SQL 审计失败：{audit_result['message']}")
        return {
            "audit_passed": True,
            "audit_message": audit_result["message"],
        }

    def audit(self, sql: str) -> Dict[str, object]:
        cleaned = sql.strip()
        lowered = cleaned.lower()

        if not cleaned:
            return {"passed": False, "message": "SQL 为空"}

        if not (lowered.startswith("select") or lowered.startswith("with")):
            return {"passed": False, "message": "当前版本只允许 SELECT / WITH 查询"}

        without_tail_semicolon = cleaned[:-1] if cleaned.endswith(";") else cleaned
        if ";" in without_tail_semicolon:
            return {"passed": False, "message": "检测到多条 SQL 语句，已拒绝执行"}

        for pattern in self.dangerous_patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return {"passed": False, "message": f"检测到危险关键字：{pattern}"}

        return {
            "passed": True,
            "message": "SQL 审计通过：只读查询，未发现明显危险关键字",
        }

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        return output.get("audit_message") or "SQL 审计通过。"
