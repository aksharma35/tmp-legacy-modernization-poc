"""Project configuration: paths, services and targets from modernize.yaml."""
from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def find_root(start: Path | None = None) -> Path:
    """Walk up from the current directory to the folder holding modernize.yaml."""
    here = (start or Path.cwd()).resolve()
    for folder in [here, *here.parents]:
        if (folder / "modernize.yaml").exists():
            return folder
    raise SystemExit("modernize.yaml not found. Run this command inside the project folder.")


@dataclass
class Service:
    name: str
    start: str
    ready_url: str
    stop: str | None = None
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    detached: bool = False

    def start_argv(self) -> list[str]:
        cmd = self.start.replace("{python}", shlex.quote(sys.executable))
        return shlex.split(cmd, posix=os.name != "nt")


@dataclass
class Target:
    name: str
    services: list[str]
    api_url: str
    web_url: str


class Config:
    def __init__(self, root: Path | None = None):
        self.root = root or find_root()
        raw = yaml.safe_load((self.root / "modernize.yaml").read_text(encoding="utf-8"))
        self.raw = raw
        self.project = raw.get("project", "project")
        self.paths = {k: self.root / v for k, v in raw["paths"].items()}

        self.services: dict[str, Service] = {}
        for name, spec in raw["services"].items():
            self.services[name] = Service(name=name, **spec)

        # Local Python 2.7 instead of Docker, e.g.
        #   MODERNIZE_LEGACY_API_START="/opt/python2.7/bin/python2.7 app.py"
        override = os.environ.get("MODERNIZE_LEGACY_API_START")
        if override:
            legacy = self.services["legacy-api"]
            legacy.start = override
            legacy.stop = None
            legacy.detached = False
            legacy.cwd = raw["paths"]["legacy_backend"]
            legacy.env = {"PORT": "5001", "TEST_HOOKS": "1"}

        self.targets: dict[str, Target] = {}
        for name, spec in raw["targets"].items():
            self.targets[name] = Target(name=name, **spec)

        self.model = os.environ.get("MODERNIZE_MODEL") or raw.get("ai", {}).get("model", "anthropic/claude-sonnet-5")

    # Handy locations -------------------------------------------------------
    @property
    def out(self) -> Path:
        path = self.root / "out"
        path.mkdir(exist_ok=True)
        return path

    @property
    def migration(self) -> Path:
        path = self.root / "migration"
        path.mkdir(exist_ok=True)
        return path

    def target(self, name: str) -> Target:
        if name not in self.targets:
            raise SystemExit(f"Unknown target '{name}'. Choose one of: {', '.join(self.targets)}")
        return self.targets[name]
