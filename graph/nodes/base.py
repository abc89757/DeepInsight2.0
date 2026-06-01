"""节点基类定义。

这个文件定义 LangGraph 节点的通用调用协议，以及 AgentNode 和 ToolNode 两类节点基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import os
from typing import Any, Dict, Optional

from services.llm_client import LLMClient
from services.node_output_store import allocate_node_step, save_node_json, save_node_text
from services.task_cancellation import raise_if_task_cancelled
from services.task_events import publish_task_event
from services.task_persistence import fail_task_step, finish_task_step, start_task_step
from services.tool_call_store import save_tool_call


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

        raise_if_task_cancelled(str(task_id) if task_id else None)

        if task_id:
            node_output_step = allocate_node_step(str(task_id), self.name)
            state["_node_output_step"] = node_output_step
            state["_node_output_name"] = self.name
            publish_task_event(
                str(task_id),
                "node_started",
                {
                    "node": self.name,
                    "step_number": node_output_step,
                    "title": self.title,
                    "summary": self.description or self.title,
                },
            )
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
            output_summary = self.summarize_output(output)

            if step_id:
                finish_task_step(
                    step_id=step_id,
                    output_summary=output_summary,
                    output_json=self.step_output(output),
                )

            publish_task_event(
                str(task_id) if task_id else None,
                "node_finished",
                {
                    "node": self.name,
                    "step_number": node_output_step,
                    "title": self.title,
                    "summary": output_summary or "",
                    "output": self.step_output(output),
                },
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
            publish_task_event(
                str(task_id) if task_id else None,
                "node_failed",
                {
                    "node": self.name,
                    "step_number": node_output_step,
                    "title": self.title,
                    "error": str(exc),
                },
            )
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
    use_stream: bool = True
    timeout: int = 300

    def __init__(self) -> None:
        """初始化 AgentNode 并创建 LLM 客户端。

        输入:
            无。
        输出:
            无返回值，实例上会持有 `llm_client`、LangChain chat model 和消息历史。
        """
        self.llm_client = LLMClient()
        from langchain_openai import ChatOpenAI

        self.model = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY"),
            temperature=self.temperature,
            timeout=int(os.getenv("LLM_TIMEOUT_SECONDS", str(self.timeout))),
            streaming=True,
        )
        self.messages: list[dict[str, str]] = []

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

    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        """使用官方 `create_agent` 调用 LLM 获取 Agent 输出。

        输入:
            prompt: 已构建的本轮 user prompt 字符串。
            state: 当前图状态。
        输出:
            Agent 最终返回的原始文本，同时会维护当前节点对象的 messages 历史。
        """
        from langchain.agents import create_agent

        self.messages.append({"role": "user", "content": prompt})
        agent = create_agent(
            model=self.model,
            tools=self.prepare_tools(state),
            system_prompt=self.build_system_prompt(state),
            name=self.name,
        )
        if self.use_stream:
            if self.tools:
                content = asyncio.run(self.astream_agent(agent, state))
            else:
                content = self.stream_agent(agent, state)
        else:
            result = self.invoke_agent(agent)
            content = self.extract_agent_content(result)
            publish_task_event(
                str(state.get("task_id")) if state.get("task_id") else None,
                "agent_message",
                {
                    "node": self.name,
                    "step_number": state.get("_node_output_step"),
                    "title": self.title,
                    "summary": content,
                },
            )
        self.messages.append({"role": "assistant", "content": content})
        return content

    def prepare_tools(self, state: Dict[str, Any]) -> list[Any]:
        """为当前 Agent 准备工具，并给工具调用加上审计日志。

        输入:
            state: 当前图状态；用于读取 task_id 和节点执行上下文。

        输出:
            可以传给 `create_agent` 的工具列表。
        """
        task_id = str(state.get("task_id")) if state.get("task_id") else None
        if not self.tools:
            return []
        return [self.wrap_tool_for_logging(tool, task_id) for tool in self.tools]

    def wrap_tool_for_logging(self, tool: Any, task_id: Optional[str]) -> Any:
        """包裹单个 LangChain tool，记录每次 invoke/ainvoke。

        输入:
            tool: 原始工具对象。
            task_id: 当前任务 ID。

        输出:
            带审计日志能力的工具对象。
        """
        from langchain_core.tools import StructuredTool

        tool_name = getattr(tool, "name", tool.__class__.__name__)
        description = getattr(tool, "description", "") or ""
        args_schema = getattr(tool, "args_schema", None)

        def _invoke_with_log(**kwargs: Any) -> Any:
            try:
                result = tool.invoke(kwargs)
                save_tool_call(task_id, self.name, tool_name, kwargs, result=result)
                return result
            except Exception as exc:
                save_tool_call(task_id, self.name, tool_name, kwargs, error=str(exc))
                raise

        async def _ainvoke_with_log(**kwargs: Any) -> Any:
            try:
                result = await tool.ainvoke(kwargs)
                save_tool_call(task_id, self.name, tool_name, kwargs, result=result)
                return result
            except Exception as exc:
                save_tool_call(task_id, self.name, tool_name, kwargs, error=str(exc))
                raise

        return StructuredTool.from_function(
            func=_invoke_with_log,
            coroutine=_ainvoke_with_log,
            name=tool_name,
            description=description,
            args_schema=args_schema,
        )

    def invoke_agent(self, agent: Any) -> Any:
        """调用官方 agent，并在存在工具时优先使用异步入口。

        输入:
            agent: `create_agent` 创建出的 runnable。

        输出:
            Agent 的原始返回值。
        """
        if self.tools:
            return asyncio.run(agent.ainvoke({"messages": list(self.messages)}))
        return agent.invoke({"messages": list(self.messages)})

    def stream_agent(self, agent: Any, state: Dict[str, Any]) -> str:
        """流式调用官方 agent，并把增量文本发布到 SSE。

        输入:
            agent: `create_agent` 创建出的 runnable。
            state: 当前图状态。

        输出:
            本次 agent 最终回复文本。
        """
        task_id = str(state.get("task_id")) if state.get("task_id") else None
        step_number = state.get("_node_output_step")
        chunks: list[str] = []
        last_content = ""
        for event in agent.stream({"messages": list(self.messages)}, stream_mode="messages"):
            message = self.extract_stream_message(event)
            if message is None:
                continue
            content = self.message_content_to_text(getattr(message, "content", "") or "")
            if not content:
                continue
            delta = self.get_delta(last_content, content)
            if not delta:
                continue
            last_content = content
            chunks.append(delta)
            publish_task_event(
                task_id,
                "agent_delta",
                {
                    "node": self.name,
                    "step_number": step_number,
                    "title": self.title,
                    "delta": delta,
                    "summary": "".join(chunks),
                },
            )
        content = "".join(chunks).strip()
        if not content and not self.tools:
            result = agent.invoke({"messages": list(self.messages)})
            content = self.extract_agent_content(result)
        publish_task_event(
            task_id,
            "agent_message",
            {
                "node": self.name,
                "step_number": step_number,
                "title": self.title,
                "summary": content,
            },
        )
        return content

    async def astream_agent(self, agent: Any, state: Dict[str, Any]) -> str:
        """异步流式调用 agent，用于带工具的节点，避免 async-only 工具走同步 invoke。"""
        task_id = str(state.get("task_id")) if state.get("task_id") else None
        step_number = state.get("_node_output_step")
        chunks: list[str] = []
        last_content = ""
        async for event in agent.astream({"messages": list(self.messages)}, stream_mode="messages"):
            message = self.extract_stream_message(event)
            if message is None:
                continue
            content = self.message_content_to_text(getattr(message, "content", "") or "")
            if not content:
                continue
            delta = self.get_delta(last_content, content)
            if not delta:
                continue
            last_content = content
            chunks.append(delta)
            publish_task_event(
                task_id,
                "agent_delta",
                {
                    "node": self.name,
                    "step_number": step_number,
                    "title": self.title,
                    "delta": delta,
                    "summary": "".join(chunks),
                },
            )
        content = "".join(chunks).strip()
        if not content:
            result = await agent.ainvoke({"messages": list(self.messages)})
            content = self.extract_agent_content(result)
        publish_task_event(
            task_id,
            "agent_message",
            {
                "node": self.name,
                "step_number": step_number,
                "title": self.title,
                "summary": content,
            },
        )
        return content

    def message_content_to_text(self, content: Any) -> str:
        """Extract only human-readable text from streamed message content."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type in {None, "text"}:
                        text = item.get("text") or item.get("content")
                        if text:
                            parts.append(str(text))
            return "".join(parts)
        return str(content or "")

    def extract_stream_message(self, event: Any) -> Any:
        """从 LangChain stream 事件中取出消息对象。

        输入:
            event: `agent.stream(..., stream_mode="messages")` 产出的事件。

        输出:
            可能包含 content 的消息对象；无法识别时返回 None。
        """
        if isinstance(event, tuple) and event:
            return event[0]
        if isinstance(event, dict):
            messages = event.get("messages")
            if messages:
                return messages[-1]
        return event

    def get_delta(self, previous: str, current: str) -> str:
        """根据上一次累计文本和当前文本计算新增片段。

        输入:
            previous: 上一次看到的累计文本。
            current: 当前事件里的文本。

        输出:
            新增文本片段。
        """
        if current.startswith(previous):
            return current[len(previous) :]
        return current

    def build_system_prompt(self, state: Dict[str, Any]) -> str:
        """构造传给 `create_agent` 的 system prompt。

        输入:
            state: 当前图状态；子类可从中读取 Skill 或其他上下文。

        输出:
            当前 Agent 的系统提示词。
        """
        return self.system_prompt or ""

    def extract_agent_content(self, result: Any) -> str:
        """从 `create_agent.invoke` 的返回值中提取最终文本。

        输入:
            result: LangChain agent 返回值，通常包含 `messages`。

        输出:
            最后一条 assistant 消息的文本内容。
        """
        if isinstance(result, dict):
            messages = result.get("messages") or []
            if messages:
                last_message = messages[-1]
                content = getattr(last_message, "content", None)
                if content is None and isinstance(last_message, dict):
                    content = last_message.get("content")
                return str(content or "").strip()
            output = result.get("output")
            if output is not None:
                return str(output).strip()
        return str(result or "").strip()
