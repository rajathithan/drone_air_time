import logging

from google.adk.models.llm_response import LlmResponse
from google.genai import types


def make_on_model_error_callback(fallback_text: str | dict):
    """Creates an on_model_error callback that handles 429 rate-limit errors."""

    def _get_fallback_text(request_contents) -> str:
        if isinstance(fallback_text, str):
            return fallback_text

        req_str = str(request_contents).lower()
        best_keyword = None
        best_index = -1

        for keyword in fallback_text:
            if keyword == "default":
                continue
            idx = req_str.rfind(keyword.lower())
            if idx > best_index:
                best_index = idx
                best_keyword = keyword

        if best_keyword:
            return fallback_text[best_keyword]

        return fallback_text.get(
            "default",
            "**[System]** Quota exhausted. Please try again later.",
        )

    async def on_model_error_callback(
        callback_context,
        llm_request,
        error: Exception,
    ) -> LlmResponse | None:
        """Catches 429 / RESOURCE_EXHAUSTED errors from the model and returns a fallback."""
        error_str = str(error)
        if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
            logging.warning(f"[429 Handler] Caught rate-limit error: {error_str[:200]}")
            fallback = _get_fallback_text(llm_request)
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=fallback)],
                )
            )
        return None

    return on_model_error_callback
