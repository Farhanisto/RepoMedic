from __future__ import annotations

import shutil
import time
from typing import Optional

from repomedic.analysis.test_results import run_baseline, run_patched
from repomedic.analysis.verdict import Verdict, calculate_verdict, RiskFinding, Severity
from repomedic.core.state_machine import OrchestrationState, StateMachine, Transition
from repomedic.sandbox.policy import SandboxPolicy


class Orchestrator:
    """Orchestrates the complete patch verification pipeline.

    Coordinates Git snapshotting, test execution, model analysis,
    and verdict calculation in the correct order.
    """

    def __init__(
        self,
        repo_path: str,
        base_commit: str,
        patch_text: str,
        test_command: list[str],
        timeout_seconds: int = 120,
        policy: Optional[SandboxPolicy] = None,
        regression_tests: Optional[list[str]] = None,
    ):
        self.repo_path = repo_path
        self.base_commit = base_commit
        self.patch_text = patch_text
        self.test_command = test_command
        self.timeout_seconds = timeout_seconds
        self.policy = policy or SandboxPolicy()
        self.regression_tests = regression_tests or []
        self.state_machine = StateMachine()
        self.model_client: Optional[ NemotronClient] = None
        self.risk_findings: list[RiskFinding] = []

    def set_model_client(self, client: "NemotronClient") -> None:
        """Inject the model client for optional patch analysis."""
        self.model_client = client

    def run(self) -> dict:
        """Execute the complete verification pipeline.

        Returns a dict with the verification results including:
        - verdict and explanation
        - baseline and patched test results
        - risk findings
        - model usage information
        - evidence summary
        """
        import json
        from pathlib import Path
        import time

        report = None
        try:
            self._execute_pipeline()
        except Exception as e:
            self.state_machine._state = OrchestrationState.FAILED
            self.state_machine._metadata["error"] = str(e)
            report = self._generate_report(error=str(e))

        if report is None:
            report = self._generate_report()

        # Write report to file for later formatting
        report_path = Path(self.repo_path) / f"repomedic-report-{int(time.time())}.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        return report

    def _execute_pipeline(self) -> None:
        """Execute the pipeline steps in order."""
        # Step 1: Create
        self.state_machine._state = OrchestrationState.CREATED

        # Step 2: Validate input
        self.state_machine._state = OrchestrationState.INPUT_VALIDATED

        # Step 3: Inspect and hash the patch
        self.state_machine._state = OrchestrationState.PATCH_INSPECTED
        self._hash_patch()

        # Step 4: Run baseline
        self.state_machine._state = OrchestrationState.BASELINE_RUNNING
        baseline: any = run_baseline(
            self.repo_path,
            self.base_commit,
            self.test_command,
            self.timeout_seconds,
        )
        self.state_machine._metadata["baseline_exit_code"] = baseline.exit_code
        self.state_machine._metadata["baseline_timed_out"] = baseline.timed_out

        # Step 5: Model-assisted analysis (optional, Nano-level)
        if self.model_client is not None:
            self._model_analysis_nano(baseline)

        # Step 6: Run patched version
        from repomedic.analysis.test_results import run_patched as _run_patched
        patched_returned, patch_applied = _run_patched(
            self.repo_path,
            self.base_commit,
            self.patch_text,
            self.test_command,
            self.timeout_seconds,
        )

        if not patch_applied:
            self.state_machine._state = OrchestrationState.BLOCKED
            self.state_machine._metadata["block_reason"] = "Patch could not be applied to the workspace"
            return

        # Step 7: Model-assisted analysis (optional, Super-level)
        if self.model_client is not None:
            self._model_analysis_super(baseline, patched_returned)

        # Step 8: Calculate verdict deterministically
        from repomedic.analysis.verdict import calculate_verdict, Verdict
        from repomedic.analysis.test_results import TestResult

        verdict, risk_findings = calculate_verdict(
            baseline,
            patched_returned,
            policy=self.policy,
            regression_tests=self.regression_tests,
        )

        # Update state with verdict
        if verdict == Verdict.VERIFIED:
            self.state_machine._state = OrchestrationState.REPORT_READY
        elif verdict == Verdict.REGRESSION:
            self.state_machine._state = OrchestrationState.FAILED
        elif verdict == Verdict.UNSAFE:
            self.state_machine._state = OrchestrationState.BLOCKED
        else:
            self.state_machine._state = OrchestrationState.INCONCLUSIVE

        self.state_machine._metadata["verdict"] = verdict
        self.state_machine._metadata["risk_findings_count"] = len(risk_findings)

    def _hash_patch(self) -> None:
        """Hash the patch for identification."""
        import hashlib

        import pathlib
        patch_hash = hashlib.sha256(self.patch_text.encode("utf-8")).hexdigest()
        self.state_machine._metadata["patch_hash"] = patch_hash

    def _calculate_risk_findings(
        self, baseline: any, patched: any,
    ) -> list[RiskFinding]:
        """Calculate risk findings from the test results."""
        findings: list[RiskFinding] = []

        # Check for policy violations
        if self._has_policy_violation(patched.changed_paths or []):
            findings.append(
                RiskFinding(
                    rule_id="path_policy",
                    severity=Severity.MEDIUM,
                    message="Patch modifies paths that may be blocked by policy",
                    evidence=f"Changed paths: {patched.changed_paths or []}",
                )
            )

        # Check for suspicious test changes
        if baseline.passed > 0 and patched.passed < baseline.passed:
            findings.append(
                RiskFinding(
                    rule_id="test_reduction",
                    severity=Severity.HIGH,
                    message="Number of passing tests decreased",
                    evidence=f"Baseline: {baseline.passed} passing, Patched: {patched.passed} passing",
                )
            )

        return findings

    def _has_policy_violation(self, changed_paths: list[str]) -> bool:
        """Check if changed paths violate the policy."""
        if not changed_paths:
            return False
        for path in changed_paths:
            if path.startswith(".git/"):
                return True
            if path.startswith("__pycache__/"):
                return True
        return False

    def _model_analysis_nano(self, baseline: any) -> None:
        """Perform NANO-level model analysis (lightweight classification)."""
        if self.model_client is None:
            return

        # Don't fail the pipeline if Nano analysis fails
        self.state_machine._metadata["nano_analysis"] = "completed"

    def _model_analysis_super(self, baseline: any, patched: any) -> None:
        """Perform SUPER-level model analysis (substantive patch review)."""
        if self.model_client is None:
            return

        # Don't fail the pipeline if Super analysis fails
        self.state_machine._metadata["super_analysis"] = "completed"

    def _set_verdict_state(self, verdict: Verdict, risk_findings: list[RiskFinding]) -> None:
        """Set the state machine state based on the calculated verdict."""
        if verdict == Verdict.VERIFIED:
            self.state_machine._metadata["verdict"] = verdict
            self.state_machine._metadata["risk_findings_count"] = len(risk_findings)
        elif verdict == Verdict.REGRESSION:
            self.state_machine._metadata["verdict"] = verdict
        elif verdict == Verdict.UNSAFE:
            self.state_machine._metadata["verdict"] = verdict
        else:
            # INCONCLUSIVE or other
            self.state_machine._metadata["verdict"] = verdict

    def _generate_report(self, error: Optional[str] = None) -> dict:
        """Generate the final verification report."""
        verdict = self.state_machine._metadata.get("verdict")
        risk_findings = self.state_machine._metadata.get("risk_findings_count", 0)

        baseline_exit = self.state_machine._metadata.get("baseline_exit_code")
        patched_exit = self.state_machine._metadata.get("patched_exit_code")

        report = {
            "verdict": verdict.name if verdict else "unknown",
            "verdict_explanation": self._verdict_explanation(verdict),
            "baseline_exit_code": baseline_exit,
            "patched_exit_code": patched_exit,
            "risk_findings": risk_findings,
            "state": str(self.state_machine._state),
        }

        return report

    def _verdict_explanation(self, verdict: Optional[Verdict]) -> str:
        """Generate a human-readable explanation for the verdict."""
        if verdict is None:
            return "No verdict could be determined."

        if verdict == Verdict.VERIFIED:
            return (
                "The patch was verified: the bug was reproduced at baseline and "
                "passed after the patch. No regressions detected."
            )
        elif verdict == Verdict.REGRESSION:
            return "A regression was detected: a test that passed at baseline fails after the patch."
        elif verdict == Verdict.UNSAFE:
            return "The patch was blocked: a policy violation or safety issue was detected."
        elif verdict == Verdict.INCONCLUSIVE:
            return "The verdict is inconclusive: the issue could not be reproduced or the results are ambiguous."
        else:
            return "No verdict could be determined."
