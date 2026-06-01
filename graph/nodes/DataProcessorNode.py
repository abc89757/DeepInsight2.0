"""数据处理师节点。

这个文件定义 DataProcessorNode，用来把查询结果预览和 artifact 信息整理成可供分析的自然语言数据情况。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps
from services.task_tool_registry import get_task_tools


class ProcessorActionInput(BaseModel):
    """数据处理师给出的路由决策。"""

    action: str = Field(description="只能填写：需要数据 或 开始分析。其他内容会默认按 开始分析 处理。")


class DataProcessorNode(AgentNode):
    """负责把查询结果转成证据结果、具体数据情况和数据缺陷说明的 AgentNode。"""

    name = "data_processor"
    title = "数据处理师"
    description = "根据查询结果生成数据情况、证据结果和数据缺陷说明。"
    system_prompt = """
你是数据处理师。你负责根据证据规划和计算规则判断本轮指标是否已有足够数据可以计算。
如果当前还没有查询结果或数据文件，不要调用依赖文件路径、CSV 或查询结果的工具，不要编造数据；请说明还需要哪些数据，并选择“需要数据”。
如果当前已经有查询结果，再把查询结果整理成可供分析师理解的数据情况和证据结果。
重点不是写最终结论，而是把具体数据情况、证据/指标处理方法、处理结果和初步含义说清楚。
如果发现数据层问题，例如字段缺失、结果为空、结果被截断、口径无法满足、样本量不足、异常值明显，也要明确写出来。

请用自然语言输出，建议使用这些小标题：
【数据情况】说明返回了多少行、哪些字段、字段值大致长什么样、数据是否是聚合结果或明细结果。
【证据结果】说明本轮选取的指标、特征、明细筛选或规则命中结果，以及这些结果的具体数值或分布情况。
【初步含义】说明这些数据结果对本轮目标有什么初步含义，但不要替洞察分析师写最终结论。
【数据缺陷】如果有数据层问题必须写清楚；如果没有明显问题，写“暂未发现明显数据层缺陷”。
""".strip()
    temperature = 0.1
    use_stream = True

    def __init__(self) -> None:
        super().__init__()
        self.processor_action = "metrics_ready"

    def choose_processor_action(self, action: str) -> Dict[str, str]:
        """记录本次 DataProcessor 执行的路由决策。"""
        normalized = (action or "").strip()
        if normalized == "\u9700\u8981\u6570\u636e":
            self.processor_action = "need_sql_data"
        elif normalized == "\u5f00\u59cb\u5206\u6790":
            self.processor_action = "metrics_ready"
        else:
            self.processor_action = "metrics_ready"
        return {
            "processor_action": self.processor_action,
            "message": "已记录 DataProcessor 下一步决策。",
        }

    def build_decision_tool(self) -> StructuredTool:
        """创建供模型选择下一步动作的小工具。"""
        return StructuredTool.from_function(
            func=self.choose_processor_action,
            name="choose_processor_action",
            description=(
                "选择 DataProcessor 下一步动作。"
                "如果还需要数据库取数，action 传入：需要数据。"
                "如果指标已经可以交给分析师，action 传入：开始分析。"
            ),
            args_schema=ProcessorActionInput,
        )

    def extract_data_issue(self, message: str) -> str:
        """从数据处理师输出中提取“数据缺陷”段落。

        输入:
            message: 数据处理师输出文本。

        输出:
            数据缺陷说明；如果没有找到专门段落，则返回空字符串。
        """
        marker = "【数据缺陷】"
        if marker not in message:
            return ""
        return message.split(marker, 1)[1].strip()

    def append_agent_message(self, state: Dict[str, Any], message: str) -> list[Dict[str, Any]]:
        """把数据处理师输出追加到调试用对话历史中。

        输入:
            state: 当前图状态。
            message: 数据处理师输出文本。

        输出:
            追加后的 `agent_messages` 列表。
        """
        messages = list(state.get("agent_messages", []))
        messages.append(
            {
                "round": int(state.get("analysis_round") or 0),
                "agent": self.name,
                "content": message,
            }
        )
        return messages

    def has_query_result(self, state: Dict[str, Any]) -> bool:
        """判断当前 state 是否已经有可供处理的查询结果。"""
        return bool(
            state.get("result_path")
            or state.get("result_preview")
            or state.get("query_artifacts")
            or state.get("result_columns")
        )

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """决定本轮继续取数，还是完成指标处理并进入分析。"""
        self.processor_action = "metrics_ready"
        skill_tools = get_task_tools(
            str(state.get("task_id")) if state.get("task_id") else None,
            "data_processor",
        )
        self.tools = [self.build_decision_tool(), *skill_tools]

        prompt = self.build_prompt(state)
        if skill_tools:
            if self.has_query_result(state):
                prompt = (
                    "当前已有查询结果，Skill 提供的数据处理工具可在需要时辅助处理这些结果。"
                    "在最终回答前必须调用 choose_processor_action 选择下一步。\n\n"
                    + prompt
                )
            else:
                prompt = (
                    "当前还没有查询结果或数据文件。不要调用依赖文件路径、CSV 或查询结果的 Skill 工具；"
                    "请先判断需要哪些数据，并在最终回答前调用 choose_processor_action 选择下一步。\n\n"
                    + prompt
                )

        raw_output = self.call_llm(prompt, state)
        self.save_raw_llm_output(state, raw_output)
        data_message = (raw_output or "").strip()
        if not data_message:
            raise ValueError("DataProcessorNode 没有返回有效内容。")

        action = self.processor_action or "metrics_ready"
        attempts = int(state.get("data_request_attempts") or 0)
        max_attempts = int(state.get("max_data_request_attempts") or 3)
        data_issue = self.extract_data_issue(data_message)

        if action == "need_sql_data" and attempts >= max_attempts:
            action = "metrics_ready"
            limit_issue = f"已达到最大取数轮次 {max_attempts}，将基于现有数据进入分析。"
            data_issue = f"{data_issue}\n\n{limit_issue}".strip()

        processed = {
            "message": data_message,
            "data_issue": data_issue,
            "artifact_path": state.get("result_path"),
            "row_count": state.get("result_row_count", 0),
            "columns": state.get("result_columns", []),
            "processor_action": action,
        }

        output: Dict[str, Any] = {
            "processor_action": action,
            "data_message": data_message,
            "current_processed_data": processed,
            "current_data_issue": data_issue,
            "agent_messages": self.append_agent_message(state, data_message),
        }

        if action == "need_sql_data":
            output.update(
                {
                    "current_data_request": data_message,
                    "data_request_attempts": attempts + 1,
                    "sql_attempts": 0,
                    "audit_passed": False,
                    "audit_message": "",
                }
            )
        else:
            output["current_metric_result"] = processed

        return output

    def build_query_context(self, state: Dict[str, Any]) -> str:
        """构造已有查询结果上下文；没有结果时不暴露空文件/空字段信息。"""
        if not self.has_query_result(state):
            return "当前还没有可用的查询结果或数据文件。不要调用依赖文件路径、CSV 或查询结果的工具；请先根据指标计划判断是否需要向 SQL 节点申请取数。"

        return f"""
最近一次查询字段：
{json_dumps(state.get("result_columns", []))}

最近一次查询行数：
{state.get("result_row_count", 0)}

最近一次查询是否截断：
{state.get("result_truncated", False)}

最近一次查询预览：
{json_dumps(state.get("result_preview", []))}

最近一次查询结果文件：
{state.get("result_path")}

所有查询产物：
{json_dumps(state.get("query_artifacts", []))}
""".strip()

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造用于判断取数或完成指标处理的 prompt。"""
        query_context = self.build_query_context(state)
        return f"""
用户问题：
{state.get("question", "")}

本轮分析目标：
{state.get("analysis_goal", "")}

EvidencePlanner 给出的指标/证据计划：
{state.get("evidence_message") or json_dumps(state.get("current_evidence_plan", {}))}

当前取数轮次：
{state.get("data_request_attempts", 0)} / {state.get("max_data_request_attempts", 3)}

数据上下文：
{query_context}

要求：
1. 如果当前指标计划还缺少计算所需数据，请说明需要 SQL 节点继续抽取哪些数据。
2. 如果现有数据已经足够，请完成指标计算或指标结果总结，并说明数据限制。
3. 在最终回答前，必须调用 choose_processor_action，action 只能传入“需要数据”或“开始分析”。
4. 如果选择“需要数据”，最终回答必须写清楚请求的指标、字段、过滤条件、粒度，以及表/列线索。
5. 如果选择“开始分析”，最终回答必须写清楚指标结果、证据依据和数据问题。
""".strip()

    def build_system_prompt(self, state: Dict[str, Any]) -> str:
        """构造数据处理师的 system prompt，只注入计算规则。"""
        skill = state.get("skill") or {}
        return f"""
{self.system_prompt}

计算规则：
{skill.get("calculations", "")}
""".strip()

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成用于任务步骤日志的数据处理摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        return output.get("data_message", "") or "数据处理完成。"
