# Legacy Modernization with Proven Parity (POC)

> **Temporary repo** for a use-case recording. Safe to delete afterwards.

A small legacy app, an **Expense Tracker** with a **Python 2.7 + Flask 1.x** backend and an
**AngularJS 1.8** frontend, is modernized to **Python 3.12 + Flask 3** and **React 19**.
That covers the two kinds of legacy work:

- an **upgrade** in the same stack (Python 2 → 3)
- a **migration** to another framework (AngularJS → React)

Both run through one pipeline, `modernize`:

- **Open-source tools do the bulk.** Semgrep and ast-grep find what must change. 2to3 and ruff
  rewrite the syntax. Playwright and pytest record how the old app behaves.
- **The AI fills the gaps.** It works through [Aider](https://aider.chat), the open-source coding
  agent, with Claude as the model. Any model Aider supports can be swapped in.
- **Tests decide.** The same tests pass on the old app and the new one. The pipeline never
  decides a behaviour change on its own; it stops and asks a person.

| # | Command | What happens | AI? |
|---|---|---|---|
| 1 | `modernize discover` | Semgrep and ast-grep list outdated patterns and extract a spec per AngularJS unit. You approve the plan. | No |
| 2 | `modernize lock` | Records 13 API cases from the running Python 2.7 API. Runs 13 browser tests on the AngularJS app. This is the contract. | No |
| 3 | `modernize transform -r python2to3` | Copies the backend, runs 2to3 and ruff, then a smoke test. The codemod output crashes (`cmp=`), so Aider fixes it, re-running the smoke test after every edit. | Yes, for leftovers only |
| 4 | `modernize verify --suite api` | Replays the contract. The code runs, but **results changed** (integer division, `round()`). The AI explains why. **You** choose *keep legacy* or *accept new*, and Aider applies your decision. | Explains and fixes; you decide |
| 5 | `modernize transform -r angularjs-react` | Scaffolds React. Aider migrates one unit at a time, and each unit's browser tests are its finish line. | Yes |
| 6 | `modernize verify --suite e2e` | The same 13 browser tests, now against React. | No |
| 7 | `modernize bridge` | Mounts React components **inside the running AngularJS page** (strangler fig) and runs all 13 tests on that hybrid page. | No |
| 8 | `modernize report` | Writes `migration/REPORT.md`: who changed what (codemod / AI / human), the decisions, coverage and rollback. | No |

---

## 1. Set up your laptop (about 15 minutes, once)

**macOS or Linux.** On **Windows**, do everything inside **WSL 2 (Ubuntu)**, and use Docker
Desktop with "WSL integration" turned on. Native Windows has not been tested.

| Tool | Why | Install |
|---|---|---|
| git | Every pipeline step is a commit | `brew install git` / `sudo apt install git` |
| Docker Desktop | Runs the Python 2.7 backend (end-of-life, don't install it natively) | docker.com |
| Node.js **22 LTS** (≥ 20.19) | Vite 8, React, Playwright | nodejs.org or `brew install node@22` |
| [uv](https://docs.astral.sh/uv/) | Gets Python 3.12 and installs everything | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| A Claude API key | The AI steps | console.anthropic.com. **Set a low monthly spend limit.** |

Then:

```bash
git clone https://github.com/aksharma35/tmp-legacy-modernization-poc.git
cd tmp-legacy-modernization-poc

# Python 3.12 exactly: 2to3 was removed in Python 3.13.
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e .

# Aider, the AI coding agent (isolated install, needs Python 3.10-3.12).
uv tool install --python 3.12 aider-chat

export ANTHROPIC_API_KEY=sk-ant-...        # or put it in your shell profile

modernize setup       # Playwright + Chromium, and builds the Python 2.7 Docker image
modernize doctor --ai # every line should be ✔ (--ai makes one tiny real call to Claude)
```

The default model is `anthropic/claude-sonnet-5`. To use another one:
`export MODERNIZE_MODEL=anthropic/claude-opus-5-5`.

## 2. Run the whole use case

Do each attempt on its own branch, so starting over is one command.

```bash
git switch -c take-1

modernize discover                      # read the tables, approve the plan
modernize lock                          # the contract: 13 API cases + 13 browser tests on legacy
modernize transform -r python2to3       # codemods, crash, AI fix, smoke test passes
modernize verify --suite api            # results differ: AI explains, you press k (keep)
modernize transform -r angularjs-react  # AI migrates 4 units, each gated by its own tests
modernize verify --suite e2e            # 13/13 on React
modernize bridge                        # React inside AngularJS, 13/13 again
modernize report                        # migration/REPORT.md
```

To see the apps side by side:

```bash
modernize up legacy   # http://localhost:5001  (AngularJS + Python 2.7)
modernize up modern   # http://localhost:5173  (React + Python 3.12)
modernize up hybrid   # http://localhost:8081  (AngularJS page with React parts)
modernize down        # stop everything
```

**Start over:**

```bash
modernize clean && git switch main && git switch -c take-2
```

Useful extras:

- `modernize transform -r angularjs-react --unit ExpenseList` redoes one unit.
- `modernize verify --headed` shows the browser while the tests run, which is good on camera.
- `modernize test e2e --target legacy` runs one check. These `test` commands are also what Aider
  runs after each edit.

## 3. If an AI run goes wrong on camera

The AI's output differs from run to run; the tests don't. If a unit keeps failing after Aider's
retries, re-run that unit with `--unit`. You can also compare with the branch
**`reference-run`**, which holds a complete run of every step. Its tags are `step-1-discover`,
`step-2-lock`, `step-3-upgrade`, `step-4-verify-api`, `step-5-migrate` and `step-8-report`
(steps 6 and 7 only run tests, so they add no commits).

Be clear about how `reference-run` was made. The repo was built in a sandbox without an API key,
so the AI edits on that branch were **written by Claude during the build session** and applied
through the real Aider, with the real test loop, using a scripted stand-in model. The codemods,
tests, decisions and report on that branch come from the pipeline itself. Your live run with
your API key is the real thing.

## 4. What is where

```
legacy/backend/       Python 2.7 Flask API (planted traps: integer division, round(), cmp=)
legacy/frontend/      AngularJS 1.8 app (planted traps: filter semantics, local-date parsing, currency format)
parity/api/           cases.yaml + pytest: record legacy responses, compare field by field
parity/e2e/           Playwright suite; runs unchanged against legacy, modern and hybrid
rules/semgrep/        Python 2 and AngularJS rules (syntax / runtime / semantic)
recipes/              What the codemods do and what the AI is asked, per migration type
templates/react-vite/ React starter the migration fills in (App.jsx wiring fixed)
bridge/               AngularJS directive that mounts React components (strangler fig)
modernize/            The CLI (Python + Typer)
CONVENTIONS.md        The rules Aider works under, including "never decide a behaviour change"
migration/            Created by the run: PLAN.md, decisions.yaml, REPORT.md
docs/VIDEO.md         The 5-minute recording flow
docs/FEASIBILITY.md   What was verified before handing this over, and what was not
```

## 5. Other setups

- **No Docker?** Point the pipeline at any local Python 2.7:
  `export MODERNIZE_LEGACY_API_START="/path/to/python2.7 app.py"`. Its Flask dependencies are in
  `legacy/backend/requirements.txt`.
- **Local open-source model instead of Claude?** Aider supports Ollama, for example
  `export MODERNIZE_MODEL=ollama_chat/qwen2.5-coder:14b`. This has **not** been tested here.
  Expect more retry rounds on the React migration.
- **Extra Aider flags:** `export MODERNIZE_AIDER_ARGS="--map-tokens 2048"`.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `2to3 needs Python 3.12` | The venv was made with 3.13+. Run `rm -rf .venv && uv venv --python 3.12 .venv`, then reinstall. |
| Legacy API does not start | `docker compose logs legacy-api`. The first build pulls `python:2.7.18-slim`. |
| `Port 5173 in use` | `modernize down`, or stop the other dev server. |
| `ANTHROPIC_API_KEY` errors in Aider | `echo $ANTHROPIC_API_KEY` in the same terminal; check the key's spend limit. |
| A React unit still fails after 3 AI rounds | Re-run that unit with `--unit`, or look at the diff: `git log -p -- modern/frontend/src`. |
