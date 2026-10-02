"""Phase 2 -- lock: record how the legacy app behaves, and prove the tests are enough, before anything changes.

Four checks must pass before the contract is locked:
  1. The API cases are recorded from the legacy API and replay identically.
  2. Every browser test passes on the legacy AngularJS app.
  3. Every item in parity/behaviour.yaml has at least one passing test.
  4. Every risky backend line found by `discover` is executed by the recorded API cases.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import requests
import yaml

from . import apicases, gitutil, procs, testing
from .config import Config
from .ui import console, fail, ok, step, table, warn


def _behaviours(cfg: Config) -> list[dict]:
    data = yaml.safe_load((cfg.root / "parity" / "behaviour.yaml").read_text(encoding="utf-8"))
    return data.get("behaviours", [])


def _risky_lines(cfg: Config) -> list[dict]:
    plan_file = cfg.out / "discover" / "plan.json"
    if not plan_file.exists():
        raise SystemExit("No migration plan yet. Run `modernize discover` first.")
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    app_file = (cfg.paths["legacy_backend"] / "app.py").relative_to(cfg.root).as_posix()
    seen, out = set(), []
    for f in plan["findings"]:
        if f["migration"] == "python2to3" and f["kind"] in ("runtime", "semantic") and f["file"] == app_file:
            if f["line"] not in seen:
                seen.add(f["line"])
                out.append(f)
    return out


def _trace(cfg: Config, method: str) -> dict | None:
    url = cfg.target("legacy").api_url + "/api/test/lines"
    try:
        res = requests.request(method, url, timeout=5)
    except requests.RequestException:
        return None
    if res.status_code == 404:
        return None
    return res.json() if method == "GET" else {}


def lock(cfg: Config) -> bool:
    step("Lock · record the legacy behaviour and prove the tests are enough",
         "Nothing changes until all four checks pass")

    procs.ensure_target(cfg, "legacy", api_only=True)
    tracing = _trace(cfg, "DELETE") is not None
    if not tracing:
        warn("The legacy API is not running under the line tracer (parity/api/linetrace.py); check 4 cannot run.")

    # 1. Record and replay the API cases.
    rec = testing.run_api(cfg, "legacy", record=True, quiet=True)
    golden = cfg.root / "parity" / "api" / "golden"
    cases = apicases.load_cases(cfg.root / "parity" / "api" / "cases.yaml")
    for stale in golden.glob("*.json"):
        if stale.stem not in cases:
            stale.unlink()
    n_cases = len(cases)
    n_requests = sum(len(steps) for steps in cases.values())
    if not rec["ok"]:
        fail("Recording the legacy API responses failed.")
        return False
    replay = testing.run_api(cfg, "legacy", quiet=True)
    if not replay["ok"]:
        fail("The legacy API does not reproduce its own recording. Is something non-deterministic?")
        return False
    ok(f"1. Recorded {n_cases} API cases ({n_requests} requests) from the legacy API; they replay identically.")
    executed = set((_trace(cfg, "GET") or {}).get("lines", [])) if tracing else set()

    # 2. Browser tests on the legacy UI.
    e2e = testing.run_e2e(cfg, "legacy")
    if not e2e["ok"]:
        fail(f"{e2e['failed']} browser test(s) fail on the legacy app. Fix the tests before migrating.")
        return False
    ok(f"2. {e2e['passed']} browser tests pass on the legacy AngularJS app.")

    # 3. Every behaviour has a passing test.
    covers = apicases.load_covers(cfg.root / "parity" / "api" / "cases.yaml")
    tested: dict[str, list[str]] = {}
    for case in rec.get("passed", []):
        for b in covers.get(case, []):
            tested.setdefault(b, []).append(f"API {case}")
    for t in e2e["tests"]:
        if t["status"] == "passed":
            for tag in t["tags"]:
                tested.setdefault(tag, []).append(f"UI {t['title']}")
    behaviours = _behaviours(cfg)
    untested = [b for b in behaviours if b["id"] not in tested]
    if untested:
        fail(f"3. {len(untested)} of {len(behaviours)} behaviours in parity/behaviour.yaml have no test:")
        for b in untested:
            console.print(f"     {b['id']}  {b['text'].strip()}")
    else:
        ok(f"3. All {len(behaviours)} behaviours in parity/behaviour.yaml have at least one passing test.")

    # 4. Every risky backend line is executed by the recorded API cases.
    risky = _risky_lines(cfg)
    missed = [f for f in risky if f["line"] not in executed] if tracing else risky
    if missed:
        fail(f"4. {len(missed)} of {len(risky)} risky backend lines found by discover are never executed by an API case:")
        for f in missed:
            console.print(f"     {f['file']}:{f['line']}  {f['rule']}  {f['code']}")
    else:
        ok(f"4. All {len(risky)} risky backend lines found by discover are executed by the API cases.")

    summary = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api_cases": n_cases,
        "api_requests": n_requests,
        "browser_tests": e2e["passed"],
        "behaviours": len(behaviours),
        "behaviours_untested": [b["id"] for b in untested],
        "risky_lines": [f"{f['file']}:{f['line']}" for f in risky],
        "risky_lines_missed": [f"{f['file']}:{f['line']}" for f in missed],
        "tested_by": tested,
    }
    (cfg.out / "lock.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    table("Contract", ["Check", "Result"], [
        ["API cases recorded on legacy", f"{n_cases} cases / {n_requests} requests"],
        ["Browser tests passing on legacy", str(e2e["passed"])],
        ["Behaviours with a test", f"{len(behaviours) - len(untested)} of {len(behaviours)}"],
        ["Risky lines executed by a test", f"{len(risky) - len(missed)} of {len(risky)}"],
    ])
    if untested or missed:
        fail("Not locked: the tests do not cover everything yet.")
        console.print("  Add the missing tests (or run `modernize draft-tests` to have Claude draft them from "
                      "parity/behaviour.yaml), then run `modernize lock` again.")
        return False

    sha = gitutil.commit(cfg.root, f"modernize: lock legacy behaviour ({n_cases} API cases, {e2e['passed']} browser tests, "
                                   f"{len(behaviours)} behaviours, {len(risky)} risky lines covered)",
                         ["parity/api/golden"])
    ok("Contract locked" + (f"  [dim]({sha})[/dim]" if sha else ""))
    return True
