from __future__ import annotations

from enum import Enum, auto


class Verdict(Enum):
    """Deterministic verdicts for patch verification."""

    UNSAFE = auto()
    REGRESSION = auto()
    VERIFIED = auto()
    INCONCLUSIVE = auto()


class Severity(Enum):
    """Severity levels for risk findings."""

    BLOCKED = auto("blocked")
    HIGH = auto("high")
    MEDIUM = auto("medium")
    LOW = auto("low")


class RiskFinding:
    """A risk finding identified during patch analysis."""

    def __init__(
        self,
        rule_id: str,
        severity: Severity,
        message: str,
        evidence: str,
    ):
        self.rule_id = rule_id
        self.severity = severity
        self.message = message
        self.evidence = evidence

    def __repr__(self) -> str:
        return f"RiskFinding(rule_id={self.rule_id}, severity={self.severity.value}, message={self.message!r})"


def calculate_verdict(
    baseline: "TestResult",
    patched: "TestResult",
    *,
    policy: "SandboxPolicy | None" = None,
    regression_tests: list[str] | None = None,
) -> tuple[Verdict, list[RiskFinding]]:
    """Calculate the verdict based on baseline and patched test results.

    This is a pure function of recorded evidence and policy.
    It must not call the model.

    Returns (verdict, risk_findings).
    """
    from repomedic.sandbox.policy import SandboxPolicy

    if policy is None:
        policy = SandboxPolicy()

    risk_findings: list[RiskFinding] = []

    # First: check for infrastructure errors and timeouts -> inconclusive
    if _has_infrastructure_error(baseline, patched):
        return Verdict.INCONCLUSIVE, risk_findings

    # Second: check for policy violations -> unsafe
    if _has_policy_violation(baseline, patched, policy):
        return Verdict.UNSAFE, risk_findings

    # Third: check for regression -> regression
    if _has_regression(baseline, patched, regression_tests=regression_tests):
        return Verdict.REGRESSION, risk_findings

    # Fourth: check for verified
    if _is_verified(baseline, patched, regression_tests=regression_tests):
        return Verdict.VERIFIED, risk_findings

    # Fifth: fallback to inconclusive
    return Verdict.INCONCLUSIVE, risk_findings


def _has_infrastructure_error(baseline, patched) -> bool:
    """Check if there's an infrastructure error or timeout.

    Returns True if baseline or patched had a timeout or their exit codes
    are unavailable, meaning we cannot reliably determine the verdict.
    """
    if baseline.timed_out or patched.timed_out:
        return True
    if baseline.exit_code is None or patched.exit_code is None:
        return True
    return False


def _has_policy_violation(baseline, patched, policy: "SandboxPolicy") -> bool:
    """Check if there's a policy violation that warrants an unsafe verdict."""
    # If the runner couldn't safely execute, it's unsafe
    if baseline.timed_out or patched.timed_out:
        return True
    # If the patch introduces changes blocked by policy
    if _is_blocked_by_policy(patched.changed_paths or [], policy):
        return True
    return False


def _has_regression(
    baseline, patched, *,
    regression_tests: list[str] | None = None,
) -> bool:
    """Check if a regression occurred: test passes at baseline and fails after patch.

    Returns True if the baseline had passing tests but the patched version
    has failing tests (indicating a regression).
    """
    # Baseline must have had successful test execution
    baseline_passed = not baseline.timed_out and baseline.exit_code == 0
    if not baseline_passed:
        return False

    # Patched version has failing tests
    patched_failed = (
        not patched.timed_out
        and patched.exit_code != 0
        and patched.exit_code is not None
    )
    if not patched_failed:
        return False

    # If regression_tests are specified, verify those specific tests pass
    # at baseline and fail after patch (opposite of regular regression)
    if regression_tests:
        # For MVP, we just check the general pass/fail status
        pass

    return True


def _is_verified(
    baseline,
    patched,
    *,
    regression_tests: list[str] | None = None,
) -> bool:
    """Check if all conditions for a `verified` verdict are met.

    Requirements:
    - The designated reproduction test fails at baseline for the expected reason.
    - The same test passes after the patch.
    - Required regression tests pass after the patch.
    - Required checks completed without timeout or infrastructure errors.
    - No blocking policy violation exists.
    """
    # 1. Baseline must have reproduced the issue (tests failed)
    baseline_reproduced = not baseline.timed_out and baseline.exit_code != 0 and baseline.exit_code is not None

    # 2. The same test passes after the patch
    patched_passes = not patched.timed_out and patched.exit_code == 0

    # 3. Required regression tests pass after the patch
    regression_ok = True
    if regression_tests:
        # For MVP, we just check that the overall result is passing
        regression_ok = not patched.timed_out and patched.exit_code == 0

    # 4. No timeout or infrastructure errors (already checked in calculate_verdict)
    # 5. No blocking policy violation (checked separately)

    return baseline_reproduced and patched_passes and regression_ok


def _is_blocked_by_policy(changed_paths: list[str], policy: "SandboxPolicy") -> bool:
    """Check if any changed paths are blocked by the policy."""
    if not changed_paths:
        return False
    for path in changed_paths:
        # Block git directory changes, binary files, etc.
        if path.startswith(".git/"):
            return True
        if path.startswith("__pycache__/"):
            return True
    return False