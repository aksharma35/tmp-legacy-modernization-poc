# Feasibility check

Before this was handed over for recording, the whole pipeline was built and run end to end in a
Linux sandbox. This page records what was proven there, what was not, and what to check on
your laptop first.

## Environment used

- Ubuntu 24.04, 2 CPUs, 7 GB RAM. No GPU.
- **Python 2.7.18**, compiled from the official CPython source, with Flask 1.1.4 and the pinned
  dependencies from `legacy/backend/requirements.txt`.
- **Python 3.12.11** (via uv): Flask 3.1.3, Semgrep 1.178.0, ast-grep 0.45.3, ruff 0.16.9,
  2to3 from the Python 3.12 standard library.
- **Node 22.22**: React 19.3.0, Vite 8.3.1, Playwright 1.56.1 (Chromium 141).
- **Aider 0.86.2**, installed with `uv tool install --python 3.12 aider-chat`.

## Verified end to end

A fresh clone ran every step in order, several times. The last run is the `reference-run`
branch.

| Step | Result | Time here* |
|---|---|---|
| `discover` | 17 backend findings (10 syntax, 2 runtime, 5 semantic). 4 AngularJS units extracted, in dependency order. | 3 s |
| `lock` | 13 API cases / 28 requests recorded from the **real Python 2.7** API, and replayed identically. 13/13 browser tests pass on AngularJS. | 12 s |
| `transform -r python2to3` | 2to3 + ruff change 3 files. The smoke test **crashes** (`cmp=`). Aider applies the fix; its lint check and smoke-test retry loop both fire; the smoke test passes. | 15 s |
| `verify --suite api` | **13 values differ in 3 fields, with no crash** (integer division, `round()`). The AI explanation panel shows; keep-legacy is recorded; Aider restores the behaviour; 13/13 API cases pass. | 21 s |
| `transform -r angularjs-react` | Scaffold + 4 units. Each unit is gated by its own tagged browser tests (build check for the service). All pass. | 65 s |
| `verify --suite e2e` | 13/13 browser tests pass on React, in a US time zone on purpose (catches UTC date bugs). | 15 s |
| `bridge` | React SummaryPanel and ExpenseForm mounted inside the AngularJS page. 13/13 pass, including cross-framework refresh. | 13 s |
| `report` | `migration/REPORT.md` written. It classifies codemod / AI / pipeline commits and shows 91.9% backend coverage from the parity cases. | 1 s |

\* Without real model latency. Expect each AI step to take 20–90 s with Claude.

The three screens (AngularJS, React, hybrid) were screenshotted side by side and render
identically; only the version badge differs.

## Not verified here, and why

| Item | Why not | What was done instead | What you do |
|---|---|---|---|
| **Live Claude calls** | The sandbox has no API key | Aider ran for real, but against a scripted stand-in model that returned reference edits written by Claude. This proved every flag, edit, commit and retry loop, but not the model's own output quality. It also confirmed Aider knows `anthropic/claude-sonnet-5` and `claude-opus-5-5`. | `modernize doctor --ai` (one tiny call), then one rehearsal |
| **Docker for Python 2.7** | Docker Hub is blocked in the sandbox | Python 2.7.18 compiled from source with the same pinned packages. Checked that the `python:2.7.18-slim` tag exists on Docker Hub. | `modernize setup` builds it; `modernize doctor` checks it |
| **macOS / Windows (WSL 2)** | Linux sandbox only | Nothing in the pipeline is Linux-specific except process groups, which have a Windows branch | Run `doctor`; use WSL 2 on Windows |
| **Local model via Ollama** | No GPU; not requested | none | Optional |

## Problems the dry runs found (already fixed)

These are worth knowing because they are the kind of thing a real team hits.

1. **Tests coupled across units.** At first every browser test waited for the expense list to
   load, so the SummaryPanel unit could never pass before ExpenseList was migrated. Each spec now
   waits only for its own unit, and cross-unit behaviour lives in `integration.spec.js`.
2. **Mixed decisions.** If a reviewer *accepts* one change and *keeps* another, the AI fix prompt
   now names both, so the AI doesn't undo the accepted one.
3. **Noise in the AI's view of the crash.** The smoke test now hands Aider just the last
   traceback from the server log, instead of the whole log.

## Cost estimate (Claude Sonnet 5 at $2 / $10 per million input / output tokens)

The measured prompt sizes for one clean run were about **69k input tokens and 15k output tokens**
across 22 requests (including Aider's commit messages and history summaries). That is about
**$0.30**. Real runs take a few retries, so budget **about $1 per full run** and **$5 for all
rehearsals**. Use a key with a spend limit.

## Risks for the recording

| Risk | Mitigation |
|---|---|
| The AI writes a component that still fails after Aider's 3 retries | Re-run that unit with `--unit X`. The tests show exactly what differs. The `reference-run` branch is the fallback. |
| Aider's release pace slowed in 2026 (last release February) | It still resolves current Claude models. Every gate is independent of the agent, so Claude Code or another agent could take its place in `modernize/ai.py`. |
| First Docker build is slow | `modernize setup` builds the image ahead of time. |
| Port clashes (5001, 5002, 5173, 8081) | `modernize doctor` flags them; `modernize down` frees ours. |
