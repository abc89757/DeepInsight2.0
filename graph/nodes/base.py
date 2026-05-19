"""节点基类定义。

这个文件定义 LangGraph 节点的通用调用协议，以及 AgentNode 和 ToolNode 两类节点基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from services.llm_client import LLMClient
from services.node_output_store import allocate_node_step, save_node_json, save_node_text
from services.task_persistence import fail_task_step, finish_task_step, start_task_step


class BaseNode(ABC):
    """所有 LangGraph 节点的基础协议。"""

    name: str = ""
    title: str = ""
    description: str = ""

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行节点并记录任务步骤状态。

        输入:
            state: 当前图状态。
        输出:
            节点 `run` 方法返回的状态更新。
        """
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} is missing name")
        if not self.title:
            raise ValueError(f"{self.__class__.__name__} is missing title")

        task_id = state.get("task_id")
        step_id: Optional[str] = None
        node_output_step: Optional[int] = None

        if task_id:
            node_output_step = allocate_node_step(str(task_id), self.name)
            state["_node_output_step"] = node_output_step
            state["_node_output_name"] = self.name
            step_id = start_task_step(
                task_id=task_id,
                step_name=self.name,
                step_title=self.title,
                input_summary=self.summarize_input(state),
                message=self.description or self.title,
            )

        try:
            output = self.run(state)
            if not isinstance(output, dict):
                raise TypeError(f"{self.name}.run() must return a dict")

            save_node_json(str(task_id) if task_id else None, node_output_step, self.name, "output", output)

            if step_id:
                finish_task_step(
                    step_id=step_id,
                    output_summary=self.summarize_output(output),
                    output_json=self.step_output(output),
                )

            return output
        except Exception as exc:
            save_node_json(
                str(task_id) if task_id else None,
                node_output_step,
                self.name,
                "error",
                {
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            if step_id:
                fail_task_step(step_id, str(exc))
            raise
        finally:
            state.pop("_node_output_step", None)
            state.pop("_node_output_name", None)

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行节点逻辑。

        输入:
            state: 当前图状态。
        输出:
            需要合并回 state 的字段字典。
        """

    def summarize_input(self, state: Dict[str, Any]) -> Optional[str]:
        """生成任务步骤输入摘要。

        输入:
            state: 当前图状态。
        输出:
            人类可读的输入摘要；默认不展示。
        """
        return None

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成任务步骤输出摘要。

        输入:
            output: 节点输出。
        输出:
            人类可读的输出摘要。
        """
        return self.description or self.title

    def step_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """挑选需要持久化到任务步骤中的输出字段。

        输入:
            output: 节点输出。
        输出:
            可 JSON 序列化的输出字典。
        """
        return output


class ToolNode(BaseNode):
    """确定性工具节点基类。"""


class AgentNode(BaseNode):
    """由 LLM 驱动的 Agent 节点基类。"""

    temperature: float = 0.2
    tools: list[Any] = []
    system_prompt: Optional[str] = None
    stream: bool = False
    timeout: int = 300

    def __init__(self) -> None:
        """初始化 AgentNode 并创建 LLM 客户端。

        输入:
            无。
        输出:
            无返回值，实例上会持有 `llm_client`。
        """
        self.llm_client = LLMClient()

    def save_raw_llm_output(self, state: Dict[str, Any], raw_output: str, label: str = "raw_llm") -> Optional[str]:
        """保存 Agent 的模型原始输出。

        输入:
            state: 当前图状态；其中包含 BaseNode 注入的节点执行步号。
            raw_output: LLM 返回的原始文本。
            label: 输出文件标签，默认 raw_llm。
        输出:
            成功写入时返回文件路径；否则返回 None。
        """
        return save_node_text(
            str(state.get("task_id")) if state.get("task_id") else None,
            state.get("_node_output_step"),
            self.name,
            label,
            raw_output,
        )

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行完整 Agent 工作。

        输入:
            state: 当前图状态。
        输出:
            需要合并回 state 的字段字典。
        """

    @abstractmethod
    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构建 Agent prompt。

        输入:
            state: 当前图状态。
        输出:
            prompt 字符串。
        """

    @abstractmethod
    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        """调用 LLM 获取 Agent 输出。

        输入:
            prompt: 已构建的 prompt 字符串。
            state: 当前图状态。
        输出:
            LLM 返回的原始文本。
        """
