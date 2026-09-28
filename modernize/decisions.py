"""Human decisions recorded during the migration (migration/decisions.yaml)."""
from __future__ import annotations

from datetime import datetime, timezone

import yaml

from .config import Config


def _path(cfg: Config):
    return cfg.migration / "decisions.yaml"


def load(cfg: Config) -> dict:
    path = _path(cfg)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    return data or {"plan": None, "behaviour_changes": []}


def save(cfg: Config, data: dict) -> None:
    header = "# Decisions made by people during the migration. The pipeline never makes these on its own.\n"
    _path(cfg).write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
