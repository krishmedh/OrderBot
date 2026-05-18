"""
Application logging: rotating log file under ``logs/`` plus optional console mirror.

Configured before FastAPI boots so intent classification and QA OpenAI calls are captured.
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings

_app_logging_initialized = False


def _resolve_level(name: str, default: int = logging.INFO) -> int:
    if not name or not isinstance(name, str):
        return default
    try:
        out = getattr(logging, name.upper(), None)
        if isinstance(out, int):
            return out
    except (TypeError, AttributeError):
        pass
    return default


def truncate_for_log(text: str, *, max_chars: int | None = None) -> str:
    limit = max_chars if max_chars is not None else settings.log_openai_max_chars
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated, total_chars={len(text)} limit={limit}]"


def _try_parse_embedded_json(text: str) -> object | None:
    """Parse a string that looks like JSON (e.g. OpenAI ``message.content``)."""
    s = (text or "").strip()
    if not s or s[0] not in "{[":
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def expand_embedded_json_strings(value: object) -> object:
    """
    Recursively replace JSON-in-string values with parsed objects for readable logs.

    OpenAI chat responses often put a JSON object inside ``choices[0].message.content``
    as a single escaped string; expanding it makes dumps indent the inner structure.
    """
    if isinstance(value, dict):
        return {k: expand_embedded_json_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_embedded_json_strings(v) for v in value]
    if isinstance(value, str):
        parsed = _try_parse_embedded_json(value)
        if parsed is not None:
            return expand_embedded_json_strings(parsed)
    return value


def format_json_for_log(obj: object, *, max_chars: int | None = None) -> str:
    try:
        expanded = expand_embedded_json_strings(obj)
        raw = json.dumps(expanded, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        raw = repr(obj) + f" json_error={exc!r}"
    return truncate_for_log(raw, max_chars=max_chars)


def configure_logging() -> None:
    """Attach file (and optional console) handlers to the ``app.*`` logger tree."""
    global _app_logging_initialized
    if _app_logging_initialized:
        return

    log_dir = Path(settings.log_directory)
    if not log_dir.is_absolute():
        log_dir = Path.cwd() / log_dir

    app_logger = logging.getLogger("app")
    configured_root = _resolve_level(settings.log_level or "INFO")
    app_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt=settings.log_format,
        datefmt=settings.log_datefmt,
    )

    if settings.log_file_enabled:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / settings.log_file_name
        fh = RotatingFileHandler(
            log_path,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        file_lvl = _resolve_level(settings.log_file_level or settings.log_level or "INFO")
        if settings.log_openai_dump_full:
            file_lvl = min(file_lvl, logging.INFO)
        fh.setLevel(file_lvl)
        fh.setFormatter(formatter)
        app_logger.addHandler(fh)

    if settings.log_console:
        ch = logging.StreamHandler(stream=sys.stderr)
        ch.setLevel(_resolve_level(settings.log_console_level or "INFO"))
        ch.setFormatter(formatter)
        app_logger.addHandler(ch)

    app_logger.propagate = False

    bootstrap = logging.getLogger("app.bootstrap")
    bootstrap.setLevel(configured_root)

    hint = "(console only)"
    if settings.log_file_enabled:
        hint = str((log_dir.resolve() / settings.log_file_name))
    bootstrap.info(
        "Logging configured: app→%s LOG_LEVEL=%s LOG_OPENAI_DUMP_FULL=%s",
        hint,
        settings.log_level,
        settings.log_openai_dump_full,
    )

    _app_logging_initialized = True


def reopen_for_tests() -> None:
    """Reset flag so tests can re-run configure_logging in isolation."""
    global _app_logging_initialized
    _app_logging_initialized = False
