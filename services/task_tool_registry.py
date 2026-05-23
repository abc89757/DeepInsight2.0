"""任务级 MCP 工具注册表。

这个模块负责为每个分析任务启动、保存和关闭 MCP client。LangGraph state 里只保存工具元信息，
真正的 client、子进程和 LangChain tools 都保存在这个运行时注册表里。
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class TaskToolGroup:
    """单个任务下某一类工具的运行时对象。"""

    name: str
    client: Any
    tools: List[Any]
    tool_file: Path


_TASK_TOOL_REGISTRY: dict[str, dict[str, TaskToolGroup]] = {}
_LOCK = threading.Lock()


def start_skill_tool_clients(task_id: str | None, skill_name: str, skill_dir: Path) -> Dict[str, Any]:
    """为当前任务启动选中 Skill 下的 MCP 工具。

    输入:
        task_id: 当前分析任务 ID；为空时不会启动工具。
        skill_name: 已选中的 Skill 名称。
        skill_dir: Skill 所在目录。

    输出:
        可写入 state 的工具元信息，不包含 client 等不可序列化对象。
    """
    if not task_id:
        return {}

    close_task_tool_clients(task_id)

    tool_groups: Dict[str, Any] = {}
    data_tool_file = _find_first_existing(
        [
            skill_dir / "tool" / "tool.py",
            skill_dir / "tool" / "data_tools.py",
            skill_dir / "tools" / "data_tools.py",
        ]
    )

    if data_tool_file:
        group = _start_stdio_tool_group(
            group_name="data_processor",
            server_name=f"{skill_name}_data_tools",
            tool_file=data_tool_file,
        )
        with _LOCK:
            _TASK_TOOL_REGISTRY.setdefault(task_id, {})[group.name] = group
        tool_groups[group.name] = {
            "enabled": True,
            "tool_file": str(data_tool_file),
            "tool_names": [getattr(tool, "name", str(tool)) for tool in group.tools],
        }

    chart_tool_file = _find_first_existing(
        [
            skill_dir / "tool" / "chart_tools.py",
            skill_dir / "tools" / "chart_tools.py",
        ]
    )

    if chart_tool_file:
        group = _start_stdio_tool_group(
            group_name="chart_generator",
            server_name=f"{skill_name}_chart_tools",
            tool_file=chart_tool_file,
        )
        with _LOCK:
            _TASK_TOOL_REGISTRY.setdefault(task_id, {})[group.name] = group
        tool_groups[group.name] = {
            "enabled": True,
            "tool_file": str(chart_tool_file),
            "tool_names": [getattr(tool, "name", str(tool)) for tool in group.tools],
        }

    return tool_groups


def get_task_tools(task_id: str | None, group_name: str) -> List[Any]:
    """读取某个任务下指定工具组的 LangChain tools。

    输入:
        task_id: 当前分析任务 ID。
        group_name: 工具组名称，例如 `data_processor`。

    输出:
        LangChain tool 对象列表；如果未加载则返回空列表。
    """
    if not task_id:
        return []
    with _LOCK:
        group = _TASK_TOOL_REGISTRY.get(task_id, {}).get(group_name)
        return list(group.tools) if group else []


def close_task_tool_clients(task_id: str | None) -> None:
    """关闭某个任务启动过的所有 MCP client。

    输入:
        task_id: 当前分析任务 ID；为空时不处理。

    输出:
        无返回值；会尽力关闭并移除注册表中的运行时对象。
    """
    if not task_id:
        return
    with _LOCK:
        groups = list(_TASK_TOOL_REGISTRY.pop(task_id, {}).values())

    for group in groups:
        try:
            _run_async(_close_client(group.client))
        except Exception as exc:
            print(f"[task {task_id}] close MCP tool group {group.name} failed: {exc}", file=sys.stderr)


def _find_first_existing(paths: list[Path]) -> Path | None:
    """从候选路径中找到第一个存在的文件。

    输入:
        paths: 按优先级排列的候选文件路径。

    输出:
        第一个存在的路径；如果都不存在则返回 None。
    """
    for path in paths:
        if path.exists():
            return path
    return None


def _start_stdio_tool_group(group_name: str, server_name: str, tool_file: Path) -> TaskToolGroup:
    """启动一个 stdio MCP server 并转换出 LangChain tools。

    输入:
        group_name: 注册表中的工具组名称。
        server_name: MCP server 名称。
        tool_file: 要作为 stdio server 启动的 Python 文件。

    输出:
        包含 MCP client 和 LangChain tools 的运行时工具组对象。
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:
        raise RuntimeError(
            "检测到 Skill 工具文件，但当前环境缺少 langchain-mcp-adapters。"
            "请先安装：pip install langchain-mcp-adapters"
        ) from exc

    config = {
        server_name: {
            "command": sys.executable,
            "args": [str(tool_file.resolve())],
            "transport": "stdio",
        }
    }
    client = MultiServerMCPClient(config)
    tools = _run_async(_enter_client_and_get_tools(client))
    return TaskToolGroup(name=group_name, client=client, tools=list(tools), tool_file=tool_file)


async def _enter_client_and_get_tools(client: Any) -> list[Any]:
    """读取 MCP client 暴露的 LangChain tools。

    输入:
        client: MultiServerMCPClient 实例。

    输出:
        LangChain tool 对象列表。
    """
    tools = client.get_tools()
    if inspect.isawaitable(tools):
        tools = await tools
    return list(tools or [])


async def _close_client(client: Any) -> None:
    """关闭 MCP client。

    输入:
        client: 需要关闭的 MCP client 对象。

    输出:
        无返回值。
    """
    close_method = getattr(client, "aclose", None)
    if close_method:
        result = close_method()
        if inspect.isawaitable(result):
            await result
        return

    close_method = getattr(client, "close", None)
    if close_method:
        close_method()


def _run_async(awaitable: Any) -> Any:
    """在同步节点代码中执行异步 MCP 操作。

    输入:
        awaitable: 需要运行的协程对象。

    输出:
        协程运行结果。
    """
    return asyncio.run(awaitable)
