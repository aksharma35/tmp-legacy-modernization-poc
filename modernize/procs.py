"""Start, stop and restart the services each target needs."""
from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path

import requests

from .config import Config, Service


def is_up(url: str) -> bool:
    try:
        requests.get(url, timeout=1.5)
        return True
    except requests.RequestException:
        return False


def _run_dir(cfg: Config) -> Path:
    path = cfg.out / "run"
    path.mkdir(exist_ok=True)
    return path


def _pid_file(cfg: Config, name: str) -> Path:
    return _run_dir(cfg) / f"{name}.pid"


def log_file(cfg: Config, name: str) -> Path:
    return _run_dir(cfg) / f"{name}.log"


def log_tail(cfg: Config, name: str, lines: int = 40) -> str:
    path = log_file(cfg, name)
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-lines:])


def _resolve(argv: list[str]) -> list[str]:
    exe = shutil.which(argv[0])
    return [exe or argv[0], *argv[1:]]


def _wait_ready(cfg: Config, svc: Service, proc: subprocess.Popen | None, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_up(svc.ready_url):
            return
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(
                f"{svc.name} exited while starting (code {proc.returncode}).\n--- log ---\n{log_tail(cfg, svc.name)}"
            )
        time.sleep(0.4)
    raise RuntimeError(f"{svc.name} did not answer at {svc.ready_url} within {timeout:.0f}s.\n--- log ---\n{log_tail(cfg, svc.name)}")


def start(cfg: Config, name: str, timeout: float = 120) -> None:
    svc = cfg.services[name]
    cwd = cfg.root / svc.cwd if svc.cwd else cfg.root
    if not cwd.exists():
        raise RuntimeError(f"{name}: folder {cwd.relative_to(cfg.root)} does not exist yet.")
    argv = _resolve(svc.start_argv())
    env = {**os.environ, **svc.env}

    if svc.detached:
        subprocess.run(argv, cwd=cwd, env=env, check=True)
        _wait_ready(cfg, svc, None, timeout)
        return

    log = open(log_file(cfg, name), "w", encoding="utf-8")
    kwargs: dict = {"cwd": cwd, "env": env, "stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(argv, **kwargs)
    _pid_file(cfg, name).write_text(str(proc.pid))
    _wait_ready(cfg, svc, proc, timeout)


def stop(cfg: Config, name: str) -> None:
    svc = cfg.services[name]
    if svc.detached:
        if svc.stop and is_up(svc.ready_url):
            subprocess.run(_resolve(shlex.split(svc.stop)), cwd=cfg.root, check=False)
        return

    pid_path = _pid_file(cfg, name)
    if not pid_path.exists():
        return
    pid = int(pid_path.read_text().strip() or 0)
    pid_path.unlink(missing_ok=True)
    if not pid:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, check=False)
        else:
            os.killpg(pid, signal.SIGTERM)
            for _ in range(50):
                try:
                    os.killpg(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
            else:
                os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    # Wait for the port to free up so a restart can bind it.
    for _ in range(50):
        if not is_up(svc.ready_url):
            break
        time.sleep(0.1)


def ensure(cfg: Config, name: str, restart: bool = False) -> None:
    svc = cfg.services[name]
    managed = _pid_file(cfg, name).exists()
    if restart and managed:
        stop(cfg, name)
    if is_up(svc.ready_url):
        if restart and not managed and not svc.detached:
            raise RuntimeError(
                f"{name} is already running at {svc.ready_url} but was not started by modernize, "
                "so it cannot be restarted to pick up code changes. Stop it and try again."
            )
        return
    start(cfg, name)


def ensure_target(cfg: Config, target: str, restart_backend: bool = False, api_only: bool = False) -> None:
    for name in cfg.target(target).services:
        if api_only and not name.endswith("-api"):
            continue
        ensure(cfg, name, restart=restart_backend and name == "modern-api")


def stop_all(cfg: Config) -> None:
    for name in cfg.services:
        stop(cfg, name)
