from __future__ import annotations

from .git import export_patch, validate_patch, hash_patch, list_changed_paths, check_patch_scope


def create_patch(repo_path: str | Path, source: str = "working_tree") -> str:
    return export_patch(repo_path, source)


def is_valid_patch(patch_text: str) -> bool:
    return validate_patch(patch_text)


def compute_patch_hash(patch_text: str) -> str:
    return hash_patch(patch_text)


def get_changed_paths(patch_text: str) -> list[str]:
    return list_changed_paths(patch_text)


def assess_patch_scope(paths: list[str], policy: list[str]) -> list[str]:
    return check_patch_scope(paths, policy)