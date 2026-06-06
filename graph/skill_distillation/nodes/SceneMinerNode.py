"""Skill 场景沉淀分析节点。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from graph.common.base import AgentNode
from graph.common.utils import json_dumps


class SceneMinerNode(AgentNode):
    """分析当前 Skill 文件应该沉淀哪些可复用规则。"""

    name = "skill_scene_miner"
    title = "Skill 场景分析师"
    description = "根据分析任务结果和评测反馈，提炼当前 Skill 文件的沉淀方向。"
    system_prompt = """
你是 Skill 场景分析师。你负责从一次通用分析任务的结果中，提炼可以复用到同类业务场景的分析经验。

你不是写最终 md 文件的人，而是给后续 Skill 文件撰写人提供沉淀方向。
请用中文自然语言输出，不要强制输出 JSON。

你需要重点判断：
1. 当前任务体现了什么业务场景或分析问题类型。
2. 哪些分析路径、指标选择、数据处理或报告表达是可复用的。
3. 哪些内容只是本次个案，不应该写进长期 Skill。
4. 当前 skill_type 对应的文件最应该沉淀什么。
5. 如果上一轮评测要求返工，本轮应该如何补充、删除或泛化。

请避免：
1. 复述本次最终报告结论。
2. 把具体表名、文件路径、任务 ID、具体数值结论写成通用规则。
3. 把一次偶然分析路径包装成稳定业务规律。
""".strip()
    temperature = 0.2
    use_stream = True

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成当前轮次的场景沉淀分析。"""
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        message = (raw_output or "").strip()
        if not message:
            raise ValueError("SceneMinerNode 没有返回有效内容。")

        return {
            "scene_mining_message": message,
            "status": "running",
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造场景沉淀分析 prompt。"""
        return f"""
当前正在沉淀的 Skill 文件类型：
{state.get("skill_type", "")}

目标文件名：
{state.get("file_name", "")}

本文件写作规格：
{json_dumps(state.get("artifact_spec", {}))}

当前迭代轮次：
{state.get("round_index", 1)} / {state.get("max_rounds", 3)}

本次 Skill 沉淀的统一场景方向：
{state.get("scene_direction", "")}

用户问题与分析轮次上下文：
{json_dumps(state.get("context", {}))}

同类型参考 Skill 文件内容：
{state.get("reference_skill_content", "")}

上一轮评测意见：
{state.get("evaluation_message", "")}

历史返工记录：
{json_dumps(state.get("revision_history", []))}

请输出本轮沉淀分析，说明后续撰写人应该怎么写这个文件、哪些内容必须泛化、哪些内容必须避免。
""".strip()

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成节点摘要。"""
        return output.get("scene_mining_message", "") or "Skill 场景分析完成。"
