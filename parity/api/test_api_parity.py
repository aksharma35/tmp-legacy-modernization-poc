"""API parity suite.

Record mode (run by `modernize lock` against the legacy API):
    PARITY_MODE=record PARITY_API_URL=http://localhost:5001 pytest parity/api
Compare mode (run by `modernize verify` / `modernize test api`):
    PARITY_API_URL=http://localhost:5002 pytest parity/api
"""
import json
import os
from pathlib import Path

import pytest

from modernize import apicases

HERE = Path(__file__).parent
GOLDEN = HERE / "golden"
CASES = apicases.load_cases(HERE / "cases.yaml")
API_URL = os.environ.get("PARITY_API_URL", "http://localhost:5002")
RECORD = os.environ.get("PARITY_MODE") == "record"

COLLECTED_DIFFS: list = []


@pytest.fixture(scope="session")
def send():
    return apicases.requests_sender(API_URL)


@pytest.mark.parametrize("case", list(CASES))
def test_api_matches_legacy(case, send):
    actual = apicases.run_case(send, CASES[case])
    golden_file = GOLDEN / f"{case}.json"

    if RECORD:
        GOLDEN.mkdir(exist_ok=True)
        golden_file.write_text(json.dumps({"case": case, "steps": actual}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return

    if not golden_file.exists():
        pytest.fail(f"No recorded legacy behaviour for '{case}'. Run `modernize lock` first.")
    golden = json.loads(golden_file.read_text(encoding="utf-8"))["steps"]
    diffs = apicases.diff_case(case, golden, actual)
    COLLECTED_DIFFS.extend(diffs)
    if diffs:
        lines = [f"{d['request']}  {d['path']}: legacy={d['legacy']!r}  new={d['modern']!r}" for d in diffs[:12]]
        more = f"\n  ... and {len(diffs) - 12} more" if len(diffs) > 12 else ""
        pytest.fail(f"Response differs from the legacy API ({len(diffs)} field(s)):\n  " + "\n  ".join(lines) + more, pytrace=False)
