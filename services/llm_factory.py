from __future__ import annotations

import os
from typing import Any, Optional


def create_chat_model(
    model_name: Optional[str] = None,
    temperature: float = 0.2,
    streaming: bool = True,
    timeout: Optional[int] = 300,
    stream_chunk_timeout: Optional[int] = 300,
    **kwargs: Any,
) -> Any:
    """Create the shared chat model instance used by agents and simple LLM calls.

    This is intentionally small for now, but it gives us one place to add provider
    adapters later based on model name or environment configuration.
    """
    from langchain_openai import ChatOpenAI

    resolved_timeout = timeout
    if resolved_timeout is None:
        resolved_timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "300"))

    return ChatOpenAI(
        model=model_name or os.getenv("LLM_MODEL", "deepseek-chat"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        api_key=os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY"),
        temperature=temperature,
        timeout=resolved_timeout,
        streaming=streaming,
        stream_chunk_timeout=stream_chunk_timeout,
        **kwargs,
    )


def invoke_text(
    prompt: str,
    system_prompt: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.2,
    timeout: Optional[int] = None,
) -> str:
    """Invoke the shared chat model once and return plain text."""
    from langchain_core.messages import HumanMessage, SystemMessage

    model = create_chat_model(
        model_name=model_name,
        temperature=temperature,
        streaming=False,
        timeout=timeout,
    )
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=prompt))
    result = model.invoke(messages)
    return str(getattr(result, "content", "") or "").strip()
