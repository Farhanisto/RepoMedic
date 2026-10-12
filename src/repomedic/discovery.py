from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def find_git_repo(start_path: Path = Path.cwd()) -> Optional[Path]:
    """Find the Git repository root, starting from start_path.
    
    Walks up the directory tree looking for a .git directory.
    Returns the repo root path, or None if not found.
    """
    current = start_path.resolve()
    max_depth = 10  # Don't search beyond parent directories too deeply
    
    for _ in range(max_depth):
        git_dir = current / ".git"
        if git_dir.is_dir():
            return current
        # Also check for .git file (worktrees can use this)
        if git_dir.is_file():
            # Read the gitdir reference
            try:
                content = git_dir.read_text().strip()
                if content.startswith("gitdir: "):
                    gitdir_path = Path(content[len("gitdir: "):]).resolve()
                    return gitdir_path.parent
            except Exception:
                pass
        if current.parent == current:
            # Reached filesystem root
            break
        current = current.parent
    
    return None


def get_repo_info(repo_path: Path) -> dict:
    """Get information about a Git repository.
    
    Returns dict with repo metadata: branch, commit, status, etc.
    """
    repo_path = repo_path.resolve()
    
    # Get current branch
    branch = None
    commit = None
    status_parts = {"staged": [], "unstaged": [], "untracked": []}
    
    try:
        # Get branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
        
        # Get HEAD commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
        
        # Get working tree status
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                # Format: XY filepath (XY = status codes)
                status_code = line[:2]
                filepath = line[3:]
                # Skip if status_code has two non-space chars (e.g., "AM", "RD")
                if status_code[0] != " " and status_code[1] != " ":
                    if status_code[0] in ("A", "D", "R") and status_code[1] == " ":
                        status_parts["staged"].append(filepath)
                    elif status_code[0] == "M" and status_code[1] == " ":
                        status_parts["unstaged"].append(filepath)
                    elif status_code[0] == " " and status_code[1] == "M":
                        status_parts["unstaged"].append(filepath)
                    elif status_code[0] == "U":
                        status_parts["untracked"].append(filepath)
                    else:
                        status_parts["untracked"].append(filepath)
                else:
                    # Two-char status code
                    if status_code[0] == " " and status_code[1] == " ":
                        status_parts["untracked"].append(filepath)
                    elif status_code[0] == "M" and status_code[1] == " ":
                        status_parts["unstaged"].append(filepath)
                    elif status_code[0] == " " and status_code[1] == "M":
                        status_parts["unstaged"].append(filepath)
                    elif status_code[0] == "A" or status_code[0] == "D" or status_code[0] == "R":
                        status_parts["staged"].append(filepath)
                    else:
                        status_parts["staged"].append(filepath)
    except Exception:
        pass
    
    return {
        "path": str(repo_path),
        "branch": branch,
        "commit": commit,
        "staged": status_parts["staged"],
        "unstaged": status_parts["unstaged"],
        "untracked": status_parts["untracked"],
    }


def resolve_patch_path(patch_input: str, repo_path: Path) -> tuple[str, bool]:
    """Resolve a patch path relative to the repository.
    
    Returns (resolved_patch_text, is_working_tree_diff).
    """
    patch_path = Path(patch_input)
    
    if patch_path.is_file():
        # It's a file path
        text = patch_path.read_text()
        return text, False
    
    # It might be a working tree diff string or a relative path
    # If it starts with '--- ', it's likely a diff string
    if patch_input.startswith("--- ") or patch_input.startswith("@@"):
        return patch_input, False
    
    # Try as relative path within the repo
    rel_path = repo_path / patch_input
    if rel_path.is_file():
        return rel_path.read_text(), False
    
    # Maybe it's a working tree diff (git diff output)
    # In that case, just return it as-is
    return patch_input, True


def discover_repository() -> Optional[dict]:
    """Discover repository info from current working directory.
    
    Returns repo info dict or None if not in a git repo.
    """
    cwd = Path.cwd()
    repo_root = find_git_repo(cwd)
    
    if repo_root is None:
        return None
    
    info = get_repo_info(Path(repo_root))
    info["cwd_relative"] = str(cwd.relative_to(repo_root))
    return info