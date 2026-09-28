"""Small git helpers. Every pipeline step is its own commit, so it can be reviewed or reverted."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=check)


def is_repo(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0


def commit(root: Path, message: str, paths: list[str] | None = None) -> str | None:
    """Stage `paths` (or everything) and commit. Returns the new SHA, or None if nothing changed."""
    if not is_repo(root):
        return None
    _git(root, "add", "-A", "--", *(paths or ["."]))
    if _git(root, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return None
    trailer = os.environ.get("MODERNIZE_COMMIT_TRAILER", "").strip()
    full = message + (f"\n\n{trailer}" if trailer else "")
    _git(root, "commit", "-q", "-m", full)
    return head(root)


def head(root: Path) -> str:
    return _git(root, "rev-parse", "--short", "HEAD").stdout.strip()


def user_name(root: Path) -> str:
    return _git(root, "config", "user.name", check=False).stdout.strip() or os.environ.get("USER", "reviewer")


def numstat(root: Path, sha: str) -> tuple[int, int, int]:
    """(files, added, removed) for one commit."""
    out = _git(root, "show", "--numstat", "--format=", sha, check=False).stdout
    files = added = removed = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            files += 1
            added += int(parts[0]) if parts[0].isdigit() else 0
            removed += int(parts[1]) if parts[1].isdigit() else 0
    return files, added, removed


def log(root: Path, *paths: str) -> list[dict]:
    """Commits touching `paths`, oldest first: sha, author, subject."""
    out = _git(root, "log", "--reverse", "--format=%h\t%an\t%s", "--", *paths, check=False).stdout
    rows = []
    for line in out.splitlines():
        sha, author, subject = (line.split("\t", 2) + ["", ""])[:3]
        rows.append({"sha": sha, "author": author, "subject": subject})
    return rows
