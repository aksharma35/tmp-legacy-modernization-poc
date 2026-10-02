"""Test runners used by the pipeline and by the AI steps' checks."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import apicases, procs
from .config import Config
from .ui import console, fail, ok


def _npm(cmd: str) -> str:
    exe = shutil.which(cmd)
    if not exe:
        raise SystemExit(f"'{cmd}' not found. Install Node.js 20.19+ (https://nodejs.org).")
    return exe


# ---------------------------------------------------------------- API parity

def run_api(cfg: Config, target: str, record: bool = False, quiet: bool = False, show: bool = True) -> dict:
    procs.ensure_target(cfg, target, restart_backend=True, api_only=True)
    out_dir = cfg.out / "parity" / ("lock" if record else target)
    env = {
        **os.environ,
        "PARITY_API_URL": cfg.target(target).api_url,
        "PARITY_OUT": str(out_dir),
        "PYTHONPATH": str(cfg.root) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    if record:
        env["PARITY_MODE"] = "record"
    else:
        env.pop("PARITY_MODE", None)
    args = [sys.executable, "-m", "pytest", "parity/api", "-p", "no:cacheprovider", "-q"]
    if quiet:
        args += ["--no-header", "-rN", "--tb=line"]
    if show:
        proc = subprocess.run(args, cwd=cfg.root, env=env)
    else:
        proc = subprocess.run(args, cwd=cfg.root, env=env, capture_output=True, text=True, encoding="utf-8")
    results_file = out_dir / "api-results.json"
    results = json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else {"passed": [], "failed": [], "diffs": []}
    results["ok"] = proc.returncode == 0
    return results


# ------------------------------------------------------------- smoke checks

def run_smoke(cfg: Config, target: str) -> bool:
    """Replay every recorded request; fail on crashes and 5xx. Shows the server log on failure."""
    try:
        procs.ensure_target(cfg, target, restart_backend=True, api_only=True)
    except RuntimeError as exc:  # the server did not even start: show why
        fail(f"Smoke test: the '{target}' backend did not start.")
        console.print(str(exc), markup=False)
        return False
    cases = apicases.load_cases(cfg.root / "parity" / "api" / "cases.yaml")
    send = apicases.requests_sender(cfg.target(target).api_url)
    problems = []
    for name, steps in cases.items():
        try:
            for step_result in apicases.run_case(send, steps):
                if step_result["status"] >= 500:
                    problems.append(f"{name}: {step_result['request']} -> HTTP {step_result['status']}")
        except Exception as exc:  # connection errors, bad JSON, reset hook missing
            problems.append(f"{name}: {type(exc).__name__}: {exc}")
    if not problems:
        ok(f"Smoke test: {len(cases)} recorded API cases ran without crashes on '{target}'.")
        return True
    fail(f"Smoke test: {len(problems)} request(s) crashed on '{target}':")
    for p in problems:
        console.print(f"  - {p}", markup=False)
    backend = next((s for s in cfg.target(target).services if s.endswith("-api")), None)
    if backend:
        console.print(f"\n--- {backend}: last error in the server log ---")
        console.print(last_traceback(procs.log_tail(cfg, backend, 400)), markup=False)
    return False


def last_traceback(log: str) -> str:
    """The last Python traceback in a server log (what the AI needs), or the log tail."""
    start = log.rfind("Traceback (most recent call last):")
    if start < 0:
        return "\n".join(log.splitlines()[-25:])
    lines = log[start:].splitlines()
    out = [lines[0]]
    for line in lines[1:]:
        out.append(line)
        if line and not line.startswith((" ", "\t")):  # the exception line ends the traceback
            break
    return "\n".join(out)


# ------------------------------------------------------------ browser parity

def run_e2e(cfg: Config, target: str, grep: str | None = None, headed: bool = False) -> dict:
    e2e_dir = cfg.root / "parity" / "e2e"
    if not (e2e_dir / "node_modules").exists():
        raise SystemExit("Browser tests are not installed. Run `modernize setup` first.")
    procs.ensure_target(cfg, target, restart_backend=True)
    json_out = cfg.out / "parity" / f"e2e-{target}.json"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PARITY_E2E_JSON": str(json_out)}
    for name, t in cfg.targets.items():
        env[f"{name.upper()}_WEB_URL"] = t.web_url
    args = [_npm("npx"), "playwright", "test", f"--project={target}"]
    if grep:
        args += ["--grep", grep]
    if headed:
        args += ["--headed"]
    proc = subprocess.run(args, cwd=e2e_dir, env=env)
    return summarize_e2e(json_out, proc.returncode == 0)


def summarize_e2e(json_file: Path, ok_flag: bool) -> dict:
    summary = {"ok": ok_flag, "passed": 0, "failed": 0, "tests": []}
    if not json_file.exists():
        return summary
    data = json.loads(json_file.read_text(encoding="utf-8"))

    def walk(suite, trail):
        title = suite.get("title", "")
        trail = trail + ([title] if title and not title.endswith(".js") else [])
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                status = "passed" if test.get("status") == "expected" else "failed"
                summary[status] += 1
                error = ""
                for r in test.get("results", []):
                    if r.get("error"):
                        error = (r["error"].get("message") or "").splitlines()[0][:200]
                summary["tests"].append({"suite": " › ".join(trail), "title": spec["title"], "status": status, "error": error,
                                         "tags": [t.lstrip("@") for t in spec.get("tags", [])]})
        for child in suite.get("suites", []):
            walk(child, trail)

    for suite in data.get("suites", []):
        walk(suite, [])
    return summary


# -------------------------------------------------------------- build check

def run_build(cfg: Config) -> bool:
    front = cfg.paths["modern_frontend"]
    if not (front / "node_modules").exists():
        raise SystemExit("modern/frontend is not scaffolded yet. Run the angularjs-react transform first.")
    proc = subprocess.run([_npm("npm"), "run", "build", "--silent"], cwd=front)
    (ok if proc.returncode == 0 else fail)("React build " + ("succeeded." if proc.returncode == 0 else "failed."))
    return proc.returncode == 0
