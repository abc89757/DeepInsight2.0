"""节点基类定义。

这个文件定义 LangGraph 节点的通用调用协议，以及 AgentNode 和 ToolNode 两类节点基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from typing import Any, Dict, Optional

from services.llm_factory import create_chat_model
from services.node_output_store import allocate_node_step, save_node_json, save_node_text
from services.task_cancellation import raise_if_task_cancelled
from services.task_events import publish_task_event
from services.task_persistence import fail_task_step, finish_task_step, start_task_step
from services.tool_call_store import save_tool_call
from graph.common.utils import split_think_content


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
            # 返回结果前把思考内容去除
            return self.strip_think_content(output)
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

    def strip_think_content(self, value: Any) -> Any:
        """移除返回给 LangGraph state 的 `<think>` 内容，保留原始结构。

        节点原始输出仍会用于本地日志、步骤数据库和 SSE 事件；这里只清洗
        最终合并进 state 的返回值，避免后续节点消费到思考内容。
        """
        if isinstance(value, str):
            body, _ = split_think_content(value)
            return body
        if isinstance(value, dict):
            return {key: self.strip_think_content(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.strip_think_content(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.strip_think_content(item) for item in value)
        return value


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
        """初始化 AgentNode 并创建 LangChain chat model。

        输入:
            无。
        输出:
            无返回值，实例上会持有 LangChain chat model 和消息历史。
        """
        self.model = create_chat_model(
            temperature=self.temperature,
            streaming=True,
            timeout=self.timeout,
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

    def save_agent_input(
        self,
        state: Dict[str, Any],
        messages: list[dict[str, Any]],
        system_prompt: Optional[str],
        tools: list[Any],
    ) -> None:
        """保存即将传给 Agent 的输入内容。

        输入:
            state: 当前图状态；其中包含 BaseNode 注入的节点执行步号。
            messages: 本轮实际传给 Agent 的 messages，包含节点已有记忆和当前 user message。
            system_prompt: 本轮 system prompt。
            tools: 本轮传给 Agent 的工具列表。
        输出:
            无返回值；失败时只打印日志，不影响主流程。
        """
        task_id = str(state.get("task_id")) if state.get("task_id") else None
        step_number = state.get("_node_output_step")
        save_node_text(task_id, step_number, self.name, "system_prompt", system_prompt or "")
        save_node_json(task_id, step_number, self.name, "messages", messages)
        save_node_json(
            task_id,
            step_number,
            self.name,
            "input",
            {
                "system_prompt": system_prompt or "",
                "messages": messages,
                "tools": [self.describe_tool(tool) for tool in tools],
                "use_stream": self.use_stream,
            },
        )

    def describe_tool(self, tool: Any) -> Dict[str, Any]:
        """返回适合保存到输入日志里的工具描述。"""
        args_schema = getattr(tool, "args_schema", None)
        schema: Any = None
        if args_schema is not None:
            try:
                schema = args_schema.model_json_schema()
            except Exception:
                try:
                    schema = args_schema.schema()
                except Exception:
                    schema = str(args_schema)
        return {
            "name": getattr(tool, "name", tool.__class__.__name__),
            "description": getattr(tool, "description", "") or "",
            "args_schema": schema,
        }

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

        tools = self.prepare_tools(state)
        system_prompt = self.build_system_prompt(state)
        messages_for_agent = [*self.messages, {"role": "user", "content": prompt}]
        self.save_agent_input(state, messages_for_agent, system_prompt, tools)
        self.messages = messages_for_agent
        agent = create_agent(
            model=self.model,
            tools=tools,
            system_prompt=system_prompt,
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
        thinking_open: bool = False
        # last_content = ""
        for event in agent.stream({"messages": list(self.messages)}, stream_mode="messages"):
            message = self.extract_stream_message(event)
            if message is None:
                continue
            # content = self.message_content_to_text(getattr(message, "content", "") or "")
            parsed = self.message_content_to_text(message)
            if not parsed:
                continue

            parsed_type = parsed.get("type")
            delta = parsed.get("delta", "")
            # if not content:
            #     continue
            # delta = self.get_delta(last_content, content)

            # last_content = content
            if parsed_type == "reason":
                if not thinking_open:
                    delta=f"<think>{delta}"
                    thinking_open = True
            elif parsed_type == "content":
                if thinking_open:
                    delta=f"</think>{delta}"
                    thinking_open = False
            else:
                continue

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
        print('--'*20)
        print(content)
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
        # 记录不同 message_key 出现的顺序
        message_order: list[str] = []
        # 保存每个 message_key 已经累计出的文本,包括思考内容+正文
        message_texts: dict[str, str] = {}
        # 保存每个 message_key 上一次看到的内容，用于算 delta
        # last_contents: dict[str, str] = {}
        # 记录哪些 message_key 属于工具调用消息，需要跳过展示
        tool_call_messages: set[str] = set()
        # 记录当前key是否思考过了，用于给content加上<think>隔离
        thinking_open: dict[str, bool] = {}
        async for event in agent.astream({"messages": list(self.messages)}, stream_mode="messages"):
            message = self.extract_stream_message(event)

            if message is None:
                continue

            message_key = self.stream_message_key(event, message)
            if message_key not in message_texts:
                message_order.append(message_key)
                message_texts[message_key] = ""
                thinking_open[message_key] = False
                # last_contents[message_key] = ""

            if self.message_has_tool_call(message):
                tool_call_messages.add(message_key)

            # 把 message.content 转成普通字符串
            # content = self.message_content_to_text(getattr(message, "content", "") or "")
            # print(content)
            # if not content:
            #     continue
            # 从“当前完整内容”里，计算出“相比上一次新增的部分”
            # delta = self.get_delta(last_contents.get(message_key, ""), content)
            parsed = self.message_content_to_text(message)
            if not parsed:
                continue

            parsed_type = parsed.get("type")
            delta = parsed.get("delta", "")
            # last_contents[message_key] = content

            if parsed_type == "reason":
                if not thinking_open.get(message_key, False):
                    delta = f"<think>{delta}"
                    thinking_open[message_key] = True

            elif parsed_type == "content":
                if thinking_open.get(message_key, False):
                    delta = f"</think>{delta}"
                    thinking_open[message_key] = False

            else:
                continue

            message_texts[message_key] = f"{message_texts.get(message_key, '')}{delta}"
            # 如果当前段消息是工具调用的消息，就不展示
            if message_key in tool_call_messages:
                continue
            # 不然就通过SSE推送事件
            publish_task_event(
                task_id,
                "agent_delta",
                {
                    "node": self.name,
                    "step_number": step_number,
                    "title": self.title,
                    "delta": delta,
                    "summary": message_texts[message_key],
                },
            )

        # debug:看一下key的数量
        print('-' * 20)
        for key in message_order:

            print(key)
            print(message_texts[key])
            print('-'*20)


        # 获取记录的最后一个非工具调用的message文本
        content = self.latest_stream_text(message_order, message_texts, tool_call_messages)
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

    # def stream_message_key(self, event: Any, message: Any) -> str:
    #     message_id = getattr(message, "id", None)
    #     if message_id:
    #         # print("KEY_SOURCE", {"source": "message.id", "value": str(message_id)})
    #         return str(message_id)
    #
    #     if isinstance(message, dict) and message.get("id"):
    #         print("KEY_SOURCE", {"source": "message['id']", "value": str(message["id"])})
    #         return str(message["id"])
    #
    #     metadata = event[1] if isinstance(event, tuple) and len(event) > 1 and isinstance(event[1], dict) else {}
    #
    #     for key in ("message_id", "run_id", "checkpoint_id"):
    #         if metadata.get(key):
    #             print("KEY_SOURCE", {"source": f"metadata.{key}", "value": str(metadata[key])})
    #             return str(metadata[key])
    #
    #     print("KEY_SOURCE", {"source": "fallback", "value": "__single_message__"})
    #     return "__single_message__"

    def stream_message_key(self, event: Any, message: Any) -> str:
        """为流式消息生成稳定 key，用来区分工具前后多条 assistant message。"""
        message_id = getattr(message, "id", None)
        if message_id:
            return str(message_id)
        if isinstance(message, dict) and message.get("id"):
            return str(message["id"])
        metadata = event[1] if isinstance(event, tuple) and len(event) > 1 and isinstance(event[1], dict) else {}
        for key in ("message_id", "run_id", "checkpoint_id"):
            if metadata.get(key):
                return str(metadata[key])
        return "__single_message__"

    def message_has_tool_call(self, message: Any) -> bool:
        """判断当前 assistant message/chunk 是否包含工具调用。"""
        for attr in ("tool_calls", "tool_call_chunks"):
            value = getattr(message, attr, None)
            if value:
                return True
        additional_kwargs = getattr(message, "additional_kwargs", None)
        if isinstance(additional_kwargs, dict) and additional_kwargs.get("tool_calls"):
            return True
        if isinstance(message, dict):
            for key in ("tool_calls", "tool_call_chunks"):
                if message.get(key):
                    return True
            additional = message.get("additional_kwargs")
            if isinstance(additional, dict) and additional.get("tool_calls"):
                return True
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type in {"tool_call", "tool_use", "function_call"}:
                    return True
                if item.get("tool_calls") or item.get("tool_call_chunks"):
                    return True
        return False

    def latest_stream_text(
        self,
        message_order: list[str],
        message_texts: dict[str, str],
        tool_call_messages: set[str],
    ) -> str:
        """返回最后一条不含工具调用的 assistant 文本。"""
        for message_key in reversed(message_order):
            if message_key in tool_call_messages:
                continue
            text = (message_texts.get(message_key) or "").strip()
            if text:
                return text
        for message_key in reversed(message_order):
            text = (message_texts.get(message_key) or "").strip()
            if text:
                return text
        return ""

    def message_content_to_text(self, message: Any) -> dict[str, str]:
        """
        从 streamed message/chunk 中提取 reasoning 或 content。

        返回：
            {"type": "reason", "delta": "..."}   表示思考内容
            {"type": "content", "delta": "..."}  表示正式回答内容
            {}                                  表示没有可展示文本
        """

        # 1. 优先解析 additional_kwargs.reasoning_content
        additional_kwargs = getattr(message, "additional_kwargs", None)
        if isinstance(additional_kwargs, dict):
            reasoning = additional_kwargs.get("reasoning_content")
            if reasoning:
                return {
                    "type": "reason",
                    "delta": str(reasoning),
                }

        # 2. 兼容 response_metadata.reasoning_content
        response_metadata = getattr(message, "response_metadata", None)
        if isinstance(response_metadata, dict):
            reasoning = response_metadata.get("reasoning_content")
            if reasoning:
                return {
                    "type": "reason",
                    "delta": str(reasoning),
                }

        # 3. 获取 content
        content = getattr(message, "content", None)

        if content is None and isinstance(message, dict):
            content = message.get("content")

        # 4. 如果 content 是 list，优先解析 reasoning block
        if isinstance(content, list):
            reason_parts: list[str] = []
            content_parts: list[str] = []

            for item in content:
                if isinstance(item, str):
                    content_parts.append(item)
                    continue

                if not isinstance(item, dict):
                    continue

                item_type = item.get("type")

                # 4.1 reasoning / thinking block
                if item_type in {"reasoning", "thinking", "reasoning_content"}:
                    text = item.get("text") or item.get("content") or item.get("reasoning_content")
                    if text:
                        reason_parts.append(str(text))

                    summary = item.get("summary")
                    if isinstance(summary, list):
                        for s in summary:
                            if isinstance(s, dict) and s.get("text"):
                                reason_parts.append(str(s["text"]))
                            elif isinstance(s, str):
                                reason_parts.append(s)

                    continue

                # 4.2 正式回答 text block
                if item_type in {None, "text"}:
                    text = item.get("text") or item.get("content")
                    if text:
                        content_parts.append(str(text))

            if reason_parts:
                return {
                    "type": "reason",
                    "delta": "".join(reason_parts),
                }

            if content_parts:
                return {
                    "type": "content",
                    "delta": "".join(content_parts),
                }

            return {}

        # 5. 如果 content 是 str，作为正式回答
        if isinstance(content, str) and content:
            return {
                "type": "content",
                "delta": content,
            }

        return {}

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
