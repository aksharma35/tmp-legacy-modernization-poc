# Feasibility check

Before this was handed over for recording, the whole pipeline was built and run end to end in a
Linux sandbox. This page records what was proven there, what was not, and what to check on your
laptop first.

## Environment used

- Ubuntu 24.04, 2 CPUs, 7 GB RAM. No GPU.
- **Python 2.7.18**, compiled from the official CPython source, with Flask 1.1.4 and the pinned
  dependencies from `legacy/backend/requirements.txt`.
- **Python 3.12.11 and 3.13.7** (via uv), one full run each: Flask 3.1.3, Semgrep 1.178.0,
  ruff 0.16.9 and fissix 24.4.24. fissix packages 2to3's fixers separately, so the tooling is not
  tied to the stdlib 2to3 that was deprecated in Python 3.11 and removed in 3.13. Its output
  matched the stdlib 2to3, plus one extra fix (`sort(cmp=...)` → `cmp_to_key`). It also ran on
  Python 3.14 (a pre-release build).
- **uv 0.8** for the dependency gate (`uv pip compile --python-version 3.12`).
- **Node 22.22**: React 19.3.0, Vite 8.3.1, Playwright 1.56.1 (Chromium 141).
- **Claude Code 2.1.287**, run headless: `claude --bare -p`, with only the Read and Edit tools,
  `--permission-mode dontAsk`, path-scoped `Edit(...)` rules, `--max-budget-usd` and `--resume`.

## Verified end to end

A fresh clone ran every step in order, several times. The last run is the `reference-run` branch.

| Step | Result | Time here* |
|---|---|---|
| `discover` | 6 of 6 dependencies resolve for Python 3.12 (Flask 1.1.4 → 3.1.3 …). 17 backend findings (11 syntax, 1 runtime, 5 semantic). 4 AngularJS units extracted by Semgrep, in dependency order. | 5 s |
| `lock` | 13 API cases / 28 requests recorded from the **real Python 2.7** API and replayed identically. 13/13 browser tests pass on AngularJS. All 15 behaviours have a test. All 5 risky lines (74, 98, 100, 106, 126) are executed by an API case. | 14 s |
| `transform -r python2to3` | Resolved pins written; fissix + ruff change 3 files. Smoke test **crashes** (`NameError: name 'cmp' is not defined`). Claude Code fixes it in 1 attempt. | 8 s |
| `verify --suite api` | **13 values differ in 3 fields, with no crash** (integer division, `round()`). Claude explains; keep-legacy is recorded; Claude Code applies it in 1 attempt; 13/13 API cases pass. | 13 s |
| `transform -r angularjs-react` | Scaffold + 4 units, each passing its own tagged browser tests in 1 attempt. | 38 s |
| `verify --suite e2e` | 13/13 browser tests pass on React, in a US time zone on purpose (catches UTC date bugs). | 15 s |
| `report` | `migration/REPORT.md`: result, contract checks, who changed what (codemod / AI / pipeline), attempts and estimated AI cost, decisions, 91.9% backend coverage, rollback. | 1 s |
| `doctor --ai` | Every prerequisite ✔, including one live call through Claude Code. | 3 s |

\* Without real model latency. Expect each AI step to take 20–90 s with Claude.

### The paths a reviewer asked about, also tested

| Path | What happened |
|---|---|
| **A dependency with no Python 3 release** (`MySQL-python` added to the legacy requirements) | `discover` showed ✘ "no Python 3 release (only a Python 2 build, which fails)", exited with an error, and nothing changed. |
| **Tests that miss things** (two API cases removed) | `lock` refused: "B8 has no test" and "legacy/backend/app.py:126 is never executed". `modernize draft-tests` had Claude Code add the cases; `lock` then passed all four checks. |
| **An AI step that never passes** (SummaryPanel forced to keep failing) | 3 attempts, each committed; then the attempts were parked on `modernize/failed-summarypanel-…`, the branch was reset to the last green commit, the remaining units were not started, and the report showed a **Blocked** section. |
| **Claude editing a file it was not given** | Claude Code's own permission rule denied it (`permission_denials` in the output). The pipeline's guard is a second layer. |

## Not verified here, and why

| Item | Why not | What was done instead | What you do |
|---|---|---|---|
| **Claude's own edits** | The sandbox has no API key | The real Claude Code CLI ran every AI step (tools, permissions, resume, budget, retry loop, checks) against a stand-in API that returned edits written by Claude in the build session. This proves the wiring, not the model's output quality. | `modernize doctor --ai`, then one full rehearsal |
| **Docker for Python 2.7** | Docker Hub is blocked in the sandbox | Python 2.7.18 compiled from source, with the same packages and the same line tracer. Checked that the `python:2.7.18-slim` tag exists on Docker Hub. | `modernize setup` builds it; `modernize doctor` checks it |
| **macOS / Windows (WSL 2)** | Linux sandbox only | Nothing in the pipeline is Linux-specific except process groups, which have a Windows branch | Run `doctor`; use WSL 2 on Windows |

## Problems the dry runs found (already fixed)

1. **Tests coupled across units.** Every browser test used to wait for the expense list, so
   SummaryPanel could never pass before ExpenseList was migrated. Each spec now waits only for its
   own unit; cross-unit behaviour lives in `integration.spec.js`.
2. **Mixed decisions.** If a reviewer *accepts* one change and *keeps* another, the fix prompt now
   names both, so the AI doesn't undo the accepted one.
3. **A scope guard that was too eager.** The first version would have discarded any uncommitted
   change outside the step's files, including your own. It now compares before and after each
   attempt and only discards what that attempt changed.
4. **Recording committed before its tests.** `draft-tests` now runs `lock --no-commit` as its check
   and commits the recording after the drafted tests.

## Cost estimate (Claude Sonnet 5 at $2 / $10 per million input / output tokens)

The reference run sent about **76k input and 13k output tokens** across 22 requests in 7 Claude
Code sessions, which Claude Code estimates at **$0.28**. A real model reads more and writes more
than the scripted stand-in, so budget **about $1 per full run** and **$5 for all rehearsals**. The
per-attempt cap (`--max-budget-usd 1.00`) bounds any single step.

## Risks for the recording

| Risk | Mitigation |
|---|---|
| A step still fails after 3 attempts on camera | The pipeline stops cleanly and keeps the attempts on a branch. Re-run that step, or cut to the `reference-run` branch. |
| First Docker build is slow | `modernize setup` builds the image ahead of time. |
| Port clashes (5001, 5002, 5173) | `modernize doctor` flags them; `modernize down` frees ours. |
