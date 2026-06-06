"""
TestAgentNodeStream
功能：最小化测试 AgentNode 的 __call__ / call_llm / astream_agent 流程，
用于观察 reasoning_content、content、tool_calls 和最终返回结果。

使用方式：
1. 把本文件放到 DeepInsight2.0 项目根目录下。
2. 修改下面的 AgentNode 导入路径，使其指向你项目中的真实 AgentNode。
3. 配置 .env 中的 LLM_MODEL / LLM_BASE_URL / LLM_API_KEY。
4. 运行：
   python test_agentnode_stream.py
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool


# TODO: 根据你的项目实际路径修改这里
# 例子：
# from app.nodes.agent_node import AgentNode
# from backend.nodes.agent_node import AgentNode
# from src.nodes.agent_node import AgentNode
from graph.common.base import AgentNode


class ChooseProcessorActionArgs(BaseModel):
    """测试工具参数。"""

    action: str = Field(
        default="不需要数据",
        description="下一步动作，可选：需要数据 / 处理已有数据 / 直接回答",
    )


def choose_processor_action(action: str = "不需要数据") -> Dict[str, Any]:
    """
    测试用工具：模拟 choose_processor_action。
    这里不做任何真实业务处理，只返回结构化结果。
    """
    print(f"[TOOL_EXECUTED] choose_processor_action(action={action!r})")
    return {
        "ok": True,
        "executed": True,
        "action": action,
        "message": "测试工具已执行。工具返回后请输出最终回答，不要再次调用该工具。",
    }


class TestReasoningAgentNode(AgentNode):
    """
    最小测试节点：
    - 继承你的 AgentNode；
    - 使用一个测试工具触发 tool_call；
    - 通过 __call__ 执行节点；
    - 观察 astream_agent 是否能拿到 reasoning_content 并正确拼接。
    """

    name = "test_reasoning_agent"
    title = "Reasoning 流式测试节点"
    temperature = 0.2
    use_stream = True
    stream = True
    timeout = 300

    system_prompt = (
        "你是一个用于测试流式输出和工具调用的 Agent。\n"
        "规则：\n"
        "1. 你必须在输出任何正式回答前，先调用一次 choose_processor_action。\n"
        "2. choose_processor_action 在本轮最多只能调用一次，调用后不得再次调用。\n"
        "3. 工具返回后，输出一个简短最终回答。\n"
        "4. 不要在工具调用前输出正式回答正文。\n"
    )

    tools = [
        StructuredTool.from_function(
            func=choose_processor_action,
            name="choose_processor_action",
            description=(
                "选择下一步处理动作。本工具只用于测试，"
                "本轮最多调用一次。"
            ),
            args_schema=ChooseProcessorActionArgs,
        )
    ]

    def has_query_result(self, state: Dict[str, Any]) -> bool:
        """测试用：模拟当前是否已有查询结果。"""
        return bool(state.get("has_query_result"))

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造测试 prompt。"""
        user_question = state.get("question") or "请简单介绍你自己，并说明你已经完成工具调用。"

        if self.has_query_result(state):
            prefix = (
                "当前已有查询结果。\n"
                "你必须在输出任何正式回答内容之前，先调用一次 choose_processor_action 选择下一步。\n"
                "不要先输出分析草稿再调用工具；必须先调用 choose_processor_action，再开始正式回答。\n"
                "choose_processor_action 在本轮节点执行中最多只能调用一次；调用后不得再次调用该工具。\n"
                "工具返回后，请基于工具结果输出最终回答。\n\n"
            )
        else:
            prefix = (
                "当前还没有查询结果或数据文件。\n"
                "你必须在输出任何正式回答内容之前，先调用一次 choose_processor_action 选择下一步。\n"
                "不要先输出分析草稿再调用工具；必须先调用 choose_processor_action，再开始正式回答。\n"
                "choose_processor_action 在本轮节点执行中最多只能调用一次；调用后不得再次调用该工具。\n"
                "工具返回后，请判断当前需要哪些数据，并在最终回答中说明。\n\n"
            )

        return prefix + f"用户问题：{user_question}"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        BaseNode.__call__ 通常会调用 run(state)。
        这里在 run 内部调用 AgentNode.call_llm。
        """
        prompt = self.build_prompt(state)
        content = self.call_llm(prompt, state)

        print("\n========== FINAL CONTENT RETURNED BY call_llm ==========")
        print(content)
        print("========================================================\n")

        return {
            "test_agent_output": content,
        }


def main() -> None:
    load_dotenv()

    # 建议你先在控制台确认这些变量是否正确
    print("[ENV] LLM_MODEL =", os.getenv("LLM_MODEL"))
    print("[ENV] LLM_BASE_URL =", os.getenv("LLM_BASE_URL"))
    print("[ENV] LLM_API_KEY exists =", bool(os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")))

    node = TestReasoningAgentNode()

    state: Dict[str, Any] = {
        "task_id": "test_reasoning_task",
        "_node_output_step": 1,
        "question": "请先调用工具，然后用两三句话介绍你自己。",
        "has_query_result": False,
    }

    print("\n========== CALL NODE BY __call__ ==========")

    # 优先测试 __call__
    # 如果你的 BaseNode.__call__ 需要的 state 字段更多，这里报错后再补。
    result = node.run(state)

    print("\n========== NODE RESULT ==========")
    print(result)
    print("=================================\n")


if __name__ == "__main__":
    main()
