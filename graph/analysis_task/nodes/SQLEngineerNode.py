"""SQL 工程师节点。

这个文件定义 SQLEngineerNode，用来根据证据规划和数据库 Schema 生成只读 SQL。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from graph.common.base import AgentNode
from graph.common.utils import json_dumps, split_think_content


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
    system_prompt = """
你是严谨的 MySQL SQL 工程师。你只输出 SQL，不输出解释。
请根据证据规划和数据库 Schema 生成一条可执行的 MySQL SELECT SQL。

要求：
1. 只能生成 SELECT 或 WITH ... SELECT 查询。
2. 不允许 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE、REPLACE、LOAD DATA、SELECT ... INTO OUTFILE、CALL、SET、GRANT、REVOKE 等写操作或高风险操作。
3. 尽量使用 Schema 中真实存在的表、字段和连接关系，不要臆造表名、字段名、外键或业务字段。
4. 多表查询必须写清 JOIN 条件，不允许无条件 CROSS JOIN。
5. 默认优先使用 INNER JOIN 和 LEFT JOIN；MySQL 不支持原生 FULL OUTER JOIN，不要生成。
6. 如果需要中间结果，优先使用 CTE 或派生表，不要创建临时表。
7. 如果需要聚合，请在 SQL 中完成基础聚合。
8. 使用 GROUP BY 时，SELECT 中的非聚合字段必须出现在 GROUP BY 中，默认遵守 ONLY_FULL_GROUP_BY 兼容写法。
9. 占比、比率、均值类指标必须保留分子和分母。
10. 分母可能为 0 时，必须使用 NULLIF(分母, 0) 避免除零。
11. 金额、比率等需要展示的小数结果，可以使用 ROUND(x, 2) 保留两位小数。
12. 明细查询默认加 LIMIT 100，除非用户明确要求完整导出。
13. 排名查询必须使用 ORDER BY 和 LIMIT。
14. 查询大表时必须尽量加入时间范围或明确过滤条件。
15. 不要 SELECT *，只选择证据规划所需字段。
16. 排序、分组、连接字段应优先使用索引字段。
17. 避免多层深度嵌套 SQL。
18. 避免在大表中使用 ORDER BY RAND()。
19. 生成 SQL 时不要直接拼接用户输入，应假设执行层会做参数绑定。
20. 必须严格兼容 MySQL 8.0+ 语法，可以使用 MySQL 8 支持的 CTE 和窗口函数。
21. 不要使用 PostgreSQL、Oracle、SQL Server、Hive、Spark SQL 等其他数据库方言。
22. 禁止使用 MySQL 不支持的中位数、百分位函数或语法，例如 PERCENTILE_CONT、PERCENTILE_DISC、WITHIN GROUP、APPROX_PERCENTILE、MEDIAN()、QUALIFY。
23. 如果需要计算中位数，请使用 MySQL 8 窗口函数 ROW_NUMBER() OVER (...) 和 COUNT(*) OVER (...)，选取中间行后 AVG() 得到中位数。
24. 不要使用 FILTER (WHERE ...)、:: 类型转换、DATE_TRUNC、ILIKE、TOP、ROWNUM 等非 MySQL 写法。
25. 时间筛选优先使用范围条件，例如：
    time_col >= '2026-05-01'
    AND time_col < '2026-06-01'
    不要优先写成 DATE(time_col) = '2026-05-01'。
26. 可以使用 MySQL 常用函数，包括：
    SUM、COUNT、COUNT DISTINCT、AVG、MIN、MAX、
    CASE WHEN、IF、COALESCE、IFNULL、NULLIF、
    DATE、DATE_FORMAT、YEAR、MONTH、DAY、WEEK、CURDATE、NOW、DATEDIFF、TIMESTAMPDIFF、DATE_ADD、DATE_SUB、
    ROW_NUMBER、RANK、DENSE_RANK、LAG、LEAD、SUM OVER、AVG OVER、
    TRIM、LOWER、UPPER、CONCAT、SUBSTRING、LEFT、RIGHT、REPLACE、LENGTH、CHAR_LENGTH、
    ROUND、FLOOR、CEIL、ABS、GREATEST、LEAST。
27. 不要在大表 WHERE 条件中频繁对索引列使用函数，例如 DATE(time_col)、TRIM(index_col)、LOWER(index_col) 等。
28. 返回结果应服务于证据规划。
29. 如果 Schema 或证据规划不足以确定字段、表或统计口径，不要臆造 SQL，只输出：需要补充字段或口径
30. 除非出现第 29 条情况，否则只输出 SQL，不要 Markdown，不要解释。
""".strip()
    temperature = 0.1
    use_stream = True
    timeout = 300

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成 SQL，并递增 SQL 尝试次数。

        输入:
            state: 当前图状态；需要包含 `question`、`schema_info` 和
                `current_evidence_plan`，也可能包含上一次 SQL 审计失败后的
                `audit_message`。

        输出:
            包含 `sql` 和递增后 `sql_attempts` 的状态更新。
        """
        raw_sql = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_sql, label="raw_sql")
        sql_body, _ = split_think_content(raw_sql)
        sql = _clean_sql(sql_body)
        if not sql:
            raise ValueError("SQL 工程师没有生成有效 SQL。")
        return {
            "sql": sql,
            "sql_attempts": int(state.get("sql_attempts") or 0) + 1,
        }

    def _legacy_build_prompt(self, state: Dict[str, Any]) -> str:
        """构造 SQL 生成 prompt。

        输入:
            state: 当前图状态；包含证据规划、数据库 Schema、Skill 计算规则，
                以及可选的 SQL 审计反馈。

        输出:
            要求模型只输出 MySQL SELECT/WITH SQL 的 prompt 字符串。
        """
        audit_message = state.get("audit_message")
        retry_hint = f"\n上一次 SQL 审计失败原因：{audit_message}\n请修复后重新生成。" if audit_message else ""
        return f"""
用户问题：
{state["question"]}

本轮分析目标：
{state.get("analysis_goal", "")}

证据规划：
{state.get("evidence_message") or json_dumps(state.get("current_evidence_plan", {}))}

数据库 Schema：
{state.get("schema_info", "")}

{retry_hint}

SQL：
""".strip()

    def _legacy_build_system_prompt(self, state: Dict[str, Any]) -> str:
        """构造 SQL 工程师的 system prompt，并加入 Skill 计算规则。

        输入:
            state: 当前图状态；包含已加载 Skill。

        输出:
            角色规则、SQL 约束和 Skill 计算规则组成的 system prompt。
        """
        skill = state.get("skill") or {}
        return f"""
{self.system_prompt}

Skill 计算规则：
{skill.get("calculations", "")}
""".strip()

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """根据 DataProcessor 的取数申请构造 SQL prompt。"""
        audit_message = state.get("audit_message")
        retry_hint = ""
        if audit_message:
            retry_hint = f"\n上一次 SQL 审计失败原因：\n{audit_message}\n请修复后重新生成 SQL。\n"

        data_request = state.get("current_data_request") or state.get("data_message") or state.get("evidence_message")
        return f"""
用户问题：
{state["question"]}

本轮分析目标：
{state.get("analysis_goal", "")}

DataProcessor 提出的取数申请：
{data_request or json_dumps(state.get("current_evidence_plan", {}))}

数据库 Schema：
{state.get("schema_info", "")}

{retry_hint}

SQL:
""".strip()

    def build_system_prompt(self, state: Dict[str, Any]) -> str:
        """直接使用 SQL 通用约束，不再读取业务 Skill。"""
        return self.system_prompt

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成用于任务步骤日志的 SQL 生成摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        sql = (output.get("sql") or "").strip()
        message = f"SQL 生成完成，尝试次数 {output.get('sql_attempts')}。"
        return f"{sql}\n\n{message}".strip() if sql else message

    def step_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """Persist the SQL generated in this step for per-step display."""
        return {
            "sql": output.get("sql"),
            "sql_attempts": output.get("sql_attempts"),
        }
