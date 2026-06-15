"""Inference backends. Production uses a private OpenAI-compatible vLLM endpoint."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..errors import StylePipelineError

SYSTEM_PROMPT = (
    "Write a short synthetic social post in a bold, emphatic rhetorical style. "
    "Do not name, impersonate, or claim to speak for any real person. "
    "Do not present the response as a real quote or official statement."
)


@dataclass
class StubBackend:
    """Deterministic backend for tests; never enabled silently in production."""

    model_version: str = "synthetic-stub-0"

    def generate(self, *, topic: str, intent: str, length: str, historical_context: str) -> str:
        return (
            f"A strong plan for {topic}: clear goals, real accountability, and results people "
            "can measure. Let us get to work!"
        )


@dataclass
class VLLMBackend:
    base_url: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 30.0

    @property
    def model_version(self) -> str:
        return self.model

    def generate(self, *, topic: str, intent: str, length: str, historical_context: str) -> str:
        prompt = "\n".join(
            (
                f"Topic: {topic}",
                f"Intent: {intent}",
                f"Length: {length}",
                f"Time context: {historical_context}",
            )
        )
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.8,
                "top_p": 0.9,
                "max_tokens": 160,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.base_url.rstrip("/") + "/v1/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise StylePipelineError(f"vLLM request failed: {exc}") from exc
        try:
            return str(result["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise StylePipelineError("vLLM returned an unexpected response shape") from exc
