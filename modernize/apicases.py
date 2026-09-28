"""API parity: run recorded request sequences and compare responses field by field."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

Send = Callable[..., tuple[int, str, str]]  # (method, path, json=, data=, headers=) -> (status, content_type, text)


@dataclass
class Step:
    method: str
    path: str
    json_body: Any = None
    raw: str | None = None
    content_type: str | None = None

    @property
    def label(self) -> str:
        return f"{self.method} {self.path}"


def parse_step(spec: Any) -> Step:
    if isinstance(spec, str):
        method, path = spec.split(None, 1)
        return Step(method.upper(), path)
    if isinstance(spec, dict) and "request" in spec:
        method, path = spec["request"].split(None, 1)
        return Step(method.upper(), path, raw=spec.get("raw"), content_type=spec.get("content_type"))
    if isinstance(spec, dict) and len(spec) == 1:
        (request, body), = spec.items()
        method, path = request.split(None, 1)
        return Step(method.upper(), path, json_body=body)
    raise ValueError(f"Cannot read step: {spec!r}")


def load_cases(cases_file: Path) -> dict[str, list[Step]]:
    data = yaml.safe_load(cases_file.read_text(encoding="utf-8"))
    return {name: [parse_step(s) for s in steps] for name, steps in data["cases"].items()}


def requests_sender(base_url: str) -> Send:
    import requests

    session = requests.Session()

    def send(method, path, json=None, data=None, headers=None):
        res = session.request(method, base_url.rstrip("/") + path, json=json, data=data, headers=headers, timeout=10)
        return res.status_code, res.headers.get("Content-Type", ""), res.text

    return send


def flask_sender(flask_app) -> Send:
    client = flask_app.test_client()

    def send(method, path, json=None, data=None, headers=None):
        res = client.open(path, method=method, json=json, data=data, headers=headers)
        return res.status_code, res.headers.get("Content-Type", ""), res.get_data(as_text=True)

    return send


def run_case(send: Send, steps: list[Step]) -> list[dict]:
    status, _, text = send("POST", "/api/test/reset")
    if status != 204:
        raise RuntimeError(f"Test reset hook returned {status}: {text[:200]}")
    results = []
    for step in steps:
        headers = {"Content-Type": step.content_type} if step.content_type else None
        if step.raw is not None:
            status, ctype, text = send(step.method, step.path, data=step.raw, headers=headers)
        elif step.json_body is not None:
            status, ctype, text = send(step.method, step.path, json=step.json_body)
        else:
            status, ctype, text = send(step.method, step.path)
        if not text.strip():
            body: Any = None
        elif "json" in ctype:
            body = json.loads(text)
        else:
            body = {"_text": text.strip()[:500]}
        results.append({"request": step.label, "status": status, "body": body})
    return results


# ------------------------------------------------------------------ diffing

def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _fmt_path(parts: list) -> str:
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out or "(body)"


def compare(expected: Any, actual: Any, parts: list | None = None) -> list[dict]:
    """Differences between two JSON values. 13 == 13.0 (JSON numbers), 13 != 12.5."""
    parts = parts or []
    if _is_number(expected) and _is_number(actual):
        return [] if float(expected) == float(actual) else [{"parts": parts, "expected": expected, "actual": actual}]
    if isinstance(expected, dict) and isinstance(actual, dict):
        diffs = []
        for key in sorted(set(expected) | set(actual)):
            if key not in actual:
                diffs.append({"parts": parts + [key], "expected": expected[key], "actual": "<missing>"})
            elif key not in expected:
                diffs.append({"parts": parts + [key], "expected": "<missing>", "actual": actual[key]})
            else:
                diffs += compare(expected[key], actual[key], parts + [key])
        return diffs
    if isinstance(expected, list) and isinstance(actual, list):
        diffs = []
        if len(expected) != len(actual):
            diffs.append({"parts": parts + ["length"], "expected": len(expected), "actual": len(actual)})
        for i, (e, a) in enumerate(zip(expected, actual)):
            diffs += compare(e, a, parts + [i])
        return diffs
    if expected == actual and type(expected) is type(actual):
        return []
    return [{"parts": parts, "expected": expected, "actual": actual}]


def diff_case(case: str, golden: list[dict], actual: list[dict]) -> list[dict]:
    diffs = []
    if len(golden) != len(actual):
        return [{"case": case, "step": 0, "request": "(sequence)", "path": "steps", "parts": ["steps"],
                 "legacy": len(golden), "modern": len(actual)}]
    for i, (g, a) in enumerate(zip(golden, actual)):
        if g["status"] != a["status"]:
            diffs.append({"case": case, "step": i, "request": g["request"], "path": "status", "parts": ["status"],
                          "legacy": g["status"], "modern": a["status"]})
            continue
        for d in compare(g["body"], a["body"]):
            diffs.append({"case": case, "step": i, "request": g["request"], "path": _fmt_path(d["parts"]),
                          "parts": d["parts"], "legacy": d["expected"], "modern": d["actual"]})
    return diffs


def signature(diff: dict) -> str:
    """Group key: same endpoint + same field, whatever the row index."""
    field_path = re.sub(r"\[\d+\]", "[*]", diff["path"])
    return f"{diff['request']}  {field_path}"


def group_diffs(diffs: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for d in diffs:
        groups.setdefault(signature(d), []).append(d)
    return groups


def set_at(obj: Any, parts: list, value: Any) -> None:
    for p in parts[:-1]:
        obj = obj[p]
    obj[parts[-1]] = value
