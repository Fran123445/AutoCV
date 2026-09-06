"""Application logging shared by every AutoCV pipeline.

The database run tables are useful for structured pipeline and model-call
telemetry. This module covers the other half: a readable, durable operational
log for stage progress, file operations, warnings, and failures.

Operational logs are grouped by pipeline and activated by ``RunLogger`` once
the database has assigned a run id. That gives every run one independent file:
``logs/<pipeline>/run-<id>.log``. A small ``general`` sink is used before the
first run is opened, which keeps import-time and startup warnings visible.
"""

from __future__ import annotations

from pathlib import Path
import re

import atexit
import logging
import os
import threading

from config import ROOT_DIR


DEFAULT_LOG_DIR = ROOT_DIR / "logs"
LOG_DIR = Path(os.getenv("AUTOCV_LOG_DIR") or DEFAULT_LOG_DIR)
LOG_LEVEL = os.getenv("AUTOCV_LOG_LEVEL", "INFO").upper()

_CONFIG_LOCK = threading.Lock()
_HANDLER_MARKER = "autocv-file-handler"


def _level(value: str | int | None) -> int:
    if isinstance(value, int):
        return value

    return getattr(logging, (value or LOG_LEVEL).upper(), logging.INFO)


def _safe_component(value: object, fallback: str) -> str:
    """Turn a pipeline name into one safe, readable directory component."""

    component = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip()).strip("._")
    return (component[:64] or fallback)


def _handler_path(handler: logging.Handler) -> Path | None:
    filename = getattr(handler, "baseFilename", None)
    return Path(filename) if filename else None


def _remove_file_handlers(root: logging.Logger) -> None:
    """Remove handlers owned by this module, leaving application handlers alone."""

    for handler in root.handlers[:]:
        if getattr(handler, "_autocv_marker", None) != _HANDLER_MARKER:
            continue
        handler.flush()
        handler.close()
        root.removeHandler(handler)


def _install_file_handler(path: Path, level: str | int | None) -> Path:
    root = logging.getLogger()
    with _CONFIG_LOCK:
        existing = next(
            (
                handler
                for handler in root.handlers
                if getattr(handler, "_autocv_marker", None) == _HANDLER_MARKER
            ),
            None,
        )
        if existing is not None and _handler_path(existing) == path.resolve():
            existing.setLevel(_level(level))
            root.setLevel(_level(level))
            return path

        _remove_file_handlers(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler._autocv_marker = _HANDLER_MARKER
        handler.setLevel(_level(level))
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        root.addHandler(handler)
        root.setLevel(_level(level))
        logging.captureWarnings(True)

    return path


def configure_logging(level: str | int | None = None) -> Path:
    """Configure the fallback sink and return its path.

    ``RunLogger`` replaces this sink with the current run's pipeline-specific
    file. Keeping this function preserves the useful lazy setup for modules
    that log before a run has started.
    """

    root = logging.getLogger()
    existing = next(
        (
            handler
            for handler in root.handlers
            if getattr(handler, "_autocv_marker", None) == _HANDLER_MARKER
        ),
        None,
    )
    if existing is not None:
        existing.setLevel(_level(level))
        root.setLevel(_level(level))
        return _handler_path(existing) or LOG_DIR / "general" / "autocv.log"

    return _install_file_handler(LOG_DIR / "general" / "autocv.log", level)


def configure_run_logging(
    pipeline: str,
    run_id: int | str,
    level: str | int | None = None,
) -> Path:
    """Switch the operational sink to one file for a database run."""

    category = _safe_component(pipeline, "other")
    filename = f"run-{_safe_component(run_id, 'unknown')}.log"
    return _install_file_handler(LOG_DIR / category / filename, level)


def get_logger(name: str) -> logging.Logger:
    """Return an AutoCV logger, configuring the file sink on first use."""

    configure_logging()
    return logging.getLogger(name)


def close_logging() -> None:
    """Flush and close AutoCV's file handlers, primarily for clean shutdowns."""

    _remove_file_handlers(logging.getLogger())


atexit.register(close_logging)
