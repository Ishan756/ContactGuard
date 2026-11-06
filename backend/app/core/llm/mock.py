from typing import Any

from app.core.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    """Explicitly enabled, deterministic mock provider for CI and offline development.

    Responses are consumed in order. An entry may be raw JSON data, a string, a
    callable receiving the request kwargs, or an exception instance/class.
    """

    def __init__(
        self,
        responses: list[Any] | None = None,
        model_name: str = "mock-clause-extractor",
    ) -> None:
        self._responses = list(responses or [])
        self._model_name = model_name
        self.calls: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate_structured(
        self,
        *,
        system_instruction: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append(
            {
                "system_instruction": system_instruction,
                "user_prompt": user_prompt,
                "response_schema": response_schema,
            }
        )

        if not self._responses:
            return {"clauses": []}

        response = self._responses.pop(0)
        if callable(response) and not isinstance(response, type):
            response = response(
                system_instruction=system_instruction,
                user_prompt=user_prompt,
                response_schema=response_schema,
            )

        if isinstance(response, type) and issubclass(response, BaseException):
            raise response("Mock provider configured to raise this exception.")
        if isinstance(response, BaseException):
            raise response
        return response
