# Legacy Modernization with Proven Parity (POC)

> **Temporary repo** for a use-case recording. Safe to delete afterwards.

A small legacy app, an **Expense Tracker** with a **Python 2.7 + Flask 1.x** backend and an
**AngularJS 1.8** frontend, is modernized to **Python 3.12 + Flask 3** and **React 19**.
That covers the two kinds of legacy work:

- an **upgrade** in the same stack (Python 2 → 3)
- a **migration** to another framework (AngularJS → React)

Both run through one pipeline, `modernize`:

- **Open-source tools do the bulk.** uv checks every dependency has a Python 3 release. Semgrep
  finds what must change. 2to3 and ruff rewrite the syntax. Playwright and pytest record how the
  old app behaves.
- **Claude Code fills the gaps.** It runs headless (`claude -p`), may only read and edit the files
  a step names, and cannot run commands. The pipeline runs the checks and owns the retry loop.
- **Tests decide.** The same tests pass on the old app and the new one. The pipeline never
  decides a behaviour change on its own; it stops and asks a person.

| # | Command | What happens | AI? |
|---|---|---|---|
| 1 | `modernize discover` | **Dependency gate:** every legacy package must have a release for Python 3.12, or the pipeline stops here. Then Semgrep lists outdated patterns and extracts a spec per AngularJS unit. You approve the plan. | No |
| 2 | `modernize lock` | Records 13 API cases from the running Python 2.7 API and runs 13 browser tests on the AngularJS app. Then **proves the tests are enough**: every behaviour in `parity/behaviour.yaml` has a test, and every risky line from step 1 is executed by a test. | No |
| 3 | `modernize transform -r python2to3` | Copies the backend, pins the resolved dependencies, runs 2to3 and ruff, then a smoke test. The codemod output crashes (`cmp=`), so Claude Code fixes it. | Yes, for leftovers only |
| 4 | `modernize verify --suite api` | Replays the contract. The code runs, but **results changed** (integer division, `round()`). Claude explains why. **You** choose *keep legacy* or *accept new*, and Claude Code applies your decision. | Explains and fixes; you decide |
| 5 | `modernize transform -r angularjs-react` | Scaffolds React. Claude Code migrates one unit at a time; each unit's browser tests are its finish line. | Yes |
| 6 | `modernize verify --suite e2e` | The same 13 browser tests, now against React. | No |
| 7 | `modernize report` | Writes `migration/REPORT.md`: who changed what (codemod / AI / pipeline), attempts and AI cost, the decisions, coverage and rollback. | No |

### Limits on every AI step

| Rule | Setting |
|---|---|
| Claude may only edit the files the step names (Read and Edit tools only, no commands) | Claude Code permission rules, plus a pipeline check that discards any other change |
| At most **3 attempts**. After each one the pipeline runs the step's check; a failure goes back to the same Claude session | `ai.max_attempts` in `modernize.yaml` |
| A spend cap on every attempt | `ai.budget_per_attempt_usd` (Claude Code `--max-budget-usd`) |
| **If the last attempt fails:** the attempts are kept on a branch `modernize/failed-<step>-<time>`, your branch goes back to the last commit where every check passed, and the pipeline stops. Nothing after that step runs. | Built in |

Every attempt is its own git commit (`ai: <step> attempt <n> (check passes|fails)`), so any AI
change can be reviewed or reverted.

---

## 1. Set up your laptop (about 15 minutes, once)

**macOS or Linux.** On **Windows**, do everything inside **WSL 2 (Ubuntu)**, and use Docker
Desktop with "WSL integration" turned on. Native Windows has not been tested.

| Tool | Why | Install |
|---|---|---|
| git | Every pipeline step is a commit | `brew install git` / `sudo apt install git` |
| Docker Desktop | Runs the Python 2.7 backend (end-of-life, don't install it natively) | docker.com |
| Node.js **22 LTS** (≥ 20.19) | Vite 8, React, Playwright, Claude Code | nodejs.org or `brew install node@22` |
| [uv](https://docs.astral.sh/uv/) | Gets Python 3.12, installs the tools, runs the dependency gate | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Claude Code | The AI steps | `npm install -g @anthropic-ai/claude-code` |
| A Claude API key | Claude Code runs in bare mode, which uses an API key, not a subscription login | console.anthropic.com. **Set a low monthly spend limit.** |

Then:

```bash
git clone https://github.com/aksharma35/tmp-legacy-modernization-poc.git
cd tmp-legacy-modernization-poc

# The tooling runs on Python 3.12 exactly: 2to3 was deprecated in 3.11 and removed in 3.13.
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e .

export ANTHROPIC_API_KEY=sk-ant-...        # or put it in your shell profile

modernize setup       # Playwright + Chromium, and builds the Python 2.7 Docker image
modernize doctor --ai # every line should be ✔ (--ai makes one tiny real call through Claude Code)
```

The default model is `claude-sonnet-5`. To use another one: `export MODERNIZE_MODEL=claude-opus-5-5`.

## 2. Run the whole use case

Do each attempt on its own branch, so starting over is one command.

```bash
git switch -c take-1

modernize discover                      # dependency gate + findings; approve the plan
modernize lock                          # the contract, plus proof the tests cover the spec and risky lines
modernize transform -r python2to3       # codemods, crash, Claude Code fixes it, smoke test passes
modernize verify --suite api            # results differ: Claude explains, you press k (keep)
modernize transform -r angularjs-react  # Claude Code migrates 4 units, each gated by its own tests
modernize verify --suite e2e            # 13/13 on React
modernize report                        # migration/REPORT.md
```

To see the apps side by side:

```bash
modernize up legacy   # http://localhost:5001  (AngularJS + Python 2.7)
modernize up modern   # http://localhost:5173  (React + Python 3.12)
modernize down        # stop everything
```

**Start over:**

```bash
modernize clean && git switch main && git switch -c take-2
```

Useful extras:

- `modernize draft-tests`: when `lock` reports a gap (a behaviour with no test, or a risky line no
  test executes), Claude Code drafts the missing tests from `parity/behaviour.yaml`, and `lock`
  checks them.
- `modernize transform -r angularjs-react --unit ExpenseList` redoes one unit.
- `modernize verify --headed` shows the browser while the tests run, which is good on camera.
- `modernize test e2e --target legacy` runs one check. These `test` commands are what the AI steps
  use to decide whether an attempt worked.
- `modernize bridge` (not part of the demo) mounts migrated React components inside the running
  AngularJS page and runs the browser suite on that hybrid page.

## 3. If an AI run goes wrong on camera

The AI's output differs from run to run; the tests don't. If a step still fails after 3 attempts,
the pipeline stops, keeps the attempts on a `modernize/failed-…` branch and puts your branch back
to the last green commit. Re-run the step, or look at the attempts with
`git log -p modernize/failed-…`.

You can also compare with the branch **`reference-run`**, which holds a complete run of every
step. `git log --oneline main..origin/reference-run` lists the commits: `modernize:` for the
pipeline, `codemod:` for the deterministic tools and `ai:` for Claude Code's attempts.

Be clear about how `reference-run` was made. The repo was built in a sandbox without an API key.
The real Claude Code CLI ran every AI step, with the real permissions, retry loop and checks, but
against a stand-in API that returned edits **written by Claude during the build session**. The
dependency gate, codemods, tests, decisions and report on that branch come from the pipeline
itself. Your live run with your API key is the real thing.

## 4. What is where

```
legacy/backend/       Python 2.7 Flask API (planted traps: integer division, round(), cmp=)
legacy/frontend/      AngularJS 1.8 app (planted traps: filter semantics, local-date parsing, currency format)
parity/behaviour.yaml What the app must do, written by people; every item needs a test
parity/api/           cases.yaml + pytest: record legacy responses, compare field by field;
                      linetrace.py records which legacy lines the cases execute
parity/e2e/           Playwright suite; runs unchanged against legacy and React
rules/semgrep/        Python 2 and AngularJS rules (syntax / runtime / semantic)
rules/extract/        Semgrep rules that extract each AngularJS unit's spec
recipes/              Dependency target, codemods and what Claude is asked, per migration type
templates/react-vite/ React starter the migration fills in (App.jsx wiring fixed)
modernize/            The CLI (Python + Typer)
CONVENTIONS.md        The rules Claude Code works under, including "never decide a behaviour change"
migration/            Created by the run: PLAN.md, decisions.yaml, REPORT.md
docs/VIDEO.md         The 5-minute recording flow
docs/FEASIBILITY.md   What was verified before handing this over, and what was not
```

## 5. Other setups

- **No Docker?** Point the pipeline at any local Python 2.7:
  `export MODERNIZE_LEGACY_PYTHON=/path/to/python2.7`. Its Flask dependencies are in
  `legacy/backend/requirements.txt`.
- **Code that must stay in your cloud account?** Claude Code can use Claude through Amazon
  Bedrock or Google Cloud instead of the Anthropic API. Not shown or tested here.
- **More attempts or a bigger budget:** `MODERNIZE_MAX_ATTEMPTS=5`, `MODERNIZE_BUDGET_USD=2`.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `2to3 needs Python 3.12` | The venv was made with 3.13+. Run `rm -rf .venv && uv venv --python 3.12 .venv`, then reinstall. |
| `discover` stops at the dependency table | A package has no Python 3.12 release. Replace or upgrade it in `legacy/backend/requirements.txt` first. |
| `lock` says "Not locked" | Add the missing tests it lists, or run `modernize draft-tests`. |
| Legacy API does not start | `docker compose logs legacy-api`. The first build pulls `python:2.7.18-slim`. |
| `Port 5173 in use` | `modernize down`, or stop the other dev server. |
| `ANTHROPIC_API_KEY is not set` | Export it in the same terminal; check the key's spend limit. |
| A step stopped after 3 attempts | See section 3. |
