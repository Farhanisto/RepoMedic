from __future__ import annotations

from typing import Optional

from repomedic.models.prompts import (
    build_nano_prompt,
    build_super_prompt,
    build_ultra_prompt,
)
from repomedic.models.schemas import (
    ModelName,
    ModelRole,
    ModelResponseMetadata,
    ModelError,
    RateLimitError,
    APITimeoutError,
    MalformedOutputError,
)


class ModelRouter:
    """Routes model requests to the appropriate Nemotron model.

    Routing plan:
    - NANO: issue classification, short log summaries, report wording
    - SUPER: substantive patch review, root-cause analysis, edge-case suggestions
    - ULTRA: optional escalation for ambiguous, high-complexity cases only
    """

    def __init__(
        self,
        nano_model: ModelName = ModelName.NANO,
        super_model: ModelName = ModelName.SUPER,
        ultra_model: ModelName = ModelName.ULTRA,
        timeout_seconds: int = 30,
        max_retries: int = 2,
    ):
        self.nano_model = nano_model
        self.super_model = super_model
        self.ultra_model = ultra_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_count = 0

    def route_nano(self, diff_text: str, issue_text: str = "") -> tuple:
        """Route to NANO model for issue classification and short summaries.

        Returns (response_text, metadata).
        """
        # Build the prompt
        prompt = build_nano_prompt(diff_text, issue_text)

        # In a real implementation, this would call the OpenAI SDK
        # with the Token Factory base URL and the NANO model ID.
        # For now, return a mock response.
        response_text = self._mock_nano_response(diff_text)

        metadata = ModelResponseMetadata(
            model=self.nano_model,
            latency_ms=self._mock_latency(),
            fallback=False,
        )
        return response_text, metadata

    def route_super(
        self,
        repo_path: str,
        base_commit: str,
        patch_text: str,
        issue_text: str = "",
        test_selector: str = "",
    ) -> tuple:
        """Route to SUPER model for substantive patch review.

        Returns (structured_analysis, metadata).
        """
        # Build the prompt
        prompt = build_super_prompt(repo_path, base_commit, patch_text, issue_text, test_selector)

        # In a real implementation, this would call the OpenAI SDK
        # with the Token Factory base URL and the SUPER model ID.
        # For now, return a mock structured response.
        analysis = self._mock_super_response(patch_text)
        metadata = ModelResponseMetadata(
            model=self.super_model,
            latency_ms=self._mock_latency(),
            fallback=False,
        )
        return analysis, metadata

    def route_ultra(self, super_output: str) -> tuple:
        """Route to ULTRA model for optional escalation.

        Returns (enhanced_analysis, metadata).
        """
        # Build the prompt
        prompt = build_ultra_prompt(super_output)

        # ULTRA is optional and only used for ambiguous cases
        analysis = self._mock_ultra_response(super_output)
        metadata = ModelResponseMetadata(
            model=self.ultra_model,
            latency_ms=self._mock_latency(),
            fallback=True,
        )
        return analysis, metadata

    def _mock_nano_response(self, diff_text: str) -> str:
        """Mock NANO model response."""
        return f"NANO analysis of diff: {diff_text[:50]}... - issue classified as pagination bug"

    def _mock_super_response(self, patch_text: str) -> dict:
        """Mock SUPER model response."""
        return {
            "summary": "Patch fixes pagination index bug",
            "relevant_files": ["app.py"],
            "edge_cases": "Page size larger than item list",
            "suspicious_changes": None,
            "suggested_tests": ["test_third_page"],
            "uncertainties": "Edge case when page_size=0",
        }

    def _mock_ultra_response(self, super_output: str) -> dict:
        """Mock ULTRA model response."""
        return {
            "confirmed": True,
            "additional_issues": [],
            "human_review": False,
        }

    def _mock_latency(self) -> int:
        """Mock latency in milliseconds."""
        import random
        return random.randint(50, 500)