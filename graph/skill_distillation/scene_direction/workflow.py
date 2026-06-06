"""Skill 场景定性辩论 LangGraph 工作流。"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from graph.skill_distillation.scene_direction.nodes import (
    DebateRoundControllerNode,
    SceneDebaterNode,
    SceneJudgeNode,
)
from graph.skill_distillation.scene_direction.prompts import DEBATER_PROMPTS
from graph.skill_distillation.scene_direction.state import SceneDirectionState


def route_after_controller(state: Dict[str, Any]) -> str:
    """根据轮次控制器输出决定继续辩论还是结束。"""
    if state.get("should_finish"):
        return "finish"
    return "continue"


def build_workflow():
    """构建场景定性辩论 graph。"""
    graph = StateGraph(SceneDirectionState)

    debaters = [
        SceneDebaterNode(
            debater_id,
            config["title"],
            config["prompt"],
        )
        for debater_id, config in DEBATER_PROMPTS.items()
    ]
    judge = SceneJudgeNode()
    controller = DebateRoundControllerNode()

    for debater in debaters:
        graph.add_node(debater.name, debater)
    graph.add_node(judge.name, judge)
    graph.add_node(controller.name, controller)

    graph.add_edge(START, debaters[0].name)
    for previous, current in zip(debaters, debaters[1:]):
        graph.add_edge(previous.name, current.name)
    graph.add_edge(debaters[-1].name, judge.name)
    graph.add_edge(judge.name, controller.name)
    graph.add_conditional_edges(
        controller.name,
        route_after_controller,
        {
            "continue": debaters[0].name,
            "finish": END,
        },
    )

    return graph.compile()


def run_scene_direction_debate(initial_state: Dict[str, Any]) -> Dict[str, Any]:
    """运行场景定性辩论 graph，并返回最终 state。"""
    workflow = build_workflow()
    final_state = dict(initial_state)
    final_state.setdefault("debater_ids", list(DEBATER_PROMPTS.keys()))
    for event in workflow.stream(final_state):
        for node_name, node_update in event.items():
            print(f"scene direction completed node: {node_name}")
            print(f"node output: {node_update}\n\n")
            if isinstance(node_update, dict):
                final_state.update(node_update)
    return final_state
