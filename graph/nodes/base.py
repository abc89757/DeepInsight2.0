from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from services.llm_client import LLMClient
from services.task_persistence import fail_task_step, finish_task_step, start_task_step


class BaseNode(ABC):
    """Base contract for every LangGraph node."""

    name: str = ""
    title: str = ""
    description: str = ""

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} is missing name")
        if not self.title:
            raise ValueError(f"{self.__class__.__name__} is missing title")

        task_id = state.get("task_id")
        step_id: Optional[str] = None

        if task_id:
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

            if step_id:
                finish_task_step(
                    step_id=step_id,
                    output_summary=self.summarize_output(output),
                    output_json=self.step_output(output),
                )

            return output
        except Exception as exc:
            if step_id:
                fail_task_step(step_id, str(exc))
            raise

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute node logic and return fields that should be merged into state."""

    def summarize_input(self, state: Dict[str, Any]) -> Optional[str]:
        return None

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        return self.description or self.title

    def step_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        return output


class ToolNode(BaseNode):
    """Deterministic pipeline node that does not directly require an LLM."""


class AgentNode(BaseNode):
    """Node whose core work is performed by an LLM-backed service."""

    temperature: float = 0.2
    tools: list[Any] = []
    system_prompt: Optional[str] = None
    stream: bool = False
    timeout: int = 60

    def __init__(self) -> None:
        self.llm_client = LLMClient()

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the full agent workflow and return state updates."""

    @abstractmethod
    def build_prompt(self, state: Dict[str, Any]) -> str:
        """Build the prompt for this agent node."""

    @abstractmethod
    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        """Call the LLM for this agent node."""
