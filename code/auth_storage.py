from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_DIR = Path.home() / ".lottery-sheet-workflow"
AUTH_FILE = APP_DIR / "auth.json"


def _restrict(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def validate_payload(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("登录态必须是 JSON 格式") from exc
    else:
        value = raw
    if not isinstance(value, dict):
        raise ValueError("登录态必须是 JSON 对象")
    # Accept the site's complete localStorage user object or a minimal subset.
    if isinstance(value.get("user"), dict):
        value = value["user"]
    required = ("token", "refreshToken", "uuid")
    missing = [key for key in required if not isinstance(value.get(key), str) or not value[key].strip()]
    if missing:
        raise ValueError("缺少字段：" + ", ".join(missing))
    token = value["token"].strip()
    refresh = value["refreshToken"].strip()
    if len(token) < 40 or len(refresh) < 40:
        raise ValueError("token 或 refreshToken 长度异常，请粘贴完整登录态")
    return {key: value[key] for key in required}


def save(payload: dict[str, Any]) -> None:
    APP_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = AUTH_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    _restrict(temp)
    temp.replace(AUTH_FILE)
    _restrict(AUTH_FILE)


def load() -> dict[str, Any] | None:
    if not AUTH_FILE.exists():
        return None
    try:
        return validate_payload(json.loads(AUTH_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def clear() -> None:
    try:
        AUTH_FILE.unlink()
    except FileNotFoundError:
        pass
