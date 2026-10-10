"""Persistent application log and HTML rendering for the in-app viewer."""

from __future__ import annotations

import html
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from auth_storage import APP_DIR, _restrict
from china_time import CHINA_TIME

LOG_FILE = APP_DIR / "runtime.log"
MAX_MEMORY_LINES = 2000
MAX_FILE_BYTES = 5 * 1024 * 1024
_LINE = re.compile(
    r"^\[(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] "
    r"(?P<level>[A-Z]+) --- (?P<message>.*)$"
)

_lines: list[tuple[str, str, str]] = []
_listeners: list[Callable[[str, str], None]] = []

_LEVEL_COLOR = {
    "INFO": "#63A4FF",
    "WARN": "#F4C95D",
    "ERROR": "#FF6B73",
}


def _load_history(path: Path | None = None) -> None:
    path = LOG_FILE if path is None else path
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for raw in raw_lines[-MAX_MEMORY_LINES:]:
        match = _LINE.match(raw)
        if match:
            _lines.append((match["time"], match["level"],
                           match["message"].replace(r"\n", "\n")))


def _append_file(timestamp: str, level: str, message: str,
                 path: Path | None = None) -> None:
    path = LOG_FILE if path is None else path
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size >= MAX_FILE_BYTES:
            backup = path.with_suffix(".log.1")
            try:
                backup.unlink()
            except FileNotFoundError:
                pass
            path.replace(backup)
            _restrict(backup)
        single_line = message.replace("\r", "").replace("\n", r"\n")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"[{timestamp}] {level} --- {single_line}\n")
        _restrict(path)
    except OSError:
        # Logging must never stop history synchronization or a bet workflow.
        pass


def info(message: str) -> None:
    write("INFO", message)


def warn(message: str) -> None:
    write("WARN", message)


def error(message: str) -> None:
    write("ERROR", message)


def write(level: str, message: str) -> None:
    label = level.strip().upper() or "INFO"
    text = str(message)
    timestamp = datetime.now(CHINA_TIME).strftime("%Y-%m-%d %H:%M:%S")
    _lines.append((timestamp, label, text))
    if len(_lines) > MAX_MEMORY_LINES:
        del _lines[:-MAX_MEMORY_LINES]
    _append_file(timestamp, label, text)
    for listener in list(_listeners):
        listener(label, text)


def history() -> list[tuple[str, str, str]]:
    return list(_lines)


def subscribe(listener: Callable[[str, str], None]) -> Callable[[], None]:
    _listeners.append(listener)

    def cancel() -> None:
        if listener in _listeners:
            _listeners.remove(listener)

    return cancel


def editor_command(path: Path) -> list[str]:
    """Open the log with the system text editor, such as Notepad on Windows."""
    text = str(path)
    if sys.platform == "win32":
        return ["notepad.exe", text]
    if sys.platform == "darwin":
        return ["open", "-e", text]
    return ["xdg-open", text]


def open_in_editor(path: Path | None = None) -> None:
    path = LOG_FILE if path is None else path
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.exists():
        path.touch(mode=0o600)
    _restrict(path)
    subprocess.Popen(editor_command(path))


def clear() -> None:
    """Clear the visible history and both active and rotated log files."""
    for path in (LOG_FILE, LOG_FILE.with_suffix(".log.1")):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    _lines.clear()
    for listener in list(_listeners):
        listener("CLEAR", "")


def format_line(timestamp: str, level: str, message: str) -> str:
    color = _LEVEL_COLOR.get(level, "#DDE6F2")
    label = html.escape(level)
    moment = html.escape(timestamp)
    body = html.escape(message).replace("\n", "<br>")
    return (
        '<p style="margin:0 0 4px 0; line-height:140%; white-space:pre-wrap;">'
        f'<span style="color:{color}; font-weight:700;">{label}</span>'
        f'<span style="color:#8190A5;">&nbsp;&nbsp;{moment}</span>'
        f'<span style="color:#E8EDF4;">&nbsp;&nbsp;—&nbsp;&nbsp;{body}</span>'
        "</p>"
    )


def document_html() -> str:
    return "".join(format_line(timestamp, level, message)
                   for timestamp, level, message in _lines)


_load_history()
