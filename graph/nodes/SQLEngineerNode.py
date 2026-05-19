"""SQL 工程师节点。

这个文件定义 SQLEngineerNode，用来根据证据规划和数据库 Schema 生成只读 SQL。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps


def _clean_sql(raw_sql: str) -> str:
    """清理模型返回的 SQL 文本。

    输入:
        raw_sql: 模型原始输出；可能包含 Markdown 代码块、前缀说明或多条语句。

    输出:
        清理后的单条 SQL；如果文本非空，会尽量保证以分号结尾。
    """
    text = (raw_sql or "").strip()
    code_match = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()

    text = re.sub(r"^\s*(SQL|sql|查询SQL|生成SQL)\s*[:：]\s*", "", text).strip()
    if ";" in text:
        first, *_ = text.split(";")
        text = first.strip() + ";"
    if text and not text.endswith(";"):
        text += ";"
    return text


class SQLEngineerNode(AgentNode):
    """负责根据证据规划生成只读 SQL 的 AgentNode。"""

    name = "sql_engineer"
    title = "SQL 工程师"
    description = "根据证据规划生成只读 SQL 查询。"
    system_prompt = "你是严谨的 MySQL SQL 工程师。你只输出 SQL，不输出解释。"
    temperature = 0.1
    timeout = 300

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成 SQL，并递增 SQL 尝试次数。

        输入:
            state: 当前图状态；需要包含 `question`、`schema_info` 和
                `current_evidence_plan`，也可能包含上一次 SQL 审计失败后的
                `audit_message`。

        输出:
            包含 `sql`、`current_sql` 和递增后 `sql_attempts` 的状态更新。
        """
        raw_sql = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_sql, label="raw_sql")
        sql = _clean_sql(raw_sql)
        if not sql:
            raise ValueError("SQL 工程师没有生成有效 SQL。")
        return {
            "sql": sql,
            "current_sql": sql,
            "sql_attempts": int(state.get("sql_attempts") or 0) + 1,
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造 SQL 生成 prompt。

        输入:
            state: 当前图状态；包含证据规划、数据库 Schema、Skill 计算规则，
                以及可选的 SQL 审计反馈。

        输出:
            要求模型只输出 MySQL SELECT/WITH SQL 的 prompt 字符串。
        """
        skill = state.get("skill") or {}
        audit_message = state.get("audit_message")
        retry_hint = f"\n上一次 SQL 审计失败原因：{audit_message}\n请修复后重新生成。" if audit_message else ""
        return f"""
请根据证据规划和数据库 Schema 生成一条可执行的 MySQL SELECT SQL。
要求：
1. 只能生成 SELECT 或 WITH 查询。
2. 不允许 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE 等写操作。
3. 尽量使用 Schema 中真实存在的表和字段。
4. 如果需要聚合，请在 SQL 中完成基础聚合。
5. 返回结果应服务于 evidence_plan 的 expected_result_shape。
6. 必须严格兼容 MySQL 8 语法，不要使用 PostgreSQL、Oracle、SQL Server、Hive 或 Spark SQL 方言。
7. 禁止使用 MySQL 不支持的中位数/百分位函数或语法，例如 PERCENTILE_CONT、PERCENTILE_DISC、WITHIN GROUP、APPROX_PERCENTILE、MEDIAN()、QUALIFY。
8. 如果需要计算中位数，请使用 MySQL 8 窗口函数 ROW_NUMBER() OVER (...) 和 COUNT(*) OVER (...)，选取中间行后 AVG() 得到中位数。
9. 不要使用 FILTER (WHERE ...)、:: 类型转换、DATE_TRUNC、ILIKE、TOP 等非 MySQL 写法。
10. 只输出 SQL，不要 Markdown。
{retry_hint}

用户问题：
{state["question"]}

本轮分析目标：
{state.get("analysis_goal", "")}

证据规划：
{json_dumps(state.get("current_evidence_plan", {}))}

数据库 Schema：
{state.get("schema_info", "")}

Skill 计算规则：
{skill.get("calculations", "")}

SQL：
""".strip()

    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        """调用配置好的 LLM 完成 SQL 生成。

        输入:
            prompt: `build_prompt` 生成的 prompt。
            state: 当前图状态；此处主要用于保持 AgentNode 接口一致。

        输出:
            模型返回的原始 SQL 文本。
        """
        return self.llm_client.complete(
            prompt=prompt,
            system_prompt=self.system_prompt,
            temperature=self.temperature,
            tools=self.tools,
            stream=self.stream,
            timeout=self.timeout,
        )

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成用于任务步骤日志的 SQL 生成摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        return f"SQL 生成完成，尝试次数 {output.get('sql_attempts')}。"
