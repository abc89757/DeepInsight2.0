"""场景定性辩论轮次控制节点。"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, Optional

from graph.common.base import BaseNode


class DebateRoundControllerNode(BaseNode):
    """根据裁判判断和轮次上限决定是否结束辩论。"""

    name = "debate_round_controller"
    title = "辩论轮次控制器"
    description = "根据收敛判定和最大辩论轮数控制场景定性流程。"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """更新辩论轮次或给出最终场景方向。"""
        current_round = int(state.get("debate_round") or 1)
        max_rounds = int(state.get("max_debate_rounds") or 3)
        decision = state.get("judge_decision") or "不收敛"

        should_finish = decision == "收敛" or current_round >= max_rounds
        if not should_finish:
            return {
                "debate_round": current_round + 1,
                "should_finish": False,
                "status": "running",
            }

        selected = self.choose_final_debate(state, current_round)
        return {
            "should_finish": True,
            "selected_debater_id": selected["debater_id"],
            "scene_direction": selected["message"],
            "status": "succeeded",
        }

    def choose_final_debate(self, state: Dict[str, Any], current_round: int) -> Dict[str, str]:
        """从当前轮发言中随机选一个作为最终方向。"""
        candidates = self.collect_debates_by_round(state, current_round)
        if not candidates:
            candidates = self.collect_all_debates(state)
        if not candidates:
            raise ValueError("没有可用于生成最终场景方向的辩论结果。")
        return random.choice(candidates)

    def collect_debates_by_round(self, state: Dict[str, Any], round_index: int) -> list[Dict[str, str]]:
        """收集指定轮次的选手发言。"""
        candidates: list[Dict[str, str]] = []
        pattern = re.compile(r"^debate_([A-Za-z0-9_]+)_(\d+)$")
        for key, value in state.items():
            match = pattern.match(str(key))
            if not match:
                continue
            if int(match.group(2)) != round_index:
                continue
            candidates.append(
                {
                    "debater_id": match.group(1),
                    "message": str(value or "").strip(),
                }
            )
        return [item for item in candidates if item["message"]]

    def collect_all_debates(self, state: Dict[str, Any]) -> list[Dict[str, str]]:
        """兜底收集所有选手发言。"""
        candidates: list[Dict[str, str]] = []
        pattern = re.compile(r"^debate_([A-Za-z0-9_]+)_(\d+)$")
        for key, value in state.items():
            match = pattern.match(str(key))
            if not match:
                continue
            candidates.append(
                {
                    "debater_id": match.group(1),
                    "message": str(value or "").strip(),
                }
            )
        return [item for item in candidates if item["message"]]

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成节点摘要。"""
        if output.get("should_finish"):
            return output.get("scene_direction", "")[:500] or "场景定性已结束。"
        return f"进入第 {output.get('debate_round')} 轮辩论。"

    def step_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """保留路由字段和最终方向。"""
        return output

