from __future__ import annotations

from enum import Enum
from typing import Optional


class ModelName(Enum):
    """Nemotron model IDs available through Token Factory."""

    NANO = "nemotron-nano"
    SUPER = "nemotron-super"
    ULTRA = "nemotron-ultra"


class ModelRole(Enum):
    """Routing roles for different model capabilities."""

    NANO = "issue_classification"
    SUPER = "patch_review"
    ULTRA = "escalation"


class TokenUsage:
    """Token usage information from a model response."""

    def __init__(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens

    def __repr__(self) -> str:
        return f"TokenUsage(prompt={self.prompt_tokens}, completion={self.completion_tokens}, total={self.total_tokens})"


class ModelResponseMetadata:
    """Metadata returned from a model call."""

    def __init__(
        self,
        model: ModelName,
        latency_ms: int,
        usage: TokenUsage | None = None,
        fallback: bool = False,
    ):
        self.model = model
        self.latency_ms = latency_ms
        self.usage = usage
        self.fallback = fallback

    def __repr__(self) -> str:
        return f"ModelResponseMetadata(model={self.model.name}, latency={self.latency_ms}ms, fallback={self.fallback})"


class ModelError(Exception):
    """Base class for model-related errors."""

    pass


class RateLimitError(ModelError):
    """Raised when the model rate limit is exceeded."""

    pass


class APITimeoutError(ModelError):
    """Raised when the model API request times out."""

    pass


class MalformedOutputError(ModelError):
    """Raised when the model output cannot be parsed into the expected schema."""

    pass