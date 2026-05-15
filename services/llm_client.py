from __future__ import annotations

import os
from typing import Any, Optional


class LLMClient:
    """Unified LLM client for API/local/streaming evolution."""

    def __init__(self) -> None:
        self.mode = os.getenv("DEEPINSIGHT_LLM_MODE", "real").lower().strip()
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        self.model = os.getenv("LLM_MODEL", "deepseek-chat")

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        tools: Optional[list[Any]] = None,
        stream: bool = False,
        timeout: int = 60,
    ) -> str:
        if stream:
            raise NotImplementedError("Streaming LLM output is not implemented yet")

        if self.mode == "mock":
            return self._mock_response(prompt)

        if self.mode in {"real", "api", "openai_compatible"}:
            return self._complete_openai_compatible(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                tools=tools,
                timeout=timeout,
            )

        if self.mode == "local":
            raise NotImplementedError("Local model calls are not implemented yet")

        raise RuntimeError(f"Unsupported LLM mode: {self.mode}")

    def _complete_openai_compatible(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        tools: Optional[list[Any]],
        timeout: int,
    ) -> str:
        if not self.api_key:
            raise RuntimeError(
                "Missing LLM_API_KEY or DEEPSEEK_API_KEY. "
                "Set DEEPINSIGHT_LLM_MODE=mock to test the pipeline without a real API key."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Missing openai dependency. Please install openai first.") from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "timeout": timeout,
        }
        if tools:
            kwargs["tools"] = tools

        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return content.strip() if content else ""

    def _mock_response(self, prompt: str) -> str:
        lower_prompt = prompt.lower()
        if "sql" in lower_prompt:
            return "SELECT * FROM information_schema.tables LIMIT 10;"
        if "报告" in prompt:
            return "# 数据分析报告\n\n当前处于 mock 模式，报告内容为占位文本。"
        if "分析" in prompt:
            return "当前处于 mock 模式，数据分析结论为占位文本。"
        return "当前处于 mock 模式，规划结果为占位文本。"
