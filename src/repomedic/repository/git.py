from __future__ import annotations

import subprocess
from pathlib import Path


def get_head_commit(repo_path: str | Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        msg = f"Failed to get HEAD commit: {result.stderr}"
        raise RuntimeError(msg)
    return result.stdout.strip()


def get_working_tree_status(repo_path: str | Path) -> dict:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    staged = []
    unstaged = []
    untracked = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        status_code = line[:2]
        filepath = line[3:]
        if status_code[0] == " " and status_code[1] == " ":
            untracked.append(filepath)
        elif status_code[0] == "M" and status_code[1] == " ":
            unstaged.append(filepath)
        elif status_code[0] == " " and status_code[1] == "M":
            unstaged.append(filepath)
        elif status_code[0] == "A" or status_code[0] == "D" or status_code[0] == "R":
            staged.append(filepath)
        else:
            staged.append(filepath)
    return {
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }


def export_patch(repo_path: str | Path, source: str) -> str:
    """Create a patch from a git diff source string.

    Supported sources:
    - 'head': diff against HEAD
    - 'working_tree': diff of working tree changes
    - A full diff text
    """
    if source == "head":
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            msg = f"Failed to generate HEAD diff: {result.stderr}"
            raise RuntimeError(msg)
        return result.stdout
    elif source == "working_tree":
        result = subprocess.run(
            ["git", "diff"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            msg = f"Failed to generate working tree diff: {result.stderr}"
            raise RuntimeError(msg)
        return result.stdout
    else:
        return source


def validate_patch(patch_text: str) -> bool:
    """Parse and reject malformed patches."""
    if not patch_text or not patch_text.strip():
        return False
    lines = patch_text.strip().splitlines()
    if not lines:
        return False
    first_line = lines[0]
    if not first_line.startswith("@@"):
        return False
    return True


def hash_patch(patch_text: str) -> str:
    import hashlib
    return hashlib.sha256(patch_text.encode("utf-8")).hexdigest()


def list_changed_paths(patch_text: str) -> list[str]:
    """Return normalized changed paths from a patch."""
    import re
    paths: set[str] = set()
    for line in patch_text.splitlines():
        if line.startswith("--- "):
            path = line[4:]
            paths.add(path)
        elif line.startswith("+++ "):
            path = line[4:]
            paths.add(path)
    return sorted(paths)


def check_patch_scope(paths: list[str], policy: list[str]) -> list[str]:
    """Flag disallowed paths and suspicious changes."""
    flags: list[str] = []
    for path in paths:
        for pattern in policy:
            if pattern in path:
                flags.append(f"blocked: {path} ({pattern})")
    return flags