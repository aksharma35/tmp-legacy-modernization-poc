"""modernize: the command-line entry point."""
from __future__ import annotations

import shutil
import subprocess
from typing import List, Optional

import typer

from . import decisions, gitutil, procs, testing
from .config import Config
from .ui import fail, info, ok, step, table

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
    help="Legacy modernization pipeline: open-source tools do the bulk, AI fills the gaps, parity tests decide.",
)
test_app = typer.Typer(no_args_is_help=True, help="Run one check. Aider uses these as its --test-cmd.")
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

    if not os.environ.get("MODERNIZE_LEGACY_API_START") and shutil.which("docker"):
        info("Building the Python 2.7 image for the legacy API (first time only)…")
        if subprocess.run(["docker", "compose", "build", "legacy-api"], cwd=cfg.root).returncode == 0:
            ok("Legacy API image built.")
    ok("Next: modernize doctor")


@app.command()
def doctor() -> None:
    """Check every prerequisite (runtimes, tools, API key, ports)."""
    from .doctor import doctor as run_doctor

    _exit(run_doctor(Config()))


@app.command()
def discover(yes: bool = typer.Option(False, "--yes", help="Approve the plan without asking.")) -> None:
    """Phase 1: find outdated patterns (Semgrep) and extract unit specs (ast-grep)."""
    from .discover import build_plan

    cfg = Config()
    step("Discover · what needs to change, and what could silently break", "Semgrep rules + ast-grep extraction, no AI")
    plan = build_plan(cfg)
    b = plan["backend"]
    table("Backend · Python 2.7 → 3.12", ["Kind", "Findings", "Who handles it"], [
        ["syntax", b["syntax"], "codemods (2to3, ruff)"],
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
def lock() -> None:
    """Phase 2: record the legacy app's behaviour (API responses + browser tests)."""
    from .lock import lock as run_lock

    _exit(run_lock(Config()))


@app.command()
def transform(
    recipe: str = typer.Option(..., "--recipe", "-r", help="python2to3 or angularjs-react"),
    unit: Optional[List[str]] = typer.Option(None, "--unit", "-u", help="Only these units (angularjs-react)."),
    no_ai: bool = typer.Option(False, "--no-ai", help="Run only the deterministic steps."),
    force: bool = typer.Option(False, "--force", help="Start the backend transform over."),
) -> None:
    """Phase 3: codemods first, then Aider for whatever is left."""
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
    """Phase 5: run migrated React components inside the live AngularJS page, then test it."""
    from .bridge import build_hybrid
    from .verify import verify_e2e

    cfg = Config()
    build_hybrid(cfg, unit)
    passed = verify_e2e(cfg, "hybrid", headed=headed)
    info(f"Open it: {cfg.target('hybrid').web_url}")
    _exit(passed)


@app.command()
def report() -> None:
    """Phase 6: write migration/REPORT.md from the pipeline's records."""
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
