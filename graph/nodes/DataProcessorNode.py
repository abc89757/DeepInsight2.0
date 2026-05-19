"""数据处理师节点。

这个文件定义 DataProcessorNode，用来把查询结果预览和 artifact 信息整理成可分析的数据证据。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps, parse_json_object


class DataProcessorNode(AgentNode):
    """负责把查询结果转成证据项处理结果和数据问题的 AgentNode。"""

    name = "data_processor"
    title = "数据处理师"
    description = "根据查询结果生成证据项、处理结果和数据问题说明。"
    system_prompt = "你是数据处理师。你只输出 JSON，不输出解释。"
    temperature = 0.1

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """把查询输出处理成本轮证据项。

        输入:
            state: 当前图状态；包含证据规划、查询结果预览、结果元信息和已加载 Skill。

        输出:
            包含 `current_processed_data` 和 `current_data_issue` 的状态更新。
        """
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        processed = parse_json_object(raw_output)
        if not processed:
            raise ValueError("数据处理师没有返回有效 JSON。")

        evidence_items = processed.get("evidence_items")
        if not isinstance(evidence_items, list):
            evidence_items = []
        data_issue = processed.get("data_issue")
        if not isinstance(data_issue, list):
            data_issue = []

        processed["evidence_items"] = evidence_items
        processed["data_issue"] = data_issue
        processed.setdefault("summary", "")
        processed.setdefault("artifact_path", state.get("result_path"))
        processed.setdefault("row_count", state.get("result_row_count", 0))
        processed.setdefault("columns", state.get("result_columns", []))

        return {
            "current_processed_data": processed,
            "current_data_issue": data_issue,
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造数据处理 prompt。

        输入:
            state: 当前图状态；包含证据规划、查询结果预览、artifact 路径和 Skill 分析规则。

        输出:
            要求模型以 JSON 返回处理后证据项的 prompt 字符串。
        """
        skill = state.get("skill") or {}
        return f"""
请根据 current_evidence_plan 和查询结果预览，完成本轮数据处理。
重点不是写最终结论，而是把每个证据项的数据处理方法、处理结果和初步含义说清楚。
如果发现数据层问题，例如字段缺失、结果为空、结果被截断、口径无法满足，也要写入 data_issue。

本轮分析目标：
{state.get("analysis_goal", "")}

证据规划：
{json_dumps(state.get("current_evidence_plan", {}))}

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

Skill 分析/计算规则：
{skill.get("analysis", "")}

要求：
1. 只输出 JSON，不要输出 Markdown 或解释。
2. JSON 字符串内部如果需要引用字段值、标签或原文，请使用单引号或中文引号，不要使用英文双引号。
3. 如果必须使用英文双引号，必须写成转义形式 `\"`，保证整体 JSON 可以被 json.loads 解析。

只输出 JSON：
{{
  "summary": "本轮数据处理摘要",
  "evidence_items": [
    {{
      "name": "证据项名称",
      "method": "数据处理、计算或筛选方法",
      "result": "处理后的结果",
      "interpretation": "这个结果对本轮分析目标的含义"
    }}
  ],
  "data_issue": [
    "数据层问题，例如字段缺失、结果为空、口径不足、预览受限"
  ],
  "artifact_path": "结果文件路径"
}}
""".strip()

    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        """调用配置好的 LLM 完成数据处理。

        输入:
            prompt: `build_prompt` 生成的 prompt。
            state: 当前图状态；此处主要用于保持 AgentNode 接口一致。

        输出:
            预期包含 JSON 对象的模型原始文本。
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
        """生成用于任务步骤日志的数据处理摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        processed = output.get("current_processed_data") or {}
        return processed.get("summary") or "数据处理完成。"
