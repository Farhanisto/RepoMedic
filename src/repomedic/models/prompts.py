from __future__ import annotations

from typing import Optional

from repomedic.models.schemas import ModelName, ModelResponseMetadata, ModelError, RateLimitError, APITimeoutError, MalformedOutputError


# Prompt templates for different model routing levels

NANO_PROMPT_TEMPLATE = """You are a Nemotron-powered code analysis assistant with access to the NANO model.

Your task is to analyze the following repository diff and provide a concise summary.

Repository diff:
{diff_text}

Issue description (if any): {issue_text}

Provide a brief response with:
1. Summary of the patch's intended behavior (2-3 sentences maximum).
2. Any suspicious changes or potential risks (1 sentence maximum).
3. Missing edge cases you can identify (1 sentence maximum, or "None identified").

Keep the total response under 200 tokens. Output only the analysis text, no reasoning or additional formatting.
"""

SUPER_PROMPT_TEMPLATE = """You are a Nemotron-powered code analysis assistant with access to the SUPER model.

Your task is to provide a substantive patch review, including root-cause analysis and edge-case suggestions.

Repository: {repo_path}
Base commit: {base_commit}
Patch: {patch_text}

Issue description (if any): {issue_text}

Required reproduction test: {test_selector}

Please provide:
1. Summary of intended behavior changes from the patch.
2. Files and functions relevant to the patch.
3. Potential missing edge cases and why they might matter.
4. Suspicious changes with supporting evidence (if any).
5. Suggested additional tests with rationale.
6. Uncertainties or ambiguous areas.

Output as structured JSON matching the analysis schema. Keep each field concise.
"""

ULTRA_PROMPT_TEMPLATE = """You are a Nemotron-powered code analysis assistant with access to the ULTRA model.

This is an optional escalation for ambiguous or high-complexity cases only.

{super_output}

Please review the above analysis and either:
- Confirm the analysis is complete and correct, or
- Identify additional issues not previously considered, or
- Flag the case for human review.

Output as structured JSON or a brief text summary.
"""


def build_nano_prompt(diff_text: str, issue_text: str = "") -> str:
    """Build a prompt for the NANO model (issue classification, short summaries)."""
    return NANO_PROMPT_TEMPLATE.format(diff_text=diff_text, issue_text=issue_text)


def build_super_prompt(
    repo_path: str,
    base_commit: str,
    patch_text: str,
    issue_text: str = "",
    test_selector: str = "",
) -> str:
    """Build a prompt for the SUPER model (substantive patch review)."""
    return SUPER_PROMPT_TEMPLATE.format(
        repo_path=repo_path,
        base_commit=base_commit,
        patch_text=patch_text,
        issue_text=issue_text,
        test_selector=test_selector,
    )


def build_ultra_prompt(super_output: str) -> str:
    """Build a prompt for the ULTRA model (optional escalation)."""
    return ULTRA_PROMPT_TEMPLATE.format(super_output=super_output)