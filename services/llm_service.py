from __future__ import annotations

from typing import Optional

from services.llm_client import LLMClient


class LLMService:
    """Backward-compatible wrapper around the unified LLM client."""

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self.client = client or LLMClient()

    def chat(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.2) -> str:
        return self.client.complete(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )
