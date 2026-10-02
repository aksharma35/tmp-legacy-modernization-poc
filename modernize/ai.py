"""Claude Code: the AI agent behind every AI step, run headless (`claude -p`).

The pipeline, not the AI, owns the loop:
  * Claude may only edit the files the step names, using Read and Edit. It cannot run commands.
  * After each attempt the pipeline runs the step's check and commits the attempt ("ai: ...").
  * A failed check is sent back to the same Claude session, up to `max_attempts` times,
    with a spend cap on every attempt.
  * If the last attempt still fails, the attempts are parked on a branch, the code goes back
    to the last green state, and the pipeline stops. Nothing downstream runs.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from . import gitutil
from .config import Config
from .ui import console, fail, info, ok, warn

FEEDBACK_LINES = 120


def claude_bin() -> str:
    exe = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if not exe:
        raise SystemExit(
            "Claude Code is not installed. Install it with:\n"
            "  npm install -g @anthropic-ai/claude-code\n"
            "or skip the AI step with --no-ai."
        )
    return exe


def _env() -> dict:
    env = dict(os.environ)
    if not env.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set. The AI steps run Claude Code in bare mode, which needs an API key.")
    return env


def _base_args(cfg: Config) -> list[str]:
    # --bare: ignore personal settings, hooks, plugins and CLAUDE.md, so every machine runs the same way.
    return [
        claude_bin(), "--bare", "-p",
        "--output-format", "json",
        "--model", cfg.model,
        "--append-system-prompt-file", str(cfg.root / "CONVENTIONS.md"),
    ]


def _call(cfg: Config, args: list[str], prompt: str) -> dict:
    proc = subprocess.run(args + [prompt], cwd=cfg.root, env=_env(), stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8")
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except (json.JSONDecodeError, IndexError):
        data = {}
    if not data:
        raise RuntimeError(f"Claude Code failed (exit {proc.returncode}):\n{(proc.stderr or proc.stdout)[-1500:]}")
    _record_usage(cfg, data)
    return data


def _record_usage(cfg: Config, data: dict) -> None:
    row = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "step": os.environ.get("MODERNIZE_STEP", ""),
        "session": data.get("session_id"),
        "cost_usd": data.get("total_cost_usd"),
        "turns": data.get("num_turns"),
        "error": data.get("is_error"),
    }
    with open(cfg.out / "ai-usage.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def ask(cfg: Config, question: str, read: list[str]) -> str:
    """A read-only question about the code. Claude can read files but change nothing."""
    files = "\n".join(f"- {p}" for p in read)
    prompt = f"{question}\n\nRelevant files (read them first):\n{files}"
    args = _base_args(cfg) + ["--tools", "Read", "--permission-mode", "dontAsk", "--max-budget-usd", str(cfg.budget_usd)]
    data = _call(cfg, args, prompt)
    if data.get("is_error"):
        raise RuntimeError(str(data.get("result"))[:500])
    return str(data.get("result", "")).strip()


# ------------------------------------------------------------------- edit loop

@dataclass
class Check:
    """A shell command whose exit code decides whether an attempt worked."""
    cmd: str
    label: str

    def run(self, cfg: Config) -> tuple[bool, str]:
        """Run it, show the output live, and keep it to send back to Claude on failure."""
        console.print(f"[dim]$ {self.label}[/dim]")
        proc = subprocess.Popen(self.cmd, shell=True, cwd=cfg.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        lines = []
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            lines.append(line.rstrip("\n"))
        proc.wait()
        clean = [re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", ln) for ln in lines]
        return proc.returncode == 0, "\n".join(clean[-FEEDBACK_LINES:])


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _out_of_scope(cfg: Config, allowed: list[str]) -> list[str]:
    allowed_set = {a.rstrip("/") for a in allowed}
    return [f for f in gitutil.changed_files(cfg.root) if f not in allowed_set]


def edit_until_green(cfg: Config, *, unit: str, prompt: str, files: list[str], read: list[str], check: Check) -> bool:
    """Ask Claude to change `files` until `check` passes, at most cfg.max_attempts times."""
    start = gitutil.head(cfg.root)
    session = None
    message = (
        prompt
        + "\n\nFiles you may edit (all other files are read-only):\n" + "\n".join(f"- {f}" for f in files)
        + "\n\nRead these first:\n" + "\n".join(f"- {r}" for r in read + files)
        + "\n\nYou cannot run commands. When you finish, the pipeline runs this check: " + check.label
    )
    edit_rules = [f"Edit({f})" for f in files]
    os.environ["MODERNIZE_STEP"] = unit

    for attempt in range(1, cfg.max_attempts + 1):
        info(f"[bold]Attempt {attempt}/{cfg.max_attempts}[/bold] · Claude Code ({cfg.model}) edits {', '.join(files)}")
        args = _base_args(cfg) + [
            "--tools", "Read,Edit",
            "--permission-mode", "dontAsk",
            "--allowedTools", "Read", *edit_rules,
            "--max-budget-usd", str(cfg.budget_usd),
        ]
        if session:
            args += ["--resume", session]
        try:
            data = _call(cfg, args, message)
        except RuntimeError as exc:
            fail(str(exc))
            data = {}
        session = data.get("session_id") or session
        summary = str(data.get("result", "")).strip()
        if summary:
            console.print(f"[magenta]Claude:[/magenta] {summary.splitlines()[0][:300]}")
        if data.get("total_cost_usd") is not None:
            info(f"Cost so far for {unit}: ${data['total_cost_usd']:.2f}")

        stray = _out_of_scope(cfg, files)
        if stray:
            gitutil.discard(cfg.root, stray)
            warn(f"Discarded edits outside the allowed files: {', '.join(stray)}")

        passed, output = check.run(cfg)
        verdict = "check passes" if passed else "check fails"
        sha = gitutil.commit(cfg.root, f"ai: {unit} attempt {attempt} ({verdict})", files,
                             trailer=f"AI-Agent: Claude Code ({cfg.model})")
        if passed:
            ok(f"{unit}: check passes after attempt {attempt}" + (f"  [dim]({sha})[/dim]" if sha else ""))
            return True
        fail(f"{unit}: check fails after attempt {attempt}" + (f"  [dim]({sha})[/dim]" if sha else ""))
        if not sha:
            warn("Claude made no changes in this attempt.")
        message = (
            f"The check failed after your changes. Output (last {FEEDBACK_LINES} lines):\n\n{output}\n\n"
            "Fix the files you are allowed to edit so the check passes. Follow CONVENTIONS.md."
        )

    # Defined failure behaviour: park the attempts, go back to green, stop.
    branch = f"modernize/failed-{_slug(unit)}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    gitutil.park_and_reset(cfg.root, branch, start)
    blocked = {"unit": unit, "attempts": cfg.max_attempts, "branch": branch, "reset_to": start,
               "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "last_output": output[-4000:]}
    (cfg.out / "blocked.json").write_text(json.dumps(blocked, indent=2), encoding="utf-8")
    fail(f"{unit} still fails after {cfg.max_attempts} attempts. The pipeline stops here.")
    console.print(
        f"  · The {cfg.max_attempts} attempts are kept on branch [bold]{branch}[/bold] for review.\n"
        f"  · Your branch is back at {start}, the last state where every check passed.\n"
        f"  · Fix it by hand, or re-run this step. Nothing after this step has run."
    )
    return False
