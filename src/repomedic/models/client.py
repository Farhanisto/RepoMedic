from __future__ import annotations

import time
from typing import Optional, get_type_hints

import openai
from openai import APIError, APITimeoutError, RateLimitError

from repomedic.models.schemas import (
    ModelName,
    ModelResponseMetadata,
    ModelError,
    RateLimitError as ModelRateLimitError,
    APITimeoutError as ModelAPITimeoutError,
    MalformedOutputError,
    TokenUsage,
)
from repomedic.models.prompts import build_nano_prompt, build_super_prompt, build_ultra_prompt
from repomedic.models.routing import ModelRouter


class NemotronClient:
    """Client for interacting with Nemotron models through Token Factory.

    Uses the OpenAI Python SDK with the Token Factory base URL and
    verified model IDs from the account catalog.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        nano_model: ModelName = ModelName.NANO,
        super_model: ModelName = ModelName.SUPER,
        ultra_model: ModelName = ModelName.ULTRA,
        timeout_seconds: int = 30,
        max_retries: int = 2,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.nano_model = nano_model
        self.super_model = super_model
        self.ultra_model = ultra_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

        # Configure the OpenAI client with Token Factory settings
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )
        self.router = ModelRouter(
            nano_model=nano_model,
            super_model=super_model,
            ultra_model=ultra_model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    def analyze_patch(
        self,
        repo_path: str,
        base_commit: str,
        patch_text: str,
        issue_description: str = "",
        test_selector: str = "",
    ) -> tuple:
        """Perform a full model-assisted analysis of a patch.

        Uses NANO for initial classification, SUPER for substantive review,
        and ULTRA optionally for escalation.

        Returns (analysis_dict, ModelResponseMetadata).
        """
        # Step 1: NANO - initial classification
        nano_response, nano_metadata = self.router.route_nano(
            patch_text, issue_description
        )
        metadata = ModelResponseMetadata(
            model=nano_metadata.model,
            latency_ms=nano_metadata.latency_ms,
            fallback=nano_metadata.fallback,
        )

        # Step 2: SUPER - substantive patch review
        super_analysis, super_metadata = self.router.route_super(
            repo_path,
            base_commit,
            patch_text,
            issue_description,
            test_selector,
        )
        metadata.latency_ms = int(
            metadata.latency_ms + super_metadata.latency_ms / 2
        )

        # Step 3: Optionally escalate to ULTRA
        ultra_analysis = None
        if self._should_escalate_to_ultra(super_analysis):
            ultra_analysis, ultra_metadata = self.router.route_ultra(
                self._serialize_super_output(super_analysis)
            )
            metadata.fallback = ultra_metadata.fallback

        # Combine results into a structured analysis
        analysis = self._combine_analysis(
            nano_response, super_analysis, ultra_analysis
        )

        return analysis, metadata

    def _should_escalate_to_ultra(self, super_analysis: dict) -> bool:
        """Determine if ULTRA escalation is needed."""
        # MVP: escalate only for ambiguous cases
        # Heuristic: if uncertainties field is present and non-empty
        uncertainties = super_analysis.get("uncertainties", "")
        return uncertainties and uncertainties.strip() != ""

    def _serialize_super_output(self, super_analysis: dict) -> str:
        """Serialize SUPER output for ULTRA prompt."""
        import json

        return json.dumps(super_analysis, indent=2)

    def _combine_analysis(
        self,
        nano_response: str,
        super_analysis: dict,
        ultra_analysis: dict | None,
    ) -> dict:
        """Combine model outputs into a single analysis dict."""
        base = {
            "nano_summary": nano_response,
            "super_summary": super_analysis.get("summary", ""),
            "relevant_files": super_analysis.get("relevant_files", []),
            "edge_cases": super_analysis.get("edge_cases", ""),
            "suspicious_changes": super_analysis.get("suspicious_changes"),
            "suggested_tests": super_analysis.get("suggested_tests", []),
            "uncertainties": super_analysis.get("uncertainties", ""),
        }

        if ultra_analysis:
            base["ultra_escalation"] = {
                "confirmed": ultra_analysis.get("confirmed", False),
                "additional_issues": ultra_analysis.get("additional_issues", []),
            }

        return base

    def count_tokens(self, text: str) -> int:
        """Estimate token count for a text string.

        Uses a simple character-based estimate for the MVP.
        """
        # Rough estimate: 1 token per ~4 characters
        return max(1, len(text) // 4)

    def validate_response(
        self, response: dict, expected_fields: list[str] | None = None
    ) -> dict:
        """Validate that the model response matches the expected schema.

        Raises MalformedOutputError if the response is invalid.
        """
        if not isinstance(response, dict):
            raise MalformedOutputError("Response is not a dictionary")

        if expected_fields:
            for field in expected_fields:
                if field not in response:
                    raise MalformedOutputError(f"Missing essential field: {field}")

        return response

    def handle_api_error(self, error: Exception) -> None:
        """Handle API errors from the model provider.

        Converts OpenAI errors to NemotinClient-specific exceptions.
        """
        if isinstance(error, RateLimitError):
            raise ModelRateLimitError(
                f"Rate limit exceeded: {error}"
            ) from error
        elif isinstance(error, APITimeoutError):
            raise ModelAPITimeoutError(
                f"API request timed out: {error}"
            ) from error
        elif isinstance(error, APIError):
            raise ModelError(f"API error: {error}") from error
        else:
            raise ModelError(f"Unexpected error: {error}") from error