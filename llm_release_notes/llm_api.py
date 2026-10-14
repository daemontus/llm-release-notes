"""Client for OpenAI-compatible chat completion endpoints."""

import logging
import os
from typing import Optional

from openai import APIError, BadRequestError, OpenAI

from .exceptions import LLMAPIError

# If the server reports far fewer prompt tokens than we estimated, it has likely
# truncated the input silently (e.g. Ollama does this when the input exceeds its num_ctx).
SILENT_TRUNCATION_RATIO = 0.5


def get_llm_client(api_key_env: str, base_url: Optional[str]) -> OpenAI:
    """Create a client for the endpoint, reading the API key from the given environment variable."""
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise LLMAPIError(f"Environment variable {api_key_env} with the LLM API key is not set")
    return OpenAI(api_key=api_key, base_url=base_url)


def generate_text(
    content: str,
    model: str,
    api_key_env: str,
    base_url: Optional[str],
    estimated_tokens: int,
) -> str:
    """Send a single user message to the model and return the generated text."""
    log = logging.getLogger(__name__)
    client = get_llm_client(api_key_env, base_url)
    log.info("Sending prompt to model '%s' (estimated at most %d input tokens)", model, estimated_tokens)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
        )
    except BadRequestError as e:
        message = str(e).lower()
        if "context" in message or "too long" in message or "token" in message:
            raise LLMAPIError(
                f"The request does not fit into the context window of model '{model}'. "
                f"Check that max_context_tokens matches the model, or reduce it. Server response: {e}"
            ) from e
        raise LLMAPIError(f"The LLM endpoint rejected the request: {e}") from e
    except APIError as e:
        raise LLMAPIError(f"Failed to generate text: {e}") from e

    usage = resp.usage
    log.info("Prompt done. Usage: %s", usage)
    if usage and usage.prompt_tokens and usage.prompt_tokens < estimated_tokens * SILENT_TRUNCATION_RATIO:
        log.warning(
            "The server reports only %d input tokens, but roughly %d or more were expected. The input may have been "
            "silently truncated (e.g. Ollama does this when the input exceeds its configured context size).",
            usage.prompt_tokens,
            int(estimated_tokens * SILENT_TRUNCATION_RATIO),
        )

    if not resp.choices:
        raise LLMAPIError("The model returned no choices")
    choice = resp.choices[0]
    text = choice.message.content if choice.message else None
    if not text:
        raise LLMAPIError(f"The model returned no text (finish reason: {choice.finish_reason})")
    if choice.finish_reason == "length":
        log.warning(
            "The output was cut off because it reached the output token limit; the release notes are likely incomplete."
        )
    return text
