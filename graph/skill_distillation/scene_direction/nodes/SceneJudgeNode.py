"""场景定性辩论裁判节点。"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from graph.common.base import AgentNode
from graph.common.utils import json_dumps, split_think_content


class SceneJudgeNode(AgentNode):
    """判断当前辩论轮次是否已经收敛。"""

    name = "scene_judge"
    title = "场景定性裁判"
    description = "判断场景定性辩论是否已经收敛。"
    system_prompt = """
你是 Skill 场景定性辩论的裁判。你只负责判断当前选手讨论是否已经收敛。

收敛表示：选手们对“这个 Skill 适用什么业务场景”和“这个场景的业务边界”已经没有明显冲突，后续可以把这些观点交给 Skill 沉淀流程使用。
不收敛表示：选手们仍然在场景类型、业务边界、与参考 Skill 的差异上存在明显冲突，或者观点还过于空泛。

你的输出只能是下面两个词之一：
收敛
不收敛
""".strip()
    temperature = 0.0
    use_stream = True

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """判断当前轮是否收敛。"""
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        body, _ = split_think_content(raw_output)
        decision = self.normalize_decision(body or raw_output)
        round_index = int(state.get("debate_round") or 1)
        return {
            "judge_decision": decision,
            "judge_message": decision,
            f"judge_{round_index}": decision,
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造裁判 prompt。"""
        round_index = int(state.get("debate_round") or 1)
        return f"""
当前辩论轮次：
{round_index} / {state.get("max_debate_rounds", 3)}

当前轮选手发言：
{json_dumps(self.collect_current_round_debates(state))}

历史裁判判断：
{json_dumps(self.collect_judge_messages(state))}

请判断当前讨论是否已经收敛。
只能输出：收敛 或 不收敛。
""".strip()

    def collect_current_round_debates(self, state: Dict[str, Any]) -> list[Dict[str, Any]]:
        """收集当前轮所有选手发言。"""
        round_index = int(state.get("debate_round") or 1)
        messages: list[Dict[str, Any]] = []
        pattern = re.compile(r"^debate_([A-Za-z0-9_]+)_(\d+)$")
        for key, value in state.items():
            match = pattern.match(str(key))
            if not match:
                continue
            if int(match.group(2)) != round_index:
                continue
            messages.append(
                {
                    "debater_id": match.group(1),
                    "round": round_index,
                    "message": value,
                }
            )
        return sorted(messages, key=lambda item: item["debater_id"])

    def collect_judge_messages(self, state: Dict[str, Any]) -> list[Dict[str, Any]]:
        """收集历史裁判判断。"""
        round_index = int(state.get("debate_round") or 1)
        messages: list[Dict[str, Any]] = []
        pattern = re.compile(r"^judge_(\d+)$")
        for key, value in state.items():
            match = pattern.match(str(key))
            if not match:
                continue
            judge_round = int(match.group(1))
            if judge_round >= round_index:
                continue
            messages.append({"round": judge_round, "message": value})
        return sorted(messages, key=lambda item: item["round"])

    def normalize_decision(self, text: str) -> str:
        """把模型输出归一成收敛/不收敛。"""
        value = (text or "").strip()
        if "不收敛" in value:
            return "不收敛"
        if "收敛" in value:
            return "收敛"
        return "不收敛"

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成节点摘要。"""
        return output.get("judge_decision") or "裁判判断完成。"

    def step_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """保留裁判判断。"""
        return output
