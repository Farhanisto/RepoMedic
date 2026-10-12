from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Protocol


class TestResult:
    def __init__(
        self,
        phase: str,
        exit_code: int | None,
        timed_out: bool,
        passed: int,
        failed: int,
        skipped: int,
        output: str,
        error: str | None,
        changed_paths: list[str],
    ):
        self.phase = phase
        self.exit_code = exit_code
        self.timed_out = timed_out
        self.passed = passed
        self.failed = failed
        self.skipped = skipped
        self.output = output
        self.error = error
        self.changed_paths = changed_paths

    def __repr__(self) -> str:
        return (
            f"TestResult(phase={self.phase}, exit={self.exit_code}, "
            f"timed_out={self.timed_out}, passed={self.passed})"
        )


class TestRunner(Protocol):
    def run(self, workspace: str, command: list[str], timeout_seconds: int) -> TestResult:
        """Run tests in an isolated workspace.

        Args:
            workspace: Path to the workspace directory containing the project.
            command: Command and arguments to execute (e.g. ["python", "-m", "pytest", "-q"]).
            timeout_seconds: Maximum time in seconds before the command is killed.

        Returns:
            TestResult with phase, exit_code, timed_out flags, and counts.
        """
        ...


def _run_local(workspace: str, command: list[str], timeout_seconds: int) -> TestResult:
    """Run a command locally in the given workspace with timeout."""
    start = time.time()
    try:
        result = subprocess.run(
            command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        elapsed = time.time() - start
        output = (result.stdout or "")[-10000:]
        error = (result.stderr or "")[-10000:] if result.stderr else None
        return TestResult(
            phase="local",
            exit_code=result.returncode,
            timed_out=False,
            passed=0,
            failed=0,
            skipped=0,
            output=output,
            error=error,
            changed_paths=[],
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            phase="local",
            exit_code=None,
            timed_out=True,
            passed=0,
            failed=0,
            skipped=0,
            output="",
            error="Test execution timed out",
            changed_paths=[],
        )


def make_local_runner() -> callable:
    """Factory that returns a TestRunner calling _run_local."""
    def runner(workspace: str, command: list[str], timeout_seconds: int) -> TestResult:
        return _run_local(workspace, command, timeout_seconds)
    return runner