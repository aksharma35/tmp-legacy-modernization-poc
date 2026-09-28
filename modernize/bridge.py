"""Strangler-fig step: mount migrated React components inside the running AngularJS page."""
from __future__ import annotations

import json
import shutil
import subprocess

from . import procs
from .config import Config
from .ui import info, ok, step


def build_hybrid(cfg: Config, units: list[str]) -> None:
    step("Bridge · React inside the legacy AngularJS page", f"Mounting: {', '.join(units)}")
    front = cfg.paths["modern_frontend"]
    if not (front / "node_modules").exists():
        raise SystemExit("Run the angularjs-react transform first (modern/frontend is missing).")

    plan_units = {u["name"]: u for u in json.loads((cfg.out / "discover" / "plan.json").read_text(encoding="utf-8"))["frontend"]["units"]}
    for name in units:
        if name not in plan_units:
            raise SystemExit(f"Unknown unit '{name}'.")
        if not plan_units[name].get("element"):
            raise SystemExit(
                f"{name} is an ng-controller block, not an element. The bridge mounts element-style "
                "directives/components (e.g. SummaryPanel, ExpenseForm)."
            )

    info("Building the React bridge bundle (npm run build:bridge)…")
    subprocess.run([shutil.which("npm") or "npm", "run", "build:bridge", "--silent"], cwd=front, check=True)

    hybrid = cfg.paths["hybrid_frontend"]
    procs.stop(cfg, "hybrid-web")
    if hybrid.exists():
        shutil.rmtree(hybrid)
    shutil.copytree(cfg.paths["legacy_frontend"], hybrid)
    shutil.copy2(front / "dist-bridge" / "react-bridge.js", hybrid / "vendor" / "react-bridge.js")
    shutil.copy2(cfg.root / "bridge" / "react-component.directive.js", hybrid / "js" / "directives" / "react-component.directive.js")

    index = hybrid / "index.html"
    html = index.read_text(encoding="utf-8")
    for name in units:
        tag = plan_units[name]["element"].strip("<>")
        html = html.replace(f"<{tag}></{tag}>", f'<react-component name="{name}"></react-component>')
    html = html.replace(
        '<script src="js/app.js"></script>',
        '<script src="js/app.js"></script>\n  <script src="vendor/react-bridge.js"></script>\n'
        '  <script src="js/directives/react-component.directive.js"></script>',
    )
    html = html.replace('<span class="badge">AngularJS 1.8</span>', f'<span class="badge">AngularJS 1.8 + React ({", ".join(units)})</span>')
    index.write_text(html, encoding="utf-8")
    ok(f"Hybrid page ready in {hybrid.relative_to(cfg.root)}: AngularJS app with {', '.join(units)} rendered by React.")
