"""Small git helpers. Every pipeline step is its own commit, so it can be reviewed or reverted."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=check)


def is_repo(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0


def commit(root: Path, message: str, paths: list[str] | None = None, trailer: str = "") -> str | None:
    """Stage `paths` (or everything) and commit. Returns the new SHA, or None if nothing changed."""
    if not is_repo(root):
        return None
    _git(root, "add", "-A", "--", *(paths or ["."]))
    if _git(root, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return None
    trailers = [t for t in (trailer, os.environ.get("MODERNIZE_COMMIT_TRAILER", "").strip()) if t]
    full = message + ("\n\n" + "\n".join(trailers) if trailers else "")
    _git(root, "commit", "-q", "-m", full)
    return head(root)


def changed_files(root: Path) -> list[str]:
    """Paths with uncommitted changes (modified, added or untracked; ignored files excluded)."""
    out = _git(root, "status", "--porcelain", "-uall", check=False).stdout
    files = []
    for line in out.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path.strip('"'))
    return files


def discard(root: Path, paths: list[str]) -> None:
    """Throw away uncommitted changes to `paths` (restore tracked files, delete untracked ones)."""
    for p in paths:
        if _git(root, "ls-files", "--error-unmatch", p, check=False).returncode == 0:
            _git(root, "checkout", "--", p, check=False)
        else:
            (root / p).unlink(missing_ok=True)


def park_and_reset(root: Path, branch: str, start: str) -> None:
    """Keep the current commits on `branch`, then move the current branch back to `start`."""
    _git(root, "branch", "-f", branch, "HEAD")
    _git(root, "reset", "-q", "--hard", start)


def head(root: Path) -> str:
    return _git(root, "rev-parse", "--short", "HEAD").stdout.strip()


def user_name(root: Path) -> str:
    return _git(root, "config", "user.name", check=False).stdout.strip() or os.environ.get("USER", "reviewer")


LOCKFILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml")


def numstat(root: Path, sha: str) -> tuple[int, int, int]:
    """(files, added, removed) for one commit, ignoring generated lockfiles."""
    out = _git(root, "show", "--numstat", "--format=", sha, check=False).stdout
    files = added = removed = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and not parts[2].endswith(LOCKFILES):
            files += 1
            added += int(parts[0]) if parts[0].isdigit() else 0
            removed += int(parts[1]) if parts[1].isdigit() else 0
    return files, added, removed


def log(root: Path, *paths: str) -> list[dict]:
    """Commits touching `paths`, oldest first: sha, author, subject."""
    out = _git(root, "log", "--reverse", "--format=%h%x09%an%x09%s", "--", *paths, check=False).stdout
    rows = []
    for line in out.splitlines():
        sha, author, subject = (line.split("\t", 2) + ["", ""])[:3]
        body = _git(root, "show", "-s", "--format=%B", sha, check=False).stdout
        coauthors = ", ".join(
            ln.split(":", 1)[1].strip() for ln in body.splitlines() if ln.lower().startswith("co-authored-by:")
        )
        rows.append({"sha": sha, "author": author, "subject": subject, "coauthors": coauthors})
    return rows
