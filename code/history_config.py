"""Non-secret worksheet binding, write mode and date preference."""
from __future__ import annotations

import json
from pathlib import Path
from auth_storage import APP_DIR

CONFIG = APP_DIR / "history.json"


def load_config() -> dict:
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            result = {k: v for k, v in data.items()
                      if k in {"workbook", "source", "copy_workbook", "date"} and isinstance(v, str)}
            result["use_copy"] = data.get("use_copy") is not False
            return result
    except (OSError, ValueError):
        pass
    return {}


def save_config(workbook: str, day: str, source: str = "", use_copy: bool = True,
                copy_workbook: str = "") -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temp = CONFIG.with_suffix(".tmp")
    payload = {
        "workbook": str(Path(workbook).resolve()) if workbook else "",
        "source": str(Path(source).resolve()) if source else "",
        "date": day, "use_copy": use_copy,
        "copy_workbook": str(Path(copy_workbook).resolve()) if copy_workbook else "",
    }
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temp.replace(CONFIG)
