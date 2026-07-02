"""Strict variant of marker's GoogleGeminiService that raises on LLM failure.

Upstream marker (``marker.services.gemini.GoogleGeminiService``) silently
returns ``{}`` on APIError, generic Exception, or repeated JSON decode
failures, which makes "LLM unreachable / misconfigured" indistinguishable
from "LLM had nothing useful to add for this block." This subclass
re-implements ``__call__`` to raise on those failure paths instead.

This module is referenced by dotted path from ``rkb.services.translate``
and imported lazily by marker via ``strings_to_classes``.
"""

from __future__ import annotations

import json
import time

from google.genai import types
from google.genai.errors import APIError
from marker.services.gemini import GoogleGeminiService

_RETRYABLE_CODES = (429, 443, 503)


class StrictGoogleGeminiService(GoogleGeminiService):
    """GoogleGeminiService that raises instead of swallowing LLM errors."""

    def __call__(
        self,
        prompt,
        image,
        block,
        response_schema,
        max_retries=None,
        timeout=None,
    ):
        if max_retries is None:
            max_retries = self.max_retries
        if timeout is None:
            timeout = self.timeout

        client = self.get_google_client(timeout=timeout)
        image_parts = self.format_image_for_llm(image)

        total_tries = max_retries + 1
        temperature = 0
        for tries in range(1, total_tries + 1):
            config = {
                "temperature": temperature,
                "response_schema": response_schema,
                "response_mime_type": "application/json",
            }
            if self.max_output_tokens:
                config["max_output_tokens"] = self.max_output_tokens
            if self.thinking_budget is not None:
                config["thinking_config"] = types.ThinkingConfig(
                    thinking_budget=self.thinking_budget,
                )

            try:
                responses = client.models.generate_content(
                    model=self.gemini_model_name,
                    contents=[*image_parts, prompt],
                    config=config,
                )
                output = responses.candidates[0].content.parts[0].text
                total_tokens = responses.usage_metadata.total_token_count
                if block:
                    block.update_metadata(
                        llm_tokens_used=total_tokens,
                        llm_request_count=1,
                    )
                return json.loads(output)
            except APIError as e:
                if e.code in _RETRYABLE_CODES and tries < total_tries:
                    time.sleep(tries * self.retry_wait_time)
                    continue
                raise
            except json.JSONDecodeError:
                if tries < total_tries:
                    temperature = 0.2
                    continue
                raise

        raise RuntimeError("Gemini call exhausted retries without success")
