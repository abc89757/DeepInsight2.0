"""单文件 Skill 沉淀 LangGraph 工作流。"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from graph.skill_distillation.nodes import (
    SceneMinerNode,
    SkillArtifactWriterNode,
    SkillEvaluatorNode,
)
from graph.skill_distillation.state import SkillDistillationState


def route_after_evaluator(state: Dict[str, Any]) -> str:
    """根据评测决策决定是否回到 SceneMiner。"""
    if state.get("evaluator_decision") == "revise":
        return "revise"
    return "finish"


def build_workflow():
    """构建单文件 Skill 沉淀 graph。"""
    graph = StateGraph(SkillDistillationState)

    scene_miner = SceneMinerNode()
    writer = SkillArtifactWriterNode()
    evaluator = SkillEvaluatorNode()

    graph.add_node(scene_miner.name, scene_miner)
    graph.add_node(writer.name, writer)
    graph.add_node(evaluator.name, evaluator)

    graph.add_edge(START, scene_miner.name)
    graph.add_edge(scene_miner.name, writer.name)
    graph.add_edge(writer.name, evaluator.name)
    graph.add_conditional_edges(
        evaluator.name,
        route_after_evaluator,
        {
            "revise": scene_miner.name,
            "finish": END,
        },
    )

    return graph.compile()


def run_skill_artifact_distillation(initial_state: Dict[str, Any]) -> Dict[str, Any]:
    """运行单个 Skill 文件沉淀 workflow，并返回最终 state。"""
    workflow = build_workflow()
    final_state = dict(initial_state)
    for event in workflow.stream(initial_state):
        for node_name, node_update in event.items():
            print(f"task completed node: {node_name}")
            print(f"node output: {node_update}\n\n")
            if isinstance(node_update, dict):
                final_state.update(node_update)
    return final_state

