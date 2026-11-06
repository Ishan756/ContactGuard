from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract interface for structured-output LLM providers.

    The provider contract is intentionally narrow: callers supply a trusted system
    instruction and an untrusted user prompt, and receive JSON data that must then
    be validated against a Pydantic schema by the caller.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Stable provider identifier (e.g. 'gemini', 'mock')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Effective model identifier used for observability and persistence."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        *,
        system_instruction: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
    ) -> Any:
        """Return structured JSON data generated from the supplied prompts.

        Implementations must keep the system instruction authoritative and must
        never execute or act on instructions found inside the user prompt.
        """
        pass
