"""数据处理师节点。

这个文件定义 DataProcessorNode，用来把查询结果预览和 artifact 信息整理成可供分析的自然语言数据情况。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps
from services.task_tool_registry import get_task_tools


class DataProcessorNode(AgentNode):
    """负责把查询结果转成证据结果、具体数据情况和数据缺陷说明的 AgentNode。"""

    name = "data_processor"
    title = "数据处理师"
    description = "根据查询结果生成数据情况、证据结果和数据缺陷说明。"
    system_prompt = """
你是数据处理师。你负责把查询结果整理成可供分析师理解的数据情况和证据结果。
请根据证据方案和查询结果预览，完成本轮数据处理。
重点不是写最终结论，而是把具体数据情况、证据/指标处理方法、处理结果和初步含义说清楚。
如果发现数据层问题，例如字段缺失、结果为空、结果被截断、口径无法满足、样本量不足、异常值明显，也要明确写出来。

请用自然语言输出，建议使用这些小标题：
【数据情况】说明返回了多少行、哪些字段、字段值大致长什么样、数据是否是聚合结果或明细结果。
【证据结果】说明本轮选取的指标、特征、明细筛选或规则命中结果，以及这些结果的具体数值或分布情况。
【初步含义】说明这些数据结果对本轮目标有什么初步含义，但不要替洞察分析师写最终结论。
【数据缺陷】如果有数据层问题必须写清楚；如果没有明显问题，写“暂未发现明显数据层缺陷”。
""".strip()
    temperature = 0.1

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """把查询输出处理成本轮数据证据说明。

        输入:
            state: 当前图状态；包含证据规划、查询结果预览、结果元信息和已加载 Skill。

        输出:
            包含 `data_message`、`current_processed_data` 和 `current_data_issue` 的状态更新。
        """
        self.tools = get_task_tools(
            str(state.get("task_id")) if state.get("task_id") else None,
            "data_processor",
        )
        prompt = self.build_prompt(state)
        if self.tools:
            prompt = (
                "当前 Skill 已经为你提供了数据处理工具。你必须先调用可用工具完成工具连通性验证，"
                "然后再根据工具返回和查询结果撰写本轮数据处理说明。\n\n"
                + prompt
            )
        raw_output = self.call_llm(prompt, state)
        self.save_raw_llm_output(state, raw_output)
        data_message = (raw_output or "").strip()
        if not data_message:
            raise ValueError("数据处理师没有返回有效内容。")

        data_issue = self.extract_data_issue(data_message)
        processed = {
            "message": data_message,
            "data_issue": data_issue,
            "artifact_path": state.get("result_path"),
            "row_count": state.get("result_row_count", 0),
            "columns": state.get("result_columns", []),
        }

        return {
            "data_message": data_message,
            "current_processed_data": processed,
            "current_data_issue": data_issue,
            "agent_messages": self.append_agent_message(state, data_message),
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造数据处理 prompt。

        输入:
            state: 当前图状态；包含证据规划、查询结果预览、artifact 路径和 Skill 分析规则。

        输出:
            要求模型以自然语言返回数据情况和证据结果的 prompt 字符串。
        """
        return f"""
用户问题：
{state.get("question", "")}

本轮分析目标：
{state.get("analysis_goal", "")}

证据规划：
{state.get("evidence_message") or json_dumps(state.get("current_evidence_plan", {}))}

结果字段：
{json_dumps(state.get("result_columns", []))}

结果行数：
{state.get("result_row_count", 0)}

是否截断：
{state.get("result_truncated", False)}

结果预览：
{json_dumps(state.get("result_preview", []))}

结果文件：
{state.get("result_path")}
""".strip()

    def build_system_prompt(self, state: Dict[str, Any]) -> str:
        """构造数据处理师的 system prompt，并加入 Skill 分析/计算规则。

        输入:
            state: 当前图状态；包含已加载 Skill。

        输出:
            角色规则、输出格式和 Skill 内容组成的 system prompt。
        """
        skill = state.get("skill") or {}
        return f"""
{self.system_prompt}

Skill 分析/计算规则：
{skill.get("analysis", "")}
""".strip()

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

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成用于任务步骤日志的数据处理摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        return output.get("data_message", "") or "数据处理完成。"
