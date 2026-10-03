"""Phase 1 -- discover: find outdated patterns and extract a spec for each AngularJS unit."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import yaml

from .config import Config


def _tool(name: str) -> str:
    """Prefer the copy installed next to this Python (the project venv)."""
    local = Path(sys.executable).parent / (name + (".exe" if sys.platform == "win32" else ""))
    return str(local) if local.exists() else (shutil.which(name) or name)


def _rel(cfg: Config, path: str | Path) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = (cfg.root / p).resolve()
    try:
        return p.relative_to(cfg.root).as_posix()
    except ValueError:
        return p.as_posix()


# ------------------------------------------------------------------- semgrep

def run_semgrep(cfg: Config) -> list[dict]:
    cmd = [_tool("semgrep"), "scan", "--config", str(cfg.root / "rules" / "semgrep"), "--json", "--metrics=off",
           "--disable-version-check", "--quiet", "--exclude", "vendor", str(cfg.paths["legacy_backend"]),
           str(cfg.paths["legacy_frontend"])]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"semgrep failed ({proc.returncode}):\n{proc.stderr[-2000:]}")
    data = json.loads(proc.stdout)
    findings = []
    for r in data["results"]:
        path = _rel(cfg, r["path"])
        line_no = r["start"]["line"]
        try:
            code = (cfg.root / path).read_text(encoding="utf-8").splitlines()[line_no - 1].strip()
        except (IndexError, OSError):
            code = ""
        meta = r["extra"].get("metadata", {})
        findings.append({
            "rule": r["check_id"].split(".")[-1],
            "migration": meta.get("migration"),
            "kind": meta.get("kind"),
            "fixed_by": meta.get("fixed_by"),
            "severity": r["extra"].get("severity"),
            "message": r["extra"].get("message"),
            "file": path,
            "line": line_no,
            "code": code[:160],
        })
    findings.sort(key=lambda f: (f["file"], f["line"]))
    return findings


# ---------------------------------------------------------- dependency gate

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:==\s*([^\s;#]+))?")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _uv_compile(names: list[str], python: str) -> tuple[bool, dict[str, str], str]:
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh")
    proc = subprocess.run([uv, "pip", "compile", "-", "--python-version", python, "--no-header", "--no-annotate", "--quiet"],
                          input="\n".join(names) + "\n", capture_output=True, text=True, encoding="utf-8")
    pins = {}
    for line in proc.stdout.splitlines():
        if "==" in line:
            n, v = line.split("==", 1)
            pins[_norm(n)] = v.strip()
    return proc.returncode == 0, pins, proc.stderr.strip()


def check_dependencies(cfg: Config) -> dict:
    """Every legacy requirement must have a release that installs on the target Python."""
    recipe = yaml.safe_load((cfg.root / "recipes" / "python2to3.yaml").read_text(encoding="utf-8"))
    dep = recipe.get("dependencies", {})
    python = str(dep.get("python", "3.12"))
    req_file = cfg.root / recipe["source"] / dep.get("requirements", "requirements.txt")
    legacy = []
    for line in req_file.read_text(encoding="utf-8").splitlines():
        m = _REQ_NAME.match(line)
        if m and not line.strip().startswith("#"):
            legacy.append({"name": m.group(1), "legacy": m.group(2) or "", "resolved": "", "status": "ok"})
    names = [d["name"] for d in legacy]

    resolved, pins, error = _uv_compile(names, python)
    blocked = []
    if not resolved:
        # Find which packages block the resolution, one at a time.
        for d in legacy:
            alone_ok, _, alone_err = _uv_compile([d["name"]], python)
            if not alone_ok:
                d["status"] = "blocked"
                d["reason"] = ("no Python 3 release (only a Python 2 build, which fails)" if "Failed to build" in alone_err
                               else f"no release that installs on Python {python}")
                blocked.append(d["name"])
        # Show what the remaining packages would resolve to.
        _, pins, _ = _uv_compile([d["name"] for d in legacy if d["status"] == "ok"], python)
    for d in legacy:
        d["resolved"] = pins.get(_norm(d["name"]), "")
    return {
        "python": python,
        "requirements": _rel(cfg, req_file),
        "packages": legacy,
        "blocked": blocked,
        "ok": resolved,
        "error": "" if resolved else error[-1500:],
        "lock": "".join(f"{n}=={v}\n" for n, v in sorted(pins.items())) if resolved and not blocked else "",
    }


# ------------------------------------------------- structural extraction

def semgrep_matches(cfg: Config, rules: Path, target: Path) -> list[dict]:
    """Run extraction rules; return each match with its file and exact matched text."""
    cmd = [_tool("semgrep"), "scan", "--config", str(rules), "--json", "--metrics=off", "--disable-version-check",
           "--quiet", str(target)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"semgrep failed ({proc.returncode}):\n{proc.stderr[-2000:]}")
    texts: dict[str, bytes] = {}
    out = []
    for r in json.loads(proc.stdout)["results"]:
        path = r["path"]
        if path not in texts:
            texts[path] = Path(path).read_bytes()
        snippet = texts[path][r["start"]["offset"]:r["end"]["offset"]].decode("utf-8")
        out.append({"rule": r["check_id"].split(".")[-1], "file": _rel(cfg, path), "line": r["start"]["line"],
                    "text": snippet})
    out.sort(key=lambda m: (m["file"], m["line"]))
    return out


# Read the names out of each matched snippet.
_REGISTER = re.compile(r"angular\.module\([^)]*\)\s*\.\s*(\w+)\s*\(\s*['\"]([^'\"]+)['\"]")
_FIRST_FN = re.compile(r"function\s*\(([^)]*)\)")
_ASSIGN = re.compile(r"\$scope\.(\w+)\s*=\s*(function\b)?")
_FIRST_ARG = re.compile(r"\(\s*(['\"][^'\"]*['\"])")
_HTTP = re.compile(r"\$http(?:\.(\w+)|\[\s*['\"](\w+)['\"]\s*\])\s*\(\s*([^,)]+)")
_CONFIRM = re.compile(r"confirm\((.*)\)\s*$", re.S)


def _unquote(s: str) -> str:
    return s.strip().strip("'\"")


def _pascal(name: str) -> str:
    name = re.sub(r"(Ctrl|Controller)$", "", name)
    return name[:1].upper() + name[1:]


def _kebab(name: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"-\1", name).lower()


class _ElementGrabber(HTMLParser):
    """Return the outer HTML of the first element whose attribute matches."""

    VOID = {"input", "br", "img", "meta", "link", "hr", "source", "area", "col", "embed", "param", "track", "wbr"}

    def __init__(self, attr: str, value: str):
        super().__init__(convert_charrefs=False)
        self.attr, self.value = attr, value
        self.depth = 0
        self.start = self.end = None

    def handle_starttag(self, tag, attrs):
        if self.end is not None:
            return
        if self.start is None:
            if dict(attrs).get(self.attr) == self.value:
                self.start = self.getpos()
                self.depth = 1
            return
        if tag not in self.VOID:
            self.depth += 1

    def handle_endtag(self, tag):
        if self.start is None or self.end is not None:
            return
        self.depth -= 1
        if self.depth == 0:
            self.end = self.getpos()


def _outer_html(text: str, attr: str, value: str) -> str:
    grabber = _ElementGrabber(attr, value)
    grabber.feed(text)
    if grabber.start is None or grabber.end is None:
        return ""
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    s = offsets[grabber.start[0] - 1] + grabber.start[1]
    e = offsets[grabber.end[0] - 1] + grabber.end[1]
    end_close = text.find(">", e) + 1
    return text[s:end_close]


def template_features(html: str) -> dict:
    def attr_values(name: str) -> list[str]:
        return sorted(set(re.findall(rf'{name}="([^"]+)"', html)))

    filters = sorted(set(m.strip() for m in re.findall(r"(?<!\|)\|(?!\|)\s*([a-zA-Z]+(?:\s*:\s*[^|}\")]+)?)", html)))
    return {
        "ng-model": attr_values("ng-model"),
        "ng-repeat": attr_values("ng-repeat"),
        "filters": filters,
        "events": attr_values("ng-click") + attr_values("ng-submit"),
        "conditionals": attr_values("ng-show") + attr_values("ng-if") + attr_values("ng-disabled"),
        "validation": sorted(set(re.findall(r"\b(required|min=\"\d+\"|maxlength=\"\d+\"|step=\"\d+\")", html))),
        "labels": sorted(set(re.findall(r"<label[^>]*>([^<]+)</label>", html))),
        "aria_labels": attr_values("aria-label"),
    }


def extract_units(cfg: Config) -> list[dict]:
    front = cfg.paths["legacy_frontend"]
    matches = semgrep_matches(cfg, cfg.root / "rules" / "extract" / "angularjs-units.yml", front / "js")
    by_file: dict[str, list[dict]] = {}
    for m in matches:
        by_file.setdefault(m["file"], []).append(m)
    index_html = (front / "index.html").read_text(encoding="utf-8")

    regs = []
    for m in matches:
        if m["rule"] == "x-register":
            reg = _REGISTER.search(m["text"])
            if reg:
                fn = _FIRST_FN.search(m["text"])
                injects = [p.strip() for p in fn.group(1).split(",") if p.strip()] if fn else []
                regs.append({"file": m["file"], "kind": reg.group(1), "name": reg.group(2), "injects": injects,
                             "text": m["text"]})
    names = {r["name"] for r in regs}

    units = []
    for reg in regs:
        file, kind, angular_name, injects = reg["file"], reg["kind"], reg["name"], reg["injects"]
        name = _pascal(angular_name)
        src = reg["text"]
        found = by_file.get(file, [])

        def texts(rule: str) -> list[str]:
            return [m["text"] for m in found if m["rule"] == rule]

        state, handlers = [], []
        for t in texts("x-scope-assign"):
            a = _ASSIGN.search(t)
            if a:
                (handlers if a.group(2) else state).append(a.group(1))

        def first_args(rule: str) -> list[str]:
            return [a.group(1) for t in texts(rule) if (a := _FIRST_ARG.search(t))]

        spec = {
            "name": name,
            "angular_name": angular_name,
            "kind": kind,
            "source_files": [file],
            "injects": injects,
            "depends_on": sorted(_pascal(i) for i in injects if i in names),
            "scope_state": sorted(set(state)),
            "handlers": sorted(set(handlers)),
            "watches": first_args("x-watch"),
            "listens": [_unquote(e) for e in first_args("x-listen")],
            "emits": [_unquote(e) for e in first_args("x-emit")],
            "http": [],
            "dialogs": [c.group(1).strip() for t in texts("x-confirm") if (c := _CONFIRM.search(t))],
        }
        for t in texts("x-http"):
            h = _HTTP.search(t)
            if h:
                spec["http"].append({"method": (h.group(1) or h.group(2)).upper(), "url": h.group(3).strip()})

        template_url = re.search(r"templateUrl:\s*'([^']+)'", src)
        if template_url:
            tpl_file = front / template_url.group(1)
            spec["template_file"] = _rel(cfg, tpl_file)
            spec["source_files"].append(spec["template_file"])
            html = tpl_file.read_text(encoding="utf-8")
        elif kind == "controller":
            html = _outer_html(index_html, "ng-controller", angular_name)
            spec["template_file"] = _rel(cfg, front / "index.html") + f' (element with ng-controller="{angular_name}")'
            spec["template_html"] = html
        else:
            html = ""

        if kind in ("directive", "component"):
            spec["element"] = f"<{_kebab(angular_name)}>"
        spec["template"] = template_features(html) if html else {}
        units.append(spec)
    return units


def attach_notes(units: list[dict], findings: list[dict], index_file: str) -> None:
    """Attach the semantic findings from each unit's own files (and its index.html block)."""
    for unit in units:
        files = set(unit["source_files"])
        notes = []
        for f in findings:
            if f["migration"] != "angularjs-react":
                continue
            in_index = f["file"] == index_file and unit.get("template_html") and f["code"] and f["code"] in unit["template_html"]
            if f["file"] in files or in_index:
                if f["kind"] == "semantic" or f["severity"] == "WARNING":
                    notes.append(f["message"])
        unit["behaviour_notes"] = sorted(set(notes))


def order_units(units: list[dict]) -> list[dict]:
    by_name = {u["name"]: u for u in units}
    depth: dict[str, int] = {}

    def d(name: str) -> int:
        if name not in depth:
            depth[name] = 0 if not by_name[name]["depends_on"] else 1 + max(d(x) for x in by_name[name]["depends_on"])
        return depth[name]

    def complexity(u: dict) -> int:
        tpl = u.get("template", {})
        return len(u["behaviour_notes"]) + len(tpl.get("ng-model", [])) + len(tpl.get("events", [])) + len(u["handlers"])

    for u in units:
        u["complexity"] = complexity(u)
    return sorted(units, key=lambda u: (d(u["name"]), u["complexity"], u["name"]))


def build_plan(cfg: Config) -> dict:
    deps = check_dependencies(cfg)
    findings = run_semgrep(cfg)
    units = extract_units(cfg)
    index_file = _rel(cfg, cfg.paths["legacy_frontend"] / "index.html")
    attach_notes(units, findings, index_file)
    units = order_units(units)

    backend = [f for f in findings if f["migration"] == "python2to3"]
    frontend = [f for f in findings if f["migration"] == "angularjs-react"]
    count = lambda fs, key, val: sum(1 for f in fs if f[key] == val)  # noqa: E731

    plan = {
        "project": cfg.project,
        "dependencies": deps,
        "findings": findings,
        "backend": {
            "recipe": "python2to3",
            "files": sorted({f["file"] for f in backend}),
            "syntax": count(backend, "kind", "syntax"),
            "runtime": count(backend, "kind", "runtime"),
            "semantic": count(backend, "kind", "semantic"),
        },
        "frontend": {
            "recipe": "angularjs-react",
            "units": units,
            "findings": len(frontend),
            "semantic": count(frontend, "kind", "semantic"),
        },
    }

    out = cfg.out / "discover"
    (out / "units").mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    for u in units:
        (out / "units" / f"{u['name']}.json").write_text(json.dumps(u, indent=2, ensure_ascii=False), encoding="utf-8")
    (cfg.migration / "PLAN.md").write_text(plan_markdown(plan), encoding="utf-8")
    return plan


def plan_markdown(plan: dict) -> str:
    b, f = plan["backend"], plan["frontend"]
    lines = [
        f"# Migration plan: {plan['project']}",
        "",
        "Generated by `modernize discover` from dependency resolution and Semgrep. Approve it before any code changes.",
        "",
        "## 1. Backend: Python 2.7 → Python 3.12 (recipe `python2to3`)",
        "",
        f"### Dependencies (must install on Python {plan['dependencies']['python']})",
        "",
        "| Package | Legacy | Python " + plan["dependencies"]["python"] + " | Status |",
        "|---|---|---|---|",
        *[f"| {d['name']} | {d['legacy'] or '-'} | {d['resolved'] or '-'} | "
          f"{'✅' if d['status'] == 'ok' else '❌ ' + d.get('reason', 'blocked')} |" for d in plan["dependencies"]["packages"]],
        "",
        "### Code findings",
        "",
        "| What | Count | Handled by |",
        "|---|---|---|",
        f"| Syntax changes | {b['syntax']} | codemods (fissix, ruff) |",
        f"| Runtime breaks the codemods leave behind | {b['runtime']} | AI (Claude Code), checked by smoke tests |",
        f"| Silent behaviour changes | {b['semantic']} | parity tests catch them, a human decides |",
        "",
        "| File:line | Rule | Kind | Code |",
        "|---|---|---|---|",
    ]
    for fd in plan["findings"]:
        if fd["migration"] == "python2to3":
            code = fd["code"].replace("|", "\\|")
            lines.append(f"| {fd['file']}:{fd['line']} | {fd['rule']} | {fd['kind']} | `{code}` |")
    lines += [
        "",
        "## 2. Frontend: AngularJS 1.8 → React 19 (recipe `angularjs-react`)",
        "",
        "Units are migrated in this order: dependencies first, then the simplest units first.",
        "",
        "| # | Unit | AngularJS | Depends on | Behaviours to preserve | Parity tests |",
        "|---|---|---|---|---|---|",
    ]
    for i, u in enumerate(f["units"], 1):
        deps = ", ".join(u["depends_on"]) or "-"
        tests = f"`@{u['name']}`" if u["kind"] != "factory" else "build check"
        lines.append(f"| {i} | {u['name']} | {u['kind']} `{u['angular_name']}` | {deps} | {len(u['behaviour_notes'])} | {tests} |")
    lines += ["", "After the last unit, the `@integration` browser tests check that the units still refresh each other "
              "(add or delete an expense → list and summary update).", "", "### Behaviours to preserve", ""]
    for u in f["units"]:
        if u["behaviour_notes"]:
            lines.append(f"**{u['name']}**")
            lines += [f"- {n}" for n in u["behaviour_notes"]]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
