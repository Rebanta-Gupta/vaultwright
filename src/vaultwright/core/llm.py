"""Talking to a local Ollama model, with the model's output treated as untrusted.

The model runs on localhost and gets no tools and no network. Its reply is
parsed as JSON against a schema and rejected if it doesn't fit — never
executed, never trusted to be well formed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_HOST = "http://localhost:11434"


class LLMError(Exception):
    """The model could not be reached, or would not answer usably."""


class Client(Protocol):
    """What refine.py needs from a model. Lets tests pass a fake."""

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class OllamaClient:
    """A thin wrapper over the ollama package.

    ``ollama`` is imported lazily so the rest of vaultwright — and its tests —
    work without it installed.
    """

    model: str = "qwen3:8b"
    host: str = DEFAULT_HOST
    temperature: float = 0.3
    retries: int = 2
    num_ctx: int = 8192

    def __post_init__(self) -> None:
        try:
            import ollama
        except ImportError as err:  # pragma: no cover - depends on install
            raise LLMError("The ollama package is not installed: uv add ollama") from err
        self._client = ollama.Client(host=self.host)

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Ask for JSON matching ``schema``; retry if the reply won't parse."""
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                response = self._client.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    format=schema,
                    options={"temperature": self.temperature, "num_ctx": self.num_ctx},
                )
            except Exception as err:  # ollama raises its own error types
                raise LLMError(
                    f"Could not reach Ollama at {self.host}: {err}\n"
                    "Is it running? Try: ollama serve"
                ) from err

            content = response["message"]["content"]
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as err:
                last_error = err
                continue
            if isinstance(parsed, dict):
                return parsed
            last_error = TypeError(f"expected a JSON object, got {type(parsed).__name__}")

        raise LLMError(
            f"{self.model} did not return usable JSON after "
            f"{self.retries + 1} attempts: {last_error}"
        )

    def available_models(self) -> list[str]:
        """Model names Ollama has pulled, for a friendlier error message."""
        try:
            listing = self._client.list()
        except Exception as err:
            raise LLMError(f"Could not reach Ollama at {self.host}: {err}") from err
        return [m.get("model", m.get("name", "")) for m in listing.get("models", [])]
