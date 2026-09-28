"""`modernize doctor`: check the laptop has everything before you hit record."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from . import procs
from .config import Config
from .discover import _tool
from .ui import console, table


def _run(args: list[str], cwd=None) -> tuple[int, str]:
    exe = shutil.which(args[0])
    if not exe:
        return 127, ""
    try:
        p = subprocess.run([exe, *args[1:]], capture_output=True, text=True, encoding="utf-8", cwd=cwd, timeout=60)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _version(text: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    return tuple(int(x) for x in m.groups() if x) if m else (0,)


def doctor(cfg: Config) -> bool:
    rows: list[list[str]] = []
    good = True

    def check(name: str, passed: bool, detail: str, fix: str = "", required: bool = True):
        nonlocal good
        if required and not passed:
            good = False
        mark = "[green]✔[/green]" if passed else ("[red]✘[/red]" if required else "[yellow]![/yellow]")
        rows.append([mark, name, detail, "" if passed else fix])

    py = sys.version_info
    try:
        import lib2to3  # noqa: F401
        has_2to3 = True
    except ImportError:
        has_2to3 = False
    check("Python 3.12 (runs 2to3)", py[:2] == (3, 12) and has_2to3, f"{py.major}.{py.minor}.{py.micro}",
          "uv venv --python 3.12 .venv && uv pip install -e .")

    code, out = _run(["git", "--version"])
    check("git", code == 0, out or "not found", "Install git")

    code, out = _run(["node", "--version"])
    check("Node.js 20.19+ (Vite 8)", code == 0 and _version(out) >= (20, 19), out or "not found", "Install Node.js 22 LTS from nodejs.org")

    if os.environ.get("MODERNIZE_LEGACY_API_START"):
        check("Python 2.7 runtime", True, "local: " + os.environ["MODERNIZE_LEGACY_API_START"])
    else:
        code, out = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
        check("Docker (runs Python 2.7)", code == 0, f"server {out}" if code == 0 else "not running",
              "Start Docker Desktop (Windows: with the WSL 2 backend)")

    for tool in ("semgrep", "ast-grep", "ruff"):
        code, out = _run([_tool(tool), "--version"])
        check(tool, code == 0, (out.splitlines() or ["not found"])[0], "uv pip install -e .")

    code, out = _run(["npx", "--no-install", "playwright", "--version"], cwd=cfg.root / "parity" / "e2e")
    check("Playwright (browser tests)", code == 0, out or "not installed", "modernize setup")

    aider = os.environ.get("AIDER_BIN") or shutil.which("aider")
    code, out = _run([aider, "--version"]) if aider else (127, "")
    check("Aider (AI agent)", code == 0, out.splitlines()[-1] if out else "not found",
          "uv tool install --python 3.12 aider-chat")

    if cfg.model.startswith("anthropic/"):
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        check("ANTHROPIC_API_KEY", bool(key), f"set (…{key[-4:]})" if key else "not set",
              "export ANTHROPIC_API_KEY=sk-ant-…  (use a key with a low spend limit)")
    check("AI model", True, cfg.model)

    for name, svc in cfg.services.items():
        port = re.search(r":(\d+)/", svc.ready_url).group(1)
        busy = procs.is_up(svc.ready_url)
        ours = (cfg.out / "run" / f"{name}.pid").exists() or svc.detached
        check(f"Port {port} ({name})", not busy or ours, "in use" if busy else "free",
              f"Something else is using port {port}. Stop it, or run `modernize down`.", required=False)

    table("modernize doctor", ["", "Check", "Found", "How to fix"], rows)
    console.print("[green]Ready to record.[/green]" if good else "[red]Fix the ✘ items above first.[/red]")
    return good
