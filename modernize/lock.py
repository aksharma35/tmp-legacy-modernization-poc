"""Phase 2 -- lock: record how the legacy app behaves, before anything changes."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import gitutil, testing
from .config import Config
from .ui import fail, ok, step, table


def lock(cfg: Config) -> bool:
    step("Lock · record the legacy behaviour", "These results become the contract the new code must meet")

    rec = testing.run_api(cfg, "legacy", record=True, quiet=True)
    golden = cfg.root / "parity" / "api" / "golden"
    n_cases = len(list(golden.glob("*.json")))
    n_requests = sum(len(json.loads(p.read_text(encoding="utf-8"))["steps"]) for p in golden.glob("*.json"))
    if not rec["ok"]:
        fail("Recording the legacy API responses failed.")
        return False
    ok(f"Recorded {n_cases} API cases ({n_requests} requests) from the legacy API.")

    replay = testing.run_api(cfg, "legacy", quiet=True)
    if not replay["ok"]:
        fail("The legacy API does not reproduce its own recording. Is something non-deterministic?")
        return False
    ok("Replayed the recording against the legacy API: identical.")

    e2e = testing.run_e2e(cfg, "legacy")
    if not e2e["ok"]:
        fail(f"{e2e['failed']} browser test(s) fail on the legacy app. Fix the tests before migrating.")
        return False
    ok(f"{e2e['passed']} browser tests pass on the legacy AngularJS app.")

    summary = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api_cases": n_cases,
        "api_requests": n_requests,
        "browser_tests": e2e["passed"],
    }
    (cfg.out / "lock.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    table("Contract locked", ["Suite", "Recorded on legacy"], [
        ["API parity", f"{n_cases} cases / {n_requests} requests"],
        ["Browser parity", f"{e2e['passed']} tests"],
    ])
    sha = gitutil.commit(cfg.root, f"modernize: lock legacy behaviour ({n_cases} API cases, {e2e['passed']} browser tests)",
                         ["parity/api/golden"])
    if sha:
        ok(f"Committed the recording  [dim]({sha})[/dim]")
    return True
