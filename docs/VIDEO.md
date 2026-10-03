# Recording the 5-minute video

The video is built around two moments. Everything else supports them.

1. **"It ran and was still wrong."** The upgraded backend starts with zero errors, and only the
   parity check notices the numbers changed, so a silent behaviour change is caught before
   release, not by customers.
2. **"The AI never decides a behaviour change."** The pipeline stops, Claude explains the cause,
   a person chooses *keep* or *accept*, and the decision is logged.

Record the full run (roughly 10–15 minutes with AI and test time), then cut it to 5 minutes. Keep
both moments at normal speed. Speed up installs and AI work 4–8×, with a visible "sped up" label.

## Before you hit record

1. Run `modernize doctor --ai`. Everything should show ✔.
2. Do one full rehearsal on a throwaway branch (`git switch -c rehearsal`), then
   `modernize clean && git switch main && git switch -c take-1`.
3. Set the terminal font to 18–20 pt, use a short prompt, and turn notifications off. Keep your
   API key off screen.
4. Open two browser windows side by side:
   - left: http://localhost:5001 (legacy)
   - right: http://localhost:5173 (React; it only works after the migration step)

## Shot list

| Time | Segment | Command / screen | Say (key line) |
|---|---|---|---|
| 0:00–0:20 | **Hook** | From the take: the `verify --suite api` table, legacy 727 vs new 727.27, "Nothing crashed: the results changed." | "This upgrade started with zero errors, and it was still wrong. Here's how we caught it before a customer did." |
| 0:20–0:45 | **The legacy app** | Legacy app in the browser. Quick look at `legacy/backend/app.py` (`print "..."`, `cmp=`) and `index.html` (`$scope`, `\| filter`) | "Python 2 and AngularJS. Open-source tools do the bulk, Claude Code fills the gaps, and tests decide." |
| 0:45–1:20 | **Discover + lock** | `modernize discover`: the dependency table (all ✔) and findings. `modernize lock`: the four checks and the "Contract" table | "Every dependency has a Python 3 release, so we can start. Then we record how the old app behaves, and prove the tests cover every behaviour in our spec and every risky line." |
| 1:20–2:40 | **Upgrade (both wow moments)** | `modernize transform -r python2to3`: codemod commit, **smoke test red (`cmp` crash)**, Claude Code attempt 1/3, smoke green. Then `modernize verify --suite api`: **values differ, nothing crashed**, Claude's explanation, press **k**, Claude Code applies the decision, green | "It runs, and it's still wrong: Python 3 changed division and rounding. The AI explains why, but it doesn't decide. I do." |
| 2:40–3:45 | **Migrate** | `modernize transform -r angularjs-react`: one unit (SummaryPanel) in full, with its attempt counter and its `@SummaryPanel` tests going green. The other three as a 5-second montage. Then `modernize verify --suite e2e`: 13/13 on React, with both apps side by side | "Each component is done when the same browser tests that pass on AngularJS pass on React. Every attempt is capped at three." |
| 3:45–4:30 | **Report** | `migration/REPORT.md` in VS Code preview: result table, decisions table (who decided), AI steps (attempts, cost), "Who changed what" | "Every AI change is a commit, and the report says what changed, what was proven and who decided." |
| 4:30–5:00 | **Close** | README section 2 | "Silent behaviour changes caught before release, and no behaviour change without a person deciding. Everything's in the repo." |

## What you will actually see

These outputs came from the dry runs.

- **`discover`**
  - "All 6 dependencies have a release for Python 3.12" (Flask 1.1.4 → 3.1.3, and so on).
  - Backend: 11 syntax findings, 1 runtime, 5 semantic.
  - Frontend: 4 units, in the order ExpenseService → SummaryPanel → ExpenseForm → ExpenseList.
- **`lock`:** four ✔ lines: 13 API cases (28 requests) replay identically; 13 browser tests pass;
  all 15 behaviours have a test; all 5 risky lines are executed.
- **`transform -r python2to3`**
  - "Codemods changed 3 file(s)". fissix turns `sorted(rows, cmp=...)` into
    `key=cmp_to_key(...)`, but leaves the `cmp()` call inside the comparison function.
  - Then `✘ Smoke test: 3 request(s) crashed`, with `NameError: name 'cmp' is not defined`.
  - Then "Attempt 1/3 · Claude Code (claude-sonnet-5) …" and `✔ Smoke test`.
- **`verify --suite api`:** "13 value(s) differ from the legacy API, in 3 field(s). Nothing
  crashed: the results changed." The table shows `average` 727 → 727.27,
  `by_category[*].average` 833 → 833.33 and `share_percent` 13.0 → 12.
- **After keep:** "API parity: the new backend now matches the contract."

Claude's own words and edits will differ from take to take. The numbers above come from the
deterministic tools and won't change.

## Safety notes for the recording

- Use an API key with a spend limit, and revoke it after recording. A clean run costs well under
  $1 (see `docs/FEASIBILITY.md`).
- The repo is marked `tmp-`. Delete it when the video is published, or make it permanent.
