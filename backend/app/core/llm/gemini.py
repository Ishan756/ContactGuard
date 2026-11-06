import asyncio
import json
import re
from typing import Any

from google import genai
from google.genai import types

from app.core.errors import (
    ConfigurationError,
    LLMResponseError,
    ProviderTimeoutError,
    ServiceUnavailableError,
)
from app.core.llm.base import LLMProvider
from app.core.logging import get_logger

logger = get_logger("contractguard.llm.gemini")

_CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _strip_code_fences(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        text = _CODE_FENCE_PATTERN.sub("", text).strip()
    return text


class GeminiLLMProvider(LLMProvider):
    """Gemini structured-output provider with configurable timeout, retries, and token limits."""

    def __init__(
        self,
        api_key: str | None,
        model_name: str,
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
        max_output_tokens: int = 8192,
    ) -> None:
        if not api_key or api_key in ("your-gemini-api-key-here", "test-gemini-key"):
            raise ConfigurationError(
                "GEMINI_API_KEY is not configured. Set GEMINI_API_KEY or explicitly enable "
                "the mock provider with LLM_PROVIDER=mock for tests/offline use.",
                details={"provider": "gemini"},
            )

        self._api_key = api_key
        self._model_name = model_name
        self._timeout_seconds = max(1.0, timeout_seconds)
        self._max_retries = max(0, max_retries)
        self._max_output_tokens = max(1, max_output_tokens)

        try:
            self._client = genai.Client(api_key=self._api_key)
        except Exception as exc:
            raise ConfigurationError(
                f"Failed to initialize Gemini client: {exc}",
                details={"provider": "gemini"},
            ) from exc

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _generate_once(
        self,
        system_instruction: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None,
    ) -> Any:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema,
            max_output_tokens=self._max_output_tokens,
            temperature=0.0,
        )
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=user_prompt,
            config=config,
        )
        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise LLMResponseError("Gemini returned an empty response.")

        try:
            return json.loads(_strip_code_fences(raw_text))
        except json.JSONDecodeError as exc:
            raise LLMResponseError(
                "Gemini returned malformed JSON.",
                details={"error": str(exc), "response_preview": raw_text[:500]},
            ) from exc

    async def generate_structured(
        self,
        *,
        system_instruction: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
    ) -> Any:
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        self._generate_once,
                        system_instruction,
                        user_prompt,
                        response_schema,
                    ),
                    timeout=self._timeout_seconds,
                )
            except TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "Gemini request timed out after %.1fs (attempt %d/%d)",
                    self._timeout_seconds,
                    attempt + 1,
                    self._max_retries + 1,
                )
            except LLMResponseError as exc:
                last_error = exc
                logger.warning(
                    "Gemini returned unprocessable output (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Gemini request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )

            if attempt < self._max_retries:
                await asyncio.sleep(min(2.0, 0.5 * (2**attempt)))

        if isinstance(last_error, TimeoutError):
            raise ProviderTimeoutError(
                f"Gemini request exceeded the {self._timeout_seconds:.0f}s timeout after "
                f"{self._max_retries + 1} attempt(s)."
            ) from last_error
        if isinstance(last_error, LLMResponseError):
            raise last_error
        raise ServiceUnavailableError(
            f"Gemini LLM request failed: {last_error}",
            details={"provider": "gemini", "model": self._model_name},
        ) from last_error
