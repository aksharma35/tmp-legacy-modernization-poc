"""Phase 4 -- verify: replay the contract against the new code; a human decides every behaviour change."""
from __future__ import annotations

import json
import sys

from rich.panel import Panel
from rich.prompt import Prompt
from rich.markup import escape
from rich.text import Text

from . import ai, apicases, decisions, gitutil, testing
from .config import Config
from .ui import console, fail, info, ok, step, table, warn

CHOICES = {"k": "keep-legacy", "a": "accept-new", "s": "skip"}


def _short(v) -> str:
    text = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return text if len(text) <= 40 else text[:37] + "…"


def _group_rows(groups: dict[str, list[dict]]) -> list[list]:
    rows = []
    for sig, ds in groups.items():
        first = ds[0]
        cases = sorted({d["case"] for d in ds})
        rows.append([sig, len(ds), _short(first["legacy"]), _short(first["modern"]), ", ".join(cases[:3]) + ("…" if len(cases) > 3 else "")])
    return rows


def _describe(groups: dict[str, list[dict]]) -> str:
    lines = []
    for sig, ds in groups.items():
        examples = "; ".join(f"legacy {_short(d['legacy'])} → new {_short(d['modern'])}" for d in ds[:3])
        lines.append(f"- {sig} ({len(ds)} value(s)): {examples}")
    return "\n".join(lines)


def _apply_accept(cfg: Config, diffs: list[dict]) -> None:
    golden_dir = cfg.root / "parity" / "api" / "golden"
    by_case: dict[str, list[dict]] = {}
    for d in diffs:
        by_case.setdefault(d["case"], []).append(d)
    for case, ds in by_case.items():
        path = golden_dir / f"{case}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for d in ds:
            step_data = data["steps"][d["step"]]
            if d["parts"] == ["status"]:
                step_data["status"] = d["modern"]
            elif d["parts"]:
                apicases.set_at(step_data["body"], d["parts"], d["modern"])
            else:
                step_data["body"] = d["modern"]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def verify_api(cfg: Config, target: str = "modern", use_ai: bool = True, decide: str | None = None) -> bool:
    step("Verify · API parity", "The same recorded requests, replayed against the new backend")
    res = testing.run_api(cfg, target, quiet=True, show=False)
    if res["ok"]:
        ok(f"All {len(res['passed'])} API cases return exactly what the legacy API returned.")
        return True
    diffs = res.get("diffs", [])
    if not diffs:
        fail("API parity failed before any responses could be compared (see output above).")
        return False

    groups = apicases.group_diffs(diffs)
    fail(f"{len(diffs)} value(s) differ from the legacy API, in {len(groups)} field(s). Nothing crashed: the results changed.")
    table("Behaviour changes", ["Endpoint and field", "Values", "Legacy", "New", "Cases"], _group_rows(groups))

    explanation = ""
    if use_ai:
        question = (
            "The parity test replays identical API requests against the legacy Python 2.7 backend "
            "(legacy/backend/app.py) and the new Python 3.12 backend (modern/backend/app.py). "
            "These fields now return different values:\n" + _describe(groups) + "\n\n"
            "For each field, in one or two short sentences: name the line of code responsible and explain "
            "why Python 3 returns a different value. Do not propose or make a fix."
        )
        info(f"Asking the AI why ({cfg.model})…")
        try:
            explanation = ai.ask(cfg, question, read=["legacy/backend/app.py", "modern/backend/app.py"])
            console.print(Panel(Text(explanation), title="AI: probable cause", border_style="magenta"))
        except (RuntimeError, SystemExit) as exc:
            warn(f"Could not get an AI explanation: {exc}")

    console.print("\n[bold]Your call.[/bold] For each field: keep the legacy behaviour, or accept the new one?")
    data = decisions.load(cfg)
    keep, accept = [], []
    reviewer = gitutil.user_name(cfg.root)
    for sig, ds in groups.items():
        if decide:
            choice = decide
        elif not sys.stdin.isatty():
            raise SystemExit("verify needs a decision. Run it in a terminal, or pass --decide keep|accept.")
        else:
            key = Prompt.ask(f"  [cyan]{escape(sig)}[/cyan]  \\[k]eep legacy / \\[a]ccept new / \\[s]kip",
                             choices=list(CHOICES), default="k")
            choice = CHOICES[key]
        if choice == "skip":
            continue
        (keep if choice == "keep-legacy" else accept).append(sig)
        data["behaviour_changes"].append({
            "field": sig,
            "values_changed": len(ds),
            "example": {"case": ds[0]["case"], "legacy": ds[0]["legacy"], "new": ds[0]["modern"]},
            "decision": choice,
            "decided_by": reviewer,
            "at": decisions.now(),
        })
    if explanation:
        data.setdefault("ai_explanations", []).append({
            "at": decisions.now(), "model": cfg.model, "fields": list(groups), "text": explanation,
        })
    decisions.save(cfg, data)

    if accept:
        _apply_accept(cfg, [d for sig in accept for d in groups[sig]])
        sha = gitutil.commit(cfg.root, f"modernize: accept new behaviour for {len(accept)} field(s)",
                             ["parity/api/golden", "migration/decisions.yaml"])
        ok(f"Accepted {len(accept)} change(s); the contract now expects the new values" + (f"  [dim]({sha})[/dim]" if sha else ""))

    if keep:
        gitutil.commit(cfg.root, f"modernize: keep legacy behaviour for {len(keep)} field(s)", ["migration/decisions.yaml"])
        if not use_ai:
            warn("Kept the legacy behaviour; fix modern/backend by hand (or rerun without --no-ai).")
            return False
        message = (
            "A reviewer decided to KEEP the legacy behaviour for these API fields. The legacy values are the expected ones:\n"
            + _describe({s: groups[s] for s in keep}) + "\n\n"
            + ("The reviewer ACCEPTED the new Python 3 behaviour for these fields, so they must stay as they are now:\n"
               + _describe({s: groups[s] for s in accept}) + "\n\n" if accept else "")
            + "Change modern/backend/app.py so the kept fields match the legacy values exactly, on Python 3.12. "
            "Replace each related `MODERNIZE-REVIEW:` comment with a one-line comment that says the legacy Python 2 "
            "behaviour was kept on purpose (decision recorded in migration/decisions.yaml). Change nothing else."
        )
        step("AI step · Claude Code applies your decision",
             f"model: {cfg.model} · at most {cfg.max_attempts} attempts · ${cfg.budget_usd:.2f} cap per attempt")
        applied = ai.edit_until_green(
            cfg, unit="backend-decisions", prompt=message, files=["modern/backend/app.py"],
            read=["legacy/backend/app.py", "migration/decisions.yaml"],
            check=ai.Check(f'"{sys.executable}" -m modernize test api --target {target}',
                           f"modernize test api --target {target}"),
        )
        if not applied:
            return False

    final = testing.run_api(cfg, target, quiet=True, show=False)
    (ok if final["ok"] else fail)(
        "API parity: the new backend now matches the contract." if final["ok"] else "API parity still fails."
    )
    return final["ok"]


def verify_e2e(cfg: Config, target: str, grep: str | None = None, headed: bool = False) -> bool:
    step(f"Verify · browser parity on '{target}'", "The same Playwright tests that pass on the legacy AngularJS app")
    res = testing.run_e2e(cfg, target, grep=grep, headed=headed)
    by_suite: dict[str, list[int]] = {}
    for t in res["tests"]:
        counts = by_suite.setdefault(t["suite"] or "(root)", [0, 0])
        counts[0 if t["status"] == "passed" else 1] += 1
    table(f"Browser parity · {target}", ["Suite", "Passed", "Failed"],
          [[s, p, f or "-"] for s, (p, f) in by_suite.items()])
    for t in res["tests"]:
        if t["status"] == "failed":
            fail(escape(f"{t['suite']} › {t['title']}: {t['error']}"))
    (ok if res["ok"] else fail)(f"{res['passed']} passed, {res['failed']} failed on '{target}'.")
    return res["ok"]
