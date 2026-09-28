"""Writes a machine-readable result file that `modernize verify` reads."""
import json
import os
from pathlib import Path

RESULTS: dict = {"passed": [], "failed": []}


def pytest_runtest_logreport(report):
    if report.when != "call":
        return
    case = report.nodeid.split("[", 1)[-1].rstrip("]")
    RESULTS["passed" if report.passed else "failed"].append(case)


def pytest_sessionfinish(session, exitstatus):
    out_dir = os.environ.get("PARITY_OUT")
    if not out_dir or not session.items:
        return
    module = session.items[0].module  # test_api_parity
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "api-results.json").write_text(json.dumps({
        "mode": "record" if module.RECORD else "compare",
        "api_url": module.API_URL,
        "passed": RESULTS["passed"],
        "failed": RESULTS["failed"],
        "diffs": module.COLLECTED_DIFFS,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
