"""Phase 3 -- transform: deterministic codemods first, then Claude Code for what is left."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

import yaml

from . import ai, gitutil, testing
from .config import Config
from .discover import _tool
from .ui import fail, info, ok, step, table, warn


def load_recipe(cfg: Config, name: str) -> dict:
    path = cfg.root / "recipes" / f"{name}.yaml"
    if not path.exists():
        options = ", ".join(p.stem for p in (cfg.root / "recipes").glob("*.yaml"))
        raise SystemExit(f"No recipe '{name}'. Available: {options}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def render(text: str, **values) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def _placeholders(cfg: Config, recipe: dict) -> dict:
    return {
        "python": sys.executable,
        "ruff": _tool("ruff"),
        "source": recipe["source"],
        "target": recipe["target"],
    }


def _load_plan(cfg: Config) -> dict:
    plan_file = cfg.out / "discover" / "plan.json"
    if not plan_file.exists():
        raise SystemExit("No migration plan yet. Run `modernize discover` first.")
    return json.loads(plan_file.read_text(encoding="utf-8"))


# ------------------------------------------------------------ python2to3

def transform_backend(cfg: Config, recipe: dict, use_ai: bool = True, force: bool = False) -> bool:
    ph = _placeholders(cfg, recipe)
    src, dst = cfg.root / recipe["source"], cfg.root / recipe["target"]

    step(f"Transform · {recipe['title']}", "Codemods first, then the AI for what they leave behind")
    if (dst / "app.py").exists():
        if not force:
            raise SystemExit(f"{recipe['target']} already exists. Use --force to start over.")
    if dst.exists():
        shutil.rmtree(dst)

    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    sha = gitutil.commit(cfg.root, f"modernize: copy {recipe['source']} to {recipe['target']}", [recipe["target"]])
    ok(f"Copied {recipe['source']} → {recipe['target']}" + (f"  [dim]({sha})[/dim]" if sha else ""))

    for mod in recipe.get("codemods", []):
        cmd = render(mod["run"], **ph)
        info(f"Codemod: {mod['name']}")
        proc = subprocess.run(cmd, shell=True, cwd=cfg.root, capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0:
            fail(f"{mod['name']} failed:\n{(proc.stderr or proc.stdout)[-1500:]}")
            if "lib2to3" in (proc.stderr or ""):
                warn("2to3 needs Python 3.12 (it was removed in 3.13). Recreate the venv with Python 3.12.")
            return False

    deps = _load_plan(cfg).get("dependencies") or {}
    if deps.get("lock"):
        (dst / "requirements.txt").write_text(
            f"# Resolved for Python {deps['python']} by `modernize discover` (uv pip compile)\n" + deps["lock"], encoding="utf-8")
        info(f"Rewrote {recipe['target']}/requirements.txt with the versions resolved for Python {deps['python']}")

    for rw in recipe.get("rewrites", []):
        path = dst / rw["file"]
        if "content" in rw:
            path.write_text(rw["content"], encoding="utf-8")
        for old, new in rw.get("replace", {}).items():
            path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
        info(f"Rewrote {recipe['target']}/{rw['file']}")

    sha = gitutil.commit(cfg.root, f"codemod: {' + '.join(m['name'].split(' ')[0] for m in recipe.get('codemods', []))} "
                         f"for {recipe['name']} (deterministic, no AI)", [recipe["target"]])
    if sha:
        files, added, removed = gitutil.numstat(cfg.root, sha)
        ok(f"Codemods changed {files} file(s): +{added} −{removed} lines  [dim]({sha})[/dim]")

    if not use_ai:
        warn("Skipping the AI step (--no-ai).")
        return testing.run_smoke(cfg, "modern")

    if testing.run_smoke(cfg, "modern"):
        ok("The codemod output already runs. Nothing for the AI to fix.")
        return True

    plan = _load_plan(cfg)
    findings = "\n".join(
        f"- {f['file']}:{f['line']}  {f['rule']} ({f['kind']})  {f['code']}"
        for f in plan["findings"] if f["migration"] == recipe["name"] and f["kind"] in ("runtime", "semantic")
    )
    message = render(recipe["ai"]["prompt"], findings=findings, **ph)
    step("AI step · Claude Code fixes what the codemods left",
         f"model: {cfg.model} · at most {cfg.max_attempts} attempts · ${cfg.budget_usd:.2f} cap per attempt")
    return ai.edit_until_green(
        cfg,
        unit="backend",
        prompt=message,
        files=[render(p, **ph) for p in recipe["ai"]["edit"]],
        read=[render(p, **ph) for p in recipe["ai"]["read"]],
        check=ai.Check(render(recipe["ai"]["check"], **ph), "modernize test smoke --target modern"),
    )


# ------------------------------------------------------- angularjs-react

def scaffold_frontend(cfg: Config, recipe: dict) -> None:
    sc = recipe["scaffold"]
    dst = cfg.root / recipe["target"]
    if (dst / "package.json").exists():
        return
    shutil.copytree(cfg.root / sc["template"], dst, ignore=shutil.ignore_patterns("node_modules", "dist", "dist-bridge"),
                    dirs_exist_ok=True)
    for c in sc.get("copy", []):
        shutil.copy2(cfg.root / c["from"], dst / c["to"])
    info("Installing React dependencies (npm install)…")
    npm = shutil.which("npm") or "npm"
    subprocess.run([npm, *sc["install"].split()[1:]], cwd=dst, check=True)
    sha = gitutil.commit(cfg.root, "modernize: scaffold React app from templates/react-vite", [recipe["target"]])
    ok(f"Scaffolded {recipe['target']} from {sc['template']}" + (f"  [dim]({sha})[/dim]" if sha else ""))


def transform_frontend(cfg: Config, recipe: dict, only: list[str] | None = None, use_ai: bool = True) -> bool:
    ph = _placeholders(cfg, recipe)
    step(f"Transform · {recipe['title']}", "No codemod exists for a framework change: scaffold, then one unit at a time")
    scaffold_frontend(cfg, recipe)

    plan = _load_plan(cfg)
    units = [u for u in plan["frontend"]["units"] if not only or u["name"] in only]
    unknown = set(only or []) - {u["name"] for u in units}
    if unknown:
        raise SystemExit(f"Unknown unit(s): {', '.join(sorted(unknown))}")

    results = []
    for unit in units:
        target_cfg = recipe["units"].get(unit["name"])
        if not target_cfg:
            warn(f"No mapping for {unit['name']} in the recipe; skipping.")
            continue
        edit = [f"{recipe['target']}/{p}" for p in target_cfg["edit"]]
        check = ai.Check(render(target_cfg["check"], **ph), target_cfg["label"])
        if use_ai:
            spec = {k: v for k, v in unit.items() if k not in ("template_html",)}
            message = render(
                recipe["ai"]["prompt"],
                unit=unit["name"],
                kind=unit["kind"],
                angular_name=unit["angular_name"],
                legacy_files=", ".join(unit["source_files"]),
                files=", ".join(edit),
                spec=json.dumps(spec, indent=2, ensure_ascii=False),
                **ph,
            )
            step(f"AI step · {unit['name']}", f"{unit['kind']} {unit['angular_name']} → {', '.join(edit)}")
            legacy_read = [p.split(" (")[0] for p in unit["source_files"]]
            if unit.get("template_html"):
                legacy_read.append(recipe["source"] + "/index.html")
            read = sorted(set(legacy_read + [render(p, **ph) for p in recipe["ai"]["read"]]))
            passed = ai.edit_until_green(cfg, unit=unit["name"], prompt=message, files=edit,
                                         read=[r for r in read if r not in edit], check=check)
        else:
            passed, _ = check.run(cfg)
        results.append([unit["name"], "✔ parity tests pass" if passed else "✘ blocked: pipeline stopped"])
        if not passed:
            break

    skipped = [u["name"] for u in units[len(results):]]
    results += [[name, "· not started"] for name in skipped]
    table("Frontend migration", ["Unit", "Result"], results)
    return all(r[1].startswith("✔") for r in results)
