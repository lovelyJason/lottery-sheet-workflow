"""Local site address and bet parameters. Kept apart from the login file."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from auth_storage import APP_DIR, _restrict
from china_time import CHINA_TIME
from play_options import normalize_play_selection

SETTINGS_FILE = APP_DIR / "settings.json"


@dataclass
class Settings:
    url: str
    bet_count: int | None
    bet_points: int | None
    poll_interval: int | None
    auto_bet: bool = False
    bet_start_offset: int = 1
    profit_limit: int | None = None
    loss_limit: int | None = None
    today_profit: float | None = None
    profit_date: str = ""
    profit_halt_date: str = ""
    profit_halt_reason: str = ""
    bet_points_schedule: tuple[int, ...] = ()
    profit_poll_interval: int | None = None
    play_mode: str = "play1"
    play2_logic: str = "logic1"


def load_settings() -> Settings:
    if not SETTINGS_FILE.exists():
        return Settings(url="", bet_count=None, bet_points=None, poll_interval=None)
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Settings(url="", bet_count=None, bet_points=None, poll_interval=None)
    if not isinstance(raw, dict):
        return Settings(url="", bet_count=None, bet_points=None, poll_interval=None)
    url = raw.get("url") if isinstance(raw.get("url"), str) else ""
    count = _stored_positive(raw.get("bet_count"))
    legacy_points = _stored_positive(raw.get("bet_points"))
    schedule = _stored_schedule(raw.get("bet_points_schedule"), count)
    if not schedule and count is not None and legacy_points is not None:
        schedule = (legacy_points,) * count
    play_mode, play2_logic = normalize_play_selection(
        raw.get("play_mode"), raw.get("play2_logic")
    )
    return Settings(
        url=url.strip(),
        bet_count=count,
        bet_points=schedule[0] if schedule else legacy_points,
        poll_interval=_stored_positive(raw.get("poll_interval")),
        auto_bet=raw.get("auto_bet") is True,
        bet_start_offset=_stored_positive(raw.get("bet_start_offset")) or 1,
        profit_limit=_stored_positive(raw.get("profit_limit")),
        loss_limit=_stored_positive(raw.get("loss_limit")),
        today_profit=_stored_number(raw.get("today_profit")),
        profit_date=raw.get("profit_date") if isinstance(raw.get("profit_date"), str) else "",
        profit_halt_date=(raw.get("profit_halt_date")
                          if isinstance(raw.get("profit_halt_date"), str) else ""),
        profit_halt_reason=(raw.get("profit_halt_reason")
                            if isinstance(raw.get("profit_halt_reason"), str) else ""),
        bet_points_schedule=schedule,
        profit_poll_interval=_stored_positive(raw.get("profit_poll_interval")),
        play_mode=play_mode,
        play2_logic=play2_logic,
    )


def save_url(raw: str) -> str:
    url = normalize_url(raw)
    data = _read()
    data["url"] = url
    _write(data)
    return url


def save_poll_intervals(history_raw: str, profit_raw: str) -> tuple[int, int]:
    interval = parse_positive(history_raw, "查询与下注轮询时间间隔")
    profit_interval = parse_positive(profit_raw, "查询盈亏值时间间隔")
    if interval > 2_147_483 or profit_interval > 2_147_483:
        raise ValueError("轮询时间间隔最多为2147483秒")
    data = _read()
    data["poll_interval"] = interval
    data["profit_poll_interval"] = profit_interval
    _write(data)
    return interval, profit_interval


def save_poll_interval(raw: str) -> int:
    """Compatibility wrapper for older callers; preserve the profit interval."""
    current = load_settings()
    interval, _ = save_poll_intervals(
        raw, str(current.profit_poll_interval or current.poll_interval or 60)
    )
    return interval


def save_play_selection(play_mode: str, play2_logic: str) -> tuple[str, str]:
    """Persist the workflow selected for the next task start."""
    normalized = normalize_play_selection(play_mode, play2_logic)
    if normalized != (play_mode, play2_logic):
        raise ValueError("玩法或玩法二逻辑无效")
    data = _read()
    data["play_mode"], data["play2_logic"] = normalized
    _write(data)
    return normalized


def save_bets(count_raw: str, points_raw: str | list[str] | tuple[str, ...], auto_bet: bool = False,
              delay_raw: str = "0", profit_limit_raw: str = "",
              loss_limit_raw: str = "") -> tuple[int, tuple[int, ...]]:
    count = parse_positive(count_raw, "投注次数")
    if count > 100:
        raise ValueError("连续投注期数最多为100期")
    raw_schedule = [points_raw] if isinstance(points_raw, str) else list(points_raw)
    if len(raw_schedule) != count:
        raise ValueError(f"请为连续投注的 {count} 期分别填写每注积分")
    schedule = tuple(
        parse_positive(str(raw), f"第 {index} 期每注积分")
        for index, raw in enumerate(raw_schedule, 1)
    )
    delay = parse_nonnegative(delay_raw, "延后期数")
    start_offset = delay + 1
    profit_limit = parse_optional_positive(profit_limit_raw, "盈利停止值")
    loss_limit = parse_optional_positive(loss_limit_raw, "亏损停止值")
    data = _read()
    data["bet_count"] = count
    data["bet_points"] = schedule[0]
    data["bet_points_schedule"] = list(schedule)
    data["auto_bet"] = bool(auto_bet)
    data["bet_start_offset"] = start_offset
    data["profit_limit"] = profit_limit
    data["loss_limit"] = loss_limit
    halted, reason = profit_halt(data.get("today_profit"), data.get("profit_date", ""),
                                 profit_limit, loss_limit)
    data["profit_halt_date"] = site_day() if halted else ""
    data["profit_halt_reason"] = reason
    _write(data)
    # Saving the dialog explicitly starts a fresh campaign, even when values
    # are unchanged.  Keep the cross-campaign issue reservations so saving or
    # changing rules cannot make the currently open issue eligible twice.
    _restart_bet_campaign()
    return count, schedule


def _restart_bet_campaign() -> None:
    path = APP_DIR / "bet_state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(state, dict) or not isinstance(state.get("attempted"), list):
        return
    restarted = {
        "fingerprint": "",
        "trigger_issue": None,
        "completed": 0,
        "attempted": state["attempted"][-500:],
    }
    temp = path.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps(restarted, ensure_ascii=False), encoding="utf-8")
        _restrict(temp)
        temp.replace(path)
        _restrict(path)
    except OSError:
        try:
            temp.unlink()
        except OSError:
            pass


def save_profit_snapshot(value: float) -> tuple[bool, str]:
    """Persist the current value and latch today's stop once a limit is reached."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("今日盈亏值格式异常")
    data = _read()
    day = site_day()
    numeric = float(value)
    already_halted = data.get("profit_halt_date") == day
    if already_halted:
        halted = True
        reason = str(data.get("profit_halt_reason") or "今日已达到盈亏停止值")
    else:
        halted, reason = profit_halt(
            numeric, day, data.get("profit_limit"), data.get("loss_limit")
        )
    data["today_profit"] = numeric
    data["profit_date"] = day
    data["profit_halt_date"] = day if halted else ""
    data["profit_halt_reason"] = reason
    _write(data)
    return halted, reason


def profit_halt(value, value_day: str, profit_limit, loss_limit) -> tuple[bool, str]:
    if value_day != site_day() or isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, ""
    if profit_limit is not None and value >= profit_limit:
        return True, f"今日盈利 {value:g} 已达到停止值 {profit_limit}"
    if loss_limit is not None and value <= -loss_limit:
        return True, f"今日亏损 {abs(value):g} 已达到停止值 {loss_limit}"
    return False, ""


def site_day() -> str:
    return datetime.now(CHINA_TIME).date().isoformat()


def normalize_url(raw: str) -> str:
    text = raw.strip()
    if not text:
        raise ValueError("请填写网页地址")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("网页地址需要以 http:// 或 https:// 开头")
    return text


def parse_positive(raw: str, label: str) -> int:
    text = raw.strip()
    if not text.isdigit() or text[0] == "0":
        raise ValueError(f"{label}只能填正整数")
    value = int(text)
    if value < 1 or value > 999_999_999:
        raise ValueError(f"{label}只能填正整数")
    return value


def parse_optional_positive(raw: str, label: str) -> int | None:
    return None if not raw.strip() else parse_positive(raw, label)


def parse_nonnegative(raw: str, label: str) -> int:
    text = raw.strip()
    if not text.isdigit():
        raise ValueError(f"{label}只能填0或正整数")
    value = int(text)
    if value > 999_999_998:
        raise ValueError(f"{label}只能填0或正整数")
    return value


def _stored_positive(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 1 or value > 999_999_999:
        return None
    return value


def _stored_number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _stored_schedule(value, count: int | None) -> tuple[int, ...]:
    if not isinstance(value, list) or count is None or len(value) != count:
        return ()
    parsed = tuple(_stored_positive(item) for item in value)
    return tuple(item for item in parsed if item is not None) if all(parsed) else ()


def _read() -> dict:
    current = load_settings()
    return {
        "url": current.url,
        "bet_count": current.bet_count,
        "bet_points": current.bet_points,
        "bet_points_schedule": list(current.bet_points_schedule),
        "poll_interval": current.poll_interval,
        "auto_bet": current.auto_bet,
        "bet_start_offset": current.bet_start_offset,
        "profit_limit": current.profit_limit,
        "loss_limit": current.loss_limit,
        "today_profit": current.today_profit,
        "profit_date": current.profit_date,
        "profit_halt_date": current.profit_halt_date,
        "profit_halt_reason": current.profit_halt_reason,
        "profit_poll_interval": current.profit_poll_interval,
        "play_mode": current.play_mode,
        "play2_logic": current.play2_logic,
    }


def _write(data: dict) -> None:
    APP_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = SETTINGS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _restrict(temp)
    temp.replace(SETTINGS_FILE)
    _restrict(SETTINGS_FILE)
