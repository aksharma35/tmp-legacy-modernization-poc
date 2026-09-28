# Recording the 5-minute video

Record the full run (it comes to roughly 10–15 minutes including AI and test time), then cut it
to 5 minutes. Keep the failing-test moments at normal speed. Speed up installs and AI "thinking"
4–8×, with a visible "sped up" label.

## Before you hit record

1. Run `modernize doctor`. Everything should show ✔.
2. Do one full rehearsal on a throwaway branch (`git switch -c rehearsal`), then
   `modernize clean && git switch main && git switch -c take-1`.
3. Set the terminal font to 18–20 pt, use a short prompt, and turn notifications off. Keep
   `.env` and your API key off screen.
4. Open two browser windows side by side:
   - left: http://localhost:5001 (legacy)
   - right: http://localhost:5173 (React; it only works after step 5)

## Shot list

| Time | Segment | Command / screen | Say (key line) |
|---|---|---|---|
| 0:00–0:20 | **Hook** | End result, from the take: legacy on the left, React on the right, then `modernize verify --suite e2e --headed` passing 13/13 | "Same app, two frameworks, one test suite proving they behave the same." |
| 0:20–0:45 | **The legacy app** | Legacy app in the browser. Quick look at `legacy/backend/app.py` (`print "..."`, `cmp=`) and `index.html` (`$scope`, `\| filter`) | "Python 2 and AngularJS: the app nobody wants to touch. Open-source tools do the bulk, AI fills the gaps, tests decide." |
| 0:45–1:15 | **Discover + lock** | `modernize discover` (the two tables), then `modernize lock` (the "Contract locked" table) | "First we record how the old app actually behaves: 13 API cases, 13 browser tests. That's the contract." |
| 1:15–2:30 | **Upgrade** | `modernize transform -r python2to3`: codemod commit, **smoke test red (cmp crash)**, Aider fixes it, green. Then `modernize verify --suite api`: **values differ, nothing crashed**, AI explanation panel, press **k** | "It runs with no errors, and it's still wrong. Python 3 changed division and rounding. The pipeline doesn't guess; it asks me." |
| 2:30–3:50 | **Migrate** | `modernize transform -r angularjs-react`: show one unit (SummaryPanel) in full, with Aider writing the file and the `@SummaryPanel` tests going green. The other three as a 5-second montage. Then `modernize bridge`: the badge shows *AngularJS 1.8 + React*, 13/13 | "Each component is done when the same browser tests pass. And it can run inside the old app, so nothing goes offline." |
| 3:50–4:15 | **Model / tools** | `git log --oneline` (codemod vs AI commits). Optional: `MODERNIZE_MODEL=... modernize transform -r angularjs-react --unit SummaryPanel` | "Aider is open source and the model is one setting. The tests are the judge, not the model." |
| 4:15–4:40 | **Report** | `migration/REPORT.md` in VS Code preview: result table, "Who changed what", decisions table | "Every change is a commit, and the report says who decided what." |
| 4:40–5:00 | **Your turn** | README section 2 | "Everything's in the repo. Write a recipe for your stack and run the same pipeline." |

## What you will actually see

These outputs came from the dry runs.

- **`discover`**
  - Backend: 10 syntax findings, 2 runtime, 5 semantic.
  - Frontend: 4 units, in the order ExpenseService → SummaryPanel → ExpenseForm → ExpenseList.
- **`lock`:** "Recorded 13 API cases (28 requests)" and "13 browser tests pass on the legacy
  AngularJS app".
- **`transform -r python2to3`**
  - "Codemods changed 3 file(s)".
  - Then `✘ Smoke test: 4 request(s) crashed`, with `TypeError: 'cmp' is an invalid keyword
    argument for sort()`.
  - Then the Aider session, then `✔ Smoke test`.
- **`verify --suite api`:** "13 value(s) differ from the legacy API, in 3 field(s). Nothing
  crashed: the results changed." The table shows `average` 727 → 727.27,
  `by_category[*].average` 833 → 833.33 and `share_percent` 13.0 → 12.
- **After keep:** "API parity: the new backend now matches the contract."

The AI's own words and edits will differ from take to take. The numbers above come from the
deterministic tools and won't change.

## Safety notes for the recording

- Use an API key with a spend limit, and revoke it after recording.
- The repo is marked `tmp-`. Delete it when the video is published, or make it permanent.
