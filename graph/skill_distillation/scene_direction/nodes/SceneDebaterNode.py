"""场景定性辩论选手节点。"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from graph.common.base import AgentNode
from graph.common.utils import json_dumps


class SceneDebaterNode(AgentNode):
    """从一个固定视角参与场景定性辩论。"""

    system_prompt = """
你是 Skill 场景定性辩论中的选手。

你的目标是在沉淀 Skill 前先判断：
这次分析任务最适合站在哪一个“背景角度”下理解。

你需要基于当前分析任务内容，给出一个明确的主背景方向。
这个方向应当能被后续 Skill 沉淀 Agent 共同使用，用来约束后续多个 Skill 文件的生成方向。

注意：
1. 你只能选择一个主方向，不要并列给出多个候选方向。
2. 你的方向应当贴合当前分析任务，不要脱离任务内容泛化。
3. 你的方向应当是业务背景、对象背景或问题目的层面的表述，不要写成技术方法、SQL方法、统计方法或文件生成方案。
4. 不要讨论是否值得沉淀为 Skill。
5. 不要编写 Skill 文件内容。
6. 不要输出 JSON。
7. 不要使用列表、编号或小标题以外的额外结构。

你的输出必须严格只有两段，每一段的文字尽量保持在50字到100字内：

第一段以【选定方向】开头，说明你认为本次任务应采用的背景角度。
第二段以【选择理由】开头，说明你为什么选择这个方向，以及它为什么比其他可能角度更合适。

除这两段外，不要输出任何其他内容。
""".strip()
    temperature = 0.25
    use_stream = True

    def __init__(self, debater_id: str, title: str, perspective_prompt: str) -> None:
        """初始化一个带固定视角的辩论选手。"""
        super().__init__()
        self.debater_id = self.normalize_debater_id(debater_id)
        self.name = f"scene_debater_{self.debater_id}"
        self.title = title
        self.description = f"{title}参与场景定性辩论。"
        self.perspective_prompt = perspective_prompt.strip()

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成当前辩论轮次的选手发言。"""
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        message = (raw_output or "").strip()
        if not message:
            raise ValueError(f"{self.title}没有返回有效辩论内容。")

        round_index = int(state.get("debate_round") or 1)
        return {
            f"debate_{self.debater_id}_{round_index}": message,
        }

    def build_system_prompt(self, state: Dict[str, Any]) -> str:
        """把共同规则和外部视角 prompt 共存到 system prompt 中。"""
        return f"""
{self.system_prompt}

你的固定观察视角：
{self.perspective_prompt}
""".strip()

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造当前轮辩论 prompt。"""
        round_index = int(state.get("debate_round") or 1)
        max_rounds = int(state.get("max_debate_rounds") or 3)
        base_context = f"""
当前辩论轮次：
{round_index} / {max_rounds}

分析任务上下文：
{json_dumps(state.get("context", {}))}

已有 Skill 的场景摘要，你的结果必须要和这些场景做出明显区分：
{state.get("reference_skill_content", "")}
""".strip()

        if round_index <= 1:
            discussion_context = "此前还没有辩论结果。请给出你的第一轮判断。"
        else:
            discussion_context = f"""
你此前的发言：
{json_dumps(self.collect_debate_messages(state, own=True))}

其他选手此前的发言：
{json_dumps(self.collect_debate_messages(state, own=False))}

裁判此前判断：
{json_dumps(self.collect_judge_messages(state))}

请结合上一轮讨论修正或坚持你的观点。重点说明这个 Skill 适用的业务场景和业务边界。
""".strip()

        return f"""
{base_context}

{discussion_context}

请输出本轮发言。你不需要照顾所有角度，只需要从你的固定视角给出清晰判断。
""".strip()

    def collect_debate_messages(self, state: Dict[str, Any], *, own: bool) -> list[Dict[str, Any]]:
        """按选手归属收集此前轮次发言。"""
        current_round = int(state.get("debate_round") or 1)
        messages: list[Dict[str, Any]] = []
        pattern = re.compile(r"^debate_([A-Za-z0-9_]+)_(\d+)$")
        for key, value in state.items():
            match = pattern.match(str(key))
            if not match:
                continue
            debater_id = match.group(1)
            round_index = int(match.group(2))
            if round_index >= current_round:
                continue
            is_own = debater_id == self.debater_id
            if is_own != own:
                continue
            messages.append(
                {
                    "debater_id": debater_id,
                    "round": round_index,
                    "message": value,
                }
            )
        return sorted(messages, key=lambda item: (item["round"], item["debater_id"]))

    def collect_judge_messages(self, state: Dict[str, Any]) -> list[Dict[str, Any]]:
        """收集此前轮次裁判判断。"""
        current_round = int(state.get("debate_round") or 1)
        messages: list[Dict[str, Any]] = []
        pattern = re.compile(r"^judge_(\d+)$")
        for key, value in state.items():
            match = pattern.match(str(key))
            if not match:
                continue
            round_index = int(match.group(1))
            if round_index >= current_round:
                continue
            messages.append({"round": round_index, "message": value})
        return sorted(messages, key=lambda item: item["round"])

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成节点摘要。"""
        return next(iter(output.values()), "") or f"{self.title}发言完成。"

    def step_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """保留当前选手发言。"""
        return output

    def normalize_debater_id(self, value: str) -> str:
        """把选手 ID 规范成可写入 state key 的形式。"""
        text = (value or "").strip().lower()
        text = re.sub(r"[^a-z0-9_]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        if not text:
            raise ValueError("SceneDebaterNode 需要有效 debater_id。")
        return text
