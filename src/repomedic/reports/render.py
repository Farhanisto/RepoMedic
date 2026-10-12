from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from repomedic.analysis.verdict import Verdict


def _generate_run_id() -> str:
    """Generate a unique run ID."""
    return f"repomedic-{int(time.time())}"


def _format_timestamp() -> str:
    """Format the current timestamp."""
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


def render_json(report_data: Dict[str, Any]) -> str:
    """Render the verification result as JSON."""
    # Ensure all values are JSON-serializable
    serializable = _make_serializable(report_data)
    return json.dumps(serializable, indent=2)


def render_markdown(report_data: Dict[str, Any]) -> str:
    """Render the verification result as Markdown."""
    lines: list[str] = []

    # Header
    lines.append(f"# RepoMedic Verification Report")
    lines.append(f"**Run ID:** {report_data.get('run_id', 'N/A')}")
    lines.append(f"**Timestamp:** {report_data.get('timestamp', 'N/A')}")
    lines.append("")

    # Verdict
    verdict = report_data.get("verdict", "unknown")
    lines.append(f"## Verdict")
    lines.append(f"**Verdict:** {verdict}")
    lines.append(f"**Explanation:** {report_data.get('verdict_explanation', 'N/A')}")
    lines.append("")

    # Baseline and patched test results
    lines.append("## Test Results")
    lines.append(f"- **Baseline exit code:** {report_data.get('baseline_exit_code', 'N/A')}")
    lines.append(f"- **Patched exit code:** {report_data.get('patched_exit_code', 'N/A')}")
    lines.append("")

    # Risk findings
    risk_findings = report_data.get("risk_findings", [])
    lines.append("## Risk Findings")
    if risk_findings:
        for i, finding in enumerate(risk_findings, 1):
            lines.append(f"### Finding {i}")
            lines.append(f"- **Rule ID:** {finding.get('rule_id', 'N/A')}")
            lines.append(f"- **Severity:** {finding.get('severity', 'N/A')}")
            lines.append(f"- **Message:** {finding.get('message', 'N/A')}")
            lines.append(f"- **Evidence:** {finding.get('evidence', 'N/A')}")
    else:
        lines.append("No risk findings.")
    lines.append("")

    # Model usage
    lines.append("## Model Usage")
    lines.append(f"- **Model IDs:** {report_data.get('model_ids', 'N/A')}")
    lines.append(f"- **Latency:** {report_data.get('latency_ms', 'N/A')}ms")
    lines.append(f"- **Token Usage:** {report_data.get('token_usage', 'N/A')}")
    lines.append("")

    # Evidence summary
    lines.append("## Evidence Summary")
    lines.append(f"- **Patch SHA-256:** {report_data.get('patch_hash', 'N/A')}")
    lines.append(f"- **Changed files:** {report_data.get('changed_files', 'N/A')}")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*Report generated: {_format_timestamp()}*")
    lines.append(f"*This report is based on deterministic evidence and explicit rules, not the model's opinion.*")

    return "\n".join(lines)


def _make_serializable(obj: Any) -> Any:
    """Ensure values are JSON-serializable."""
    if isinstance(obj, dict):
        return {str(k): _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(item) for item in obj]
    elif isinstance(obj, Verdict):
        return obj.name
    elif isinstance(obj, bool):
        return obj
    elif isinstance(obj, float | int | str | type(None)):
        return obj
    else:
        return str(obj)


def create_report(
    *,
    run_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    verdict: Optional[Verdict] = None,
    verdict_explanation: str = "",
    baseline_exit_code: Optional[int] = None,
    patched_exit_code: Optional[int] = None,
    risk_findings: list = None,
    model_ids: str = "",
    latency_ms: int = 0,
    token_usage: str = "",
    patch_hash: str = "",
    changed_files: str = "",
) -> Dict[str, str]:
    """Create a report data dict and render it as JSON and Markdown.

    Returns a dict with 'json' and 'markdown' keys.
    """
    risk_findings = risk_findings or []
    report = {
        "run_id": run_id or _generate_run_id(),
        "timestamp": timestamp or _format_timestamp(),
        "verdict": verdict.name if verdict else "inconclusive",
        "verdict_explanation": verdict_explanation,
        "baseline_exit_code": baseline_exit_code,
        "patched_exit_code": patched_exit_code,
        "risk_findings": risk_findings,
        "model_ids": model_ids,
        "latency_ms": latency_ms,
        "token_usage": token_usage,
        "patch_hash": patch_hash,
        "changed_files": changed_files,
    }

    return {
        "json": render_json(report),
        "markdown": render_markdown(report),
    }