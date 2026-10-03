"""modernize: the command-line entry point."""
from __future__ import annotations

import shutil
import subprocess
from typing import List, Optional

import typer

from . import decisions, gitutil, procs, testing
from .config import Config
from .ui import console, fail, info, ok, step, table

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
    help="Legacy modernization pipeline: open-source tools do the bulk, AI fills the gaps, parity tests decide.",
)
test_app = typer.Typer(no_args_is_help=True, help="Run one check. The AI steps use these to decide whether an attempt worked.")
app.add_typer(test_app, name="test")


def _exit(passed: bool) -> None:
    raise typer.Exit(code=0 if passed else 1)


@app.command()
def setup() -> None:
    """Install the browser test runner and its Chromium build."""
    cfg = Config()
    e2e = cfg.root / "parity" / "e2e"
    npm, npx = shutil.which("npm"), shutil.which("npx")
    if not npm or not npx:
        raise SystemExit("npm/npx not found. Install Node.js 22 LTS first.")
    subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=e2e, check=True)
    subprocess.run([npx, "playwright", "install", "chromium"], cwd=e2e, check=True)
    ok("Browser tests installed.")
    import os

    if not os.environ.get("MODERNIZE_LEGACY_PYTHON") and shutil.which("docker"):
        info("Building the Python 2.7 image for the legacy API (first time only)…")
        if subprocess.run(["docker", "compose", "build", "legacy-api"], cwd=cfg.root).returncode == 0:
            ok("Legacy API image built.")
    ok("Next: modernize doctor")


@app.command()
def doctor(ai: bool = typer.Option(False, "--ai", help="Also make one tiny live call to the AI model.")) -> None:
    """Check every prerequisite (runtimes, tools, API key, ports)."""
    from .doctor import doctor as run_doctor

    _exit(run_doctor(Config(), live=ai))


@app.command()
def discover(yes: bool = typer.Option(False, "--yes", help="Approve the plan without asking.")) -> None:
    """Phase 1: check dependencies, find outdated patterns and extract unit specs (Semgrep)."""
    from .discover import build_plan

    cfg = Config()
    step("Discover · what needs to change, and what could silently break", "Dependency resolution + Semgrep rules, no AI")
    plan = build_plan(cfg)
    deps = plan["dependencies"]
    table(f"Dependencies · must install on Python {deps['python']}", ["Package", "Legacy", f"Python {deps['python']}", "Status"], [
        [d["name"], d["legacy"] or "-", d["resolved"] or "-",
         "[green]✔[/green]" if d["status"] == "ok" else f"[red]✘ {d.get('reason', 'no compatible release')}[/red]"]
        for d in deps["packages"]
    ])
    if not deps["ok"]:
        fail(f"{len(deps['blocked']) or 'Some'} dependenc{'y' if len(deps['blocked']) == 1 else 'ies'} "
             f"cannot run on Python {deps['python']}: {', '.join(deps['blocked']) or 'see migration/PLAN.md'}.")
        console.print("  Replace or upgrade them first. The pipeline stops here, before any code changes.")
        _exit(False)
    ok(f"All {len(deps['packages'])} dependencies have a release for Python {deps['python']}.")
    b = plan["backend"]
    table("Backend · Python 2.7 → 3.12", ["Kind", "Findings", "Who handles it"], [
        ["syntax", b["syntax"], "codemods (fissix, ruff)"],
        ["runtime", b["runtime"], "AI, checked by smoke tests"],
        ["semantic", b["semantic"], "parity tests + a human"],
    ])
    table("Frontend · AngularJS → React (migration order)", ["#", "Unit", "AngularJS", "Behaviours to keep", "Checked by"], [
        [i, u["name"], f"{u['kind']} {u['angular_name']}", len(u["behaviour_notes"]), "build" if u["kind"] == "factory" else f"@{u['name']}"]
        for i, u in enumerate(plan["frontend"]["units"], 1)
    ])
    info("Full plan: migration/PLAN.md")
    approved = yes or typer.confirm("Approve this plan?", default=True)
    data = decisions.load(cfg)
    data["plan"] = {"approved": approved, "by": gitutil.user_name(cfg.root), "at": decisions.now()}
    decisions.save(cfg, data)
    if approved:
        sha = gitutil.commit(cfg.root, "modernize: migration plan approved", ["migration/PLAN.md", "migration/decisions.yaml"])
        ok("Plan approved" + (f"  [dim]({sha})[/dim]" if sha else ""))
    else:
        fail("Plan not approved. Nothing will change.")
    _exit(approved)


@app.command()
def lock(no_commit: bool = typer.Option(False, "--no-commit", help="Run the checks without committing the recording.")) -> None:
    """Phase 2: record the legacy behaviour and prove the tests cover the spec and every risky line."""
    from .lock import lock as run_lock

    _exit(run_lock(Config(), commit=not no_commit))


@app.command("draft-tests")
def draft_tests() -> None:
    """Claude drafts tests for the gaps the last `lock` reported, from parity/behaviour.yaml."""
    import json
    import sys

    from . import ai

    cfg = Config()
    lock_file = cfg.out / "lock.json"
    if not lock_file.exists():
        raise SystemExit("Run `modernize lock` first; it reports which tests are missing.")
    gaps = json.loads(lock_file.read_text(encoding="utf-8"))
    untested, missed = gaps.get("behaviours_untested", []), gaps.get("risky_lines_missed", [])
    if not untested and not missed:
        ok("The last lock found no gaps. Nothing to draft.")
        raise typer.Exit(0)
    specs = sorted(p.relative_to(cfg.root).as_posix() for p in (cfg.root / "parity" / "e2e" / "tests").glob("*.spec.js"))
    prompt = (
        "The parity tests do not cover everything yet. Draft the missing tests.\n\n"
        f"Behaviours in parity/behaviour.yaml with no test: {', '.join(untested) or 'none'}\n"
        f"Risky backend lines (legacy/backend/app.py) no API case executes: {', '.join(missed) or 'none'}\n\n"
        "Rules:\n"
        "- API behaviours and risky lines: add cases to parity/api/cases.yaml, each with `covers:` listing the behaviour IDs.\n"
        "- Screen behaviours: add Playwright tests to the existing spec files, each with { tag: '@B<n>' }, "
        "using parity/e2e/tests/helpers.js and selectors a user would see (labels, roles, text).\n"
        "- Tests must describe what the legacy app does today and pass against it. Read the legacy code to be sure.\n"
        "- Do not change or delete existing tests."
    )
    step("AI step · Claude Code drafts the missing tests",
         f"model: {cfg.model} · at most {cfg.max_attempts} attempts · checked by `modernize lock`")
    passed = ai.edit_until_green(
        cfg, unit="tests", prompt=prompt, files=["parity/api/cases.yaml", *specs],
        read=["parity/behaviour.yaml", "legacy/backend/app.py", "legacy/frontend/index.html", "parity/e2e/tests/helpers.js"],
        check=ai.Check(f'"{sys.executable}" -m modernize lock --no-commit', "modernize lock"),
    )
    if passed:
        from .lock import commit_lock

        sha = commit_lock(cfg)
        ok("Contract locked" + (f"  [dim]({sha})[/dim]" if sha else ""))
    _exit(passed)


@app.command()
def transform(
    recipe: str = typer.Option(..., "--recipe", "-r", help="python2to3 or angularjs-react"),
    unit: Optional[List[str]] = typer.Option(None, "--unit", "-u", help="Only these units (angularjs-react)."),
    no_ai: bool = typer.Option(False, "--no-ai", help="Run only the deterministic steps."),
    force: bool = typer.Option(False, "--force", help="Start the backend transform over."),
) -> None:
    """Phase 3: codemods first, then Claude Code for whatever is left."""
    from . import transform as tf

    cfg = Config()
    rec = tf.load_recipe(cfg, recipe)
    if recipe == "python2to3":
        _exit(tf.transform_backend(cfg, rec, use_ai=not no_ai, force=force))
    _exit(tf.transform_frontend(cfg, rec, only=unit, use_ai=not no_ai))


@app.command()
def verify(
    suite: str = typer.Option("all", "--suite", help="api, e2e or all"),
    target: str = typer.Option("modern", "--target"),
    no_ai: bool = typer.Option(False, "--no-ai", help="Skip the AI explanation and fix."),
    decide: Optional[str] = typer.Option(None, "--decide", help="Non-interactive: keep or accept every change."),
    headed: bool = typer.Option(False, "--headed", help="Show the browser while the tests run."),
) -> None:
    """Phase 4: replay the contract against the new code. You decide every behaviour change."""
    from . import verify as vf

    cfg = Config()
    choice = {"keep": "keep-legacy", "accept": "accept-new", None: None}.get(decide)
    passed = True
    if suite in ("api", "all"):
        passed &= vf.verify_api(cfg, target if target != "hybrid" else "modern", use_ai=not no_ai, decide=choice)
    if suite in ("e2e", "all"):
        passed &= vf.verify_e2e(cfg, target, headed=headed)
    _exit(passed)


@app.command()
def bridge(
    unit: List[str] = typer.Option(["SummaryPanel"], "--unit", "-u", help="React units to mount inside AngularJS."),
    headed: bool = typer.Option(False, "--headed"),
) -> None:
    """Optional (not in the demo): run migrated React components inside the live AngularJS page, then test it."""
    from .bridge import build_hybrid
    from .verify import verify_e2e

    cfg = Config()
    build_hybrid(cfg, unit)
    passed = verify_e2e(cfg, "hybrid", headed=headed)
    info(f"Open it: {cfg.target('hybrid').web_url}")
    _exit(passed)


@app.command()
def report() -> None:
    """Phase 5: write migration/REPORT.md from the pipeline's records."""
    from .report import build_report

    cfg = Config()
    path = build_report(cfg)
    sha = gitutil.commit(cfg.root, "modernize: migration report", [str(path.relative_to(cfg.root))])
    if sha:
        info(f"Committed  [dim]({sha})[/dim]")


@app.command()
def up(target: str = typer.Argument("legacy", help="legacy, modern or hybrid")) -> None:
    """Start a target's services and print where to open it."""
    cfg = Config()
    procs.ensure_target(cfg, target)
    ok(f"{target}: {cfg.target(target).web_url}")


@app.command()
def clean() -> None:
    """Stop services and delete generated files that git does not track (use between rehearsal takes)."""
    cfg = Config()
    procs.stop_all(cfg)
    removed = []
    if (cfg.root / "out").exists():
        shutil.rmtree(cfg.root / "out")
        removed.append("out/")
    tracked = subprocess.run(["git", "ls-files", "modern"], cwd=cfg.root, capture_output=True, text=True).stdout.strip()
    if (cfg.root / "modern").exists() and not tracked:
        shutil.rmtree(cfg.root / "modern")
        removed.append("modern/")
    ok("Clean. Removed: " + (", ".join(removed) if removed else "nothing"))


@app.command()
def down() -> None:
    """Stop every service started by modernize."""
    procs.stop_all(Config())
    ok("Stopped.")


@test_app.command("api")
def test_api(target: str = typer.Option("modern", "--target")) -> None:
    """API parity against the recorded legacy responses."""
    _exit(testing.run_api(Config(), target, quiet=True)["ok"])


@test_app.command("e2e")
def test_e2e(
    target: str = typer.Option("modern", "--target"),
    grep: Optional[str] = typer.Option(None, "--grep"),
    headed: bool = typer.Option(False, "--headed"),
) -> None:
    """Browser parity (Playwright) against a target."""
    _exit(testing.run_e2e(Config(), target, grep=grep, headed=headed)["ok"])


@test_app.command("smoke")
def test_smoke(target: str = typer.Option("modern", "--target")) -> None:
    """Replay every recorded request; fail on crashes or 5xx (shows the server log)."""
    _exit(testing.run_smoke(Config(), target))


@test_app.command("build")
def test_build() -> None:
    """Build the React app."""
    _exit(testing.run_build(Config()))


def main() -> None:
    """Console entry point: show pipeline errors as one clear line instead of a traceback."""
    try:
        app()
    except RuntimeError as exc:
        fail(str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
