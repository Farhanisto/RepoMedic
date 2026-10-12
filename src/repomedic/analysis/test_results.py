from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from repomedic.sandbox.runner import TestResult, make_local_runner


def _checkout_commit(repo_path: str | Path, base_commit: str, target_dir: str) -> Path:
    """Check out a commit into a target directory, returning the workspace path."""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["git", "clone", "--no-local", "--quiet", str(repo_path), str(target)],
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        ["git", "checkout", base_commit, "--quiet"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        msg = f"Failed to checkout {base_commit}: {result.stderr}"
        raise RuntimeError(msg)

    return target


def _apply_patch_direct(workspace: Path, patch_text: str) -> bool:
    """Apply a patch by directly modifying file contents.

    For the MVP, handles the common case of a single hunk that
    replaces one line in a file, using the unified diff format.
    """
    # Try git apply first
    patch_file = workspace / ".repomedic.patch"
    patch_file.write_text(patch_text)

    result = subprocess.run(
        ["git", "apply", str(patch_file)],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    patch_file.unlink(missing_ok=True)
    if result.returncode == 0:
        return True

    # Fallback: apply via direct content replacement
    return _apply_patch_by_content_replacement(workspace, patch_text)


def _apply_patch_by_content_replacement(workspace: Path, patch_text: str) -> bool:
    """Fallback: apply patch by reading/writing file content directly.

    Parses the unified diff to find the target file and the old/new lines,
    then replaces the old line content with the new line content.
    """
    lines = patch_text.splitlines()
    i = 0

    while i < len(lines):
        # Find the --- line to get the file path
        if lines[i].startswith("--- ") or lines[i].startswith("diff --/"):
            file_path = lines[i][4:] if lines[i].startswith("--- ") else ""
            # Strip 'a/' or 'b/' prefix if present (git diff convention)
            if file_path.startswith("a/"):
                file_path = file_path[2:]
            elif file_path.startswith("b/"):
                file_path = file_path[2:]
            i += 1
            # Skip the +++ line
            if i < len(lines) and lines[i].startswith("+++ "):
                i += 1
        else:
            i += 1
            continue

        # Now find the @@ hunk header
        while i < len(lines) and not lines[i].startswith("@@"):
            i += 1
        if i >= len(lines):
            return False

        # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
        hunk_match = re.match(
            r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", lines[i]
        )
        if not hunk_match:
            i += 1
            continue

        old_start = hunk_match.group(1)  # old start line (1-indexed)
        old_count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
        new_start = int(hunk_match.group(3))  # new start line (1-indexed)

        # Collect the hunk content lines
        i += 1
        old_lines: list[str] = []  # lines to remove (start with "-")
        new_lines: list[str] = []  # lines to add (start with "+")
        context_lines: list[str] = []  # lines to keep (start with " ")

        while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith(
            "--- "
        ) and not lines[i].startswith("diff --/"):
            line = lines[i]
            if line.startswith("-"):
                old_lines.append(line[1:])  # content after "-"
            elif line.startswith("+"):
                new_lines.append(line[1:])  # content after "+"
            elif line.startswith(" "):
                context_lines.append(line[1:])  # content after " "
            # else: ignore other lines
            i += 1

        if not old_lines or not new_lines:
            return False

        # Find the target file
        target_file = workspace / file_path
        if not target_file.exists():
            return False

        # Read current content
        content = target_file.read_text()
        content_lines = content.splitlines()

        # Apply removals and additions
        # For MVP: find the first old_line position in the content
        # and replace it with the first new_line
        for old_line in old_lines:
            # Find the line in content that matches (or partially matches) the old line
            found = False
            for idx, cline in enumerate(content_lines):
                if old_line in cline:
                    # Replace this line
                    content_lines[idx] = new_lines[0] if new_lines else ""
                    found = True
                    break
            if not found:
                # Try partial match: just remove the old line
                # and don't add a replacement at this position
                pass

        # Write back the modified content
        target_file.write_text("\n".join(content_lines) + ("\n" if content_lines else ""))

        return True

    return False


def _clone_and_apply_patch(
    repo_path: str | Path,
    base_commit: str,
    patch_text: str,
    target_dir: str,
) -> tuple[Path, bool]:
    """Clone workspace at base_commit and apply patch.

    Returns (workspace_path, patch_applied).
    """
    target = _checkout_commit(repo_path, base_commit, target_dir)
    patch_applied = _apply_patch_direct(target, patch_text)
    return target, patch_applied


def run_baseline(
    repo_path: str | Path,
    base_commit: str,
    test_command: list[str],
    timeout_seconds: int = 120,
) -> TestResult:
    """Run the test command at the base commit (baseline)."""
    workspace = _checkout_commit(repo_path, base_commit, "/tmp/repomedic-baseline")
    runner = make_local_runner()
    result = runner(str(workspace), test_command, timeout_seconds)
    shutil.rmtree(workspace, ignore_errors=True)
    return result


def run_patched(
    repo_path: str | Path,
    base_commit: str,
    patch_text: str,
    test_command: list[str],
    timeout_seconds: int = 120,
) -> tuple[TestResult, bool]:
    """Run the test command after applying the patch.

    Returns (test_result, patch_applied) where patch_applied indicates
    whether the patch was successfully applied.
    """
    workspace, patch_applied = _clone_and_apply_patch(
        repo_path, base_commit, patch_text, "/tmp/repomedic-patched"
    )

    if not patch_applied:
        shutil.rmtree(workspace, ignore_errors=True)
        return TestResult(
            phase="patched",
            exit_code=None,
            timed_out=False,
            passed=0,
            failed=0,
            skipped=0,
            output="",
            error="Patch could not be applied",
            changed_paths=[],
        ), False

    runner = make_local_runner()
    result = runner(str(workspace), test_command, timeout_seconds)
    shutil.rmtree(workspace, ignore_errors=True)
    return result, True


def compare_results(
    baseline: TestResult,
    patched: TestResult,
) -> dict[str, object]:
    """Compare baseline and patched test results."""
    comparison: dict[str, object] = {
        "baseline_exit_code": baseline.exit_code,
        "patched_exit_code": patched.exit_code,
        "baseline_timed_out": baseline.timed_out,
        "patched_timed_out": patched.timed_out,
        "baseline_passed": baseline.passed,
        "patched_passed": patched.passed,
        "baseline_failed": baseline.failed,
        "patched_failed": patched.failed,
        "baseline_skipped": baseline.skipped,
        "patched_skipped": patched.skipped,
        "baseline_output": baseline.output[-2000:] if baseline.output else "",
        "patched_output": patched.output[-2000:] if patched.output else "",
    }
    return comparison