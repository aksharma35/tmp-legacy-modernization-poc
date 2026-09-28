"""Aider: the open-source AI coding agent that makes every AI edit in this pipeline."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import Config
from .ui import console


def aider_bin() -> str:
    exe = os.environ.get("AIDER_BIN") or shutil.which("aider")
    if not exe:
        raise SystemExit(
            "Aider is not installed. Install it with:\n"
            "  uv tool install --python 3.12 aider-chat\n"
            "or skip the AI step with --no-ai."
        )
    return exe


def _base_args(cfg: Config) -> list[str]:
    args = [
        aider_bin(),
        "--model", cfg.model,
        "--yes-always",
        "--no-check-update",
        "--no-show-release-notes",
        "--no-show-model-warnings",
        "--analytics-disable",
        "--no-gitignore",
        "--no-pretty",
        "--no-stream",
    ]
    extra = os.environ.get("MODERNIZE_AIDER_ARGS")
    if extra:
        args += extra.split()
    return args


def run(cfg: Config, message: str, edit: list[str], read: list[str], test_cmd: str | None = None) -> int:
    """Let Aider edit `edit` files. With `test_cmd`, Aider re-runs it after every edit
    and sends failures back to the model (up to 3 rounds per request)."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(message)
        msg_file = f.name
    args = _base_args(cfg) + ["--message-file", msg_file, "--auto-commits", "--no-dirty-commits"]
    for r in read:
        args += ["--read", r]
    if test_cmd:
        args += ["--test-cmd", test_cmd, "--auto-test"]
    args += edit
    console.print(f"[dim]$ aider --model {cfg.model} … {' '.join(edit)}[/dim]")
    try:
        return subprocess.run(args, cwd=cfg.root).returncode
    finally:
        Path(msg_file).unlink(missing_ok=True)


_HEADER = re.compile(
    r"^(Aider v|Main model:|Weak model:|Editor model:|Git repo:|Repo-map:|Added .* to the chat|"
    r"Use /help|Warning|https://aider\.chat|Cur working dir:|Git working dir:|Model:|Tokens:|Cost:|"
    r"Restored previous|Initial repo scan|Scanning repo)"
)


def ask(cfg: Config, question: str, read: list[str]) -> str:
    """Ask a question about the code without editing anything. Returns the answer text."""
    args = _base_args(cfg) + ["--chat-mode", "ask", "--no-auto-commits", "--no-dirty-commits", "--message", question]
    for r in read:
        args += ["--read", r]
    proc = subprocess.run(args, cwd=cfg.root, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"Aider failed ({proc.returncode}):\n{(proc.stderr or proc.stdout)[-1500:]}")
    lines = [ln for ln in proc.stdout.splitlines() if not _HEADER.match(ln.strip())]
    return "\n".join(lines).strip()
