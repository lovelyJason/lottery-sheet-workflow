"""Authenticated Special Code B betting client and at-most-once issue runner."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from auth_storage import APP_DIR, _restrict
from china_time import CHINA_TIME
from history_client import BROWSER, SUCCESS_CODES, origin, safe_message

BET_STATE_FILE = APP_DIR / "bet_state.json"
ZODIACS = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")

# Lunar-year boundaries from the site's current frontend bundle.
LUNAR_NEW_YEAR = {
    2023: "2023-01-22", 2024: "2024-02-10", 2025: "2025-01-29",
    2026: "2026-02-17", 2027: "2027-02-06", 2028: "2028-01-26",
    2029: "2029-02-13", 2030: "2030-02-03", 2031: "2031-01-23",
    2032: "2032-02-11", 2033: "2033-01-31", 2034: "2034-02-19",
    2035: "2035-02-08", 2036: "2036-01-28", 2037: "2037-02-15",
    2038: "2038-02-04", 2039: "2039-01-24", 2040: "2040-02-12",
    2041: "2041-02-01", 2042: "2042-01-22", 2043: "2043-02-10",
    2044: "2044-01-30", 2045: "2045-02-17", 2046: "2046-02-06",
    2047: "2047-01-26", 2048: "2048-02-14", 2049: "2049-02-02",
    2050: "2050-01-23", 2051: "2051-02-11", 2052: "2052-02-01",
    2053: "2053-02-19",
}


class BetError(ValueError):
    pass


@dataclass(frozen=True)
class BetPlan:
    count: int
    points: int
    tail: str | None
    zodiac: str | None
    start_offset: int = 1
    point_schedule: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        schedule = self.point_schedule or (self.points,) * self.count
        if len(schedule) != self.count or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 1
                for value in schedule):
            raise BetError("每期积分配置与连续投注期数不一致")
        object.__setattr__(self, "point_schedule", tuple(schedule))

    def points_for_slot(self, slot: int) -> int:
        index = slot - self.start_offset
        if not 0 <= index < self.count:
            raise BetError("当前期不在投注窗口内")
        return self.point_schedule[index]


@dataclass(frozen=True)
class BetOutcome:
    issue: str
    selected: int
    total_points: int
    completed: int
    target_count: int
    message: str
    points: int = 0
    bets: tuple[tuple[str, int], ...] = ()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def zodiac_numbers(zodiac: str, open_time: int) -> set[int]:
    if zodiac not in ZODIACS:
        raise BetError("Excel I1 生肖无效")
    try:
        day = datetime.fromtimestamp(int(open_time), CHINA_TIME).date()
        boundary = datetime.fromisoformat(LUNAR_NEW_YEAR[day.year]).date()
    except (KeyError, OSError, OverflowError, TypeError, ValueError) as exc:
        raise BetError("开奖日期超出当前生肖映射范围，已停止自动投注") from exc
    lunar_year = day.year if day >= boundary else day.year - 1
    year_animal = (lunar_year - 2020) % 12  # 2020 was 鼠年.
    wanted = ZODIACS.index(zodiac)
    residue = (year_animal - wanted) % 12
    return {number for number in range(1, 50) if (number - 1) % 12 == residue}


def selected_numbers(plan: BetPlan, open_time: int) -> list[int]:
    excluded: set[int] = set()
    if plan.tail is not None:
        if plan.tail not in tuple(str(i) for i in range(10)):
            raise BetError("Excel H1 尾数无效")
        excluded.update(number for number in range(1, 50) if str(number).endswith(plan.tail))
    if plan.zodiac is not None:
        excluded.update(zodiac_numbers(plan.zodiac, open_time))
    if not excluded:
        raise BetError("Excel H1/I1 都为空，已停止自动投注")
    return [number for number in range(1, 50) if number not in excluded]


class BetClient:
    def __init__(self, site: str, auth: dict, opener=None):
        self.site = origin(site)
        self.auth = dict(auth)
        self.api = ""
        self.opener = opener or build_opener(NoRedirect())

    @property
    def secrets(self) -> tuple[str, ...]:
        return tuple(str(self.auth.get(key, "")) for key in ("token", "refreshToken", "uuid"))

    def _request(self, url: str, method: str = "GET", payload: dict | None = None,
                 authenticated: bool = True) -> dict:
        headers = {"Accept": "application/json", "User-Agent": BROWSER}
        if authenticated:
            token = str(self.auth.get("token", "")).strip()
            uuid = str(self.auth.get("uuid", "")).strip()
            if not token or not uuid or any(c in token + uuid for c in "\r\n"):
                raise BetError("登录态字段不完整，请重新导入")
            if not token.startswith("Bearer "):
                token = "Bearer " + token
            headers.update({
                "Authorization": token, "uuid": uuid, "Device-Type": "pc",
                "X-Requested-With": "XMLHttpRequest", "Origin": self.site,
                "Referer": self.site + "/",
            })
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        try:
            request = Request(url, data=data, headers=headers, method=method)
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise BetError("投注接口响应过大")
            body = json.loads(raw)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise BetError("登录态失效或投注接口访问受限") from None
            raise BetError(f"投注接口 HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise BetError("投注请求网络连接失败或超时；本期不自动重试") from None
        except (json.JSONDecodeError, UnicodeError):
            raise BetError("投注接口未返回有效 JSON") from None
        if not isinstance(body, dict):
            raise BetError("投注接口响应结构异常")
        return body

    def discover(self) -> str:
        body = self._request(self.site + "/domain.json", authenticated=False)
        domain = body.get("domain")
        if not isinstance(domain, str):
            raise BetError("网站 domain.json 缺少 API 地址")
        candidate = origin(domain)
        a, b = urlsplit(candidate).hostname, urlsplit(self.site).hostname
        if a != b and (len(a.split(".")) < 3 or len(b.split(".")) < 3
                       or a.split(".")[1:] != b.split(".")[1:]):
            raise BetError("API 地址与网页站点不一致，未发送登录凭据")
        self.api = candidate
        return candidate

    def _api(self, path: str, method: str = "GET", payload: dict | None = None) -> dict:
        if not self.api:
            self.discover()
        body = self._request(self.api + path, method, payload)
        if body.get("encrypt") is True:
            raise BetError("投注接口启用了加密响应")
        if body.get("code") not in SUCCESS_CODES:
            message = safe_message(body.get("msg", "请求失败"), self.secrets)
            raise BetError(message or "投注接口业务失败")
        return body

    def game_id(self) -> int:
        body = self._api("/api/v1/member/gameList")
        game = _find_game(body.get("data"), "bingoLh")
        game_id = game.get("id") if game else None
        if type(game_id) is not int or game_id < 1:
            raise BetError("gameList 中找不到宾果六合 game_id")
        return game_id

    def next_issue(self, game_id: int) -> tuple[str, int]:
        body = self._api(f"/api/v1/member/issueData/{game_id}")
        data = body.get("data")
        nxt = data.get("next") if isinstance(data, dict) else None
        issue = nxt.get("nextIssue") if isinstance(nxt, dict) else None
        open_time = nxt.get("open_time") if isinstance(nxt, dict) else None
        if not isinstance(issue, str) or not issue.isdigit():
            raise BetError("当前期号无效，已停止自动投注")
        if nxt.get("game_status") != 1 or nxt.get("status") != 1:
            raise BetError(f"{issue} 期当前不可投注")
        try:
            open_time = int(open_time)
        except (TypeError, ValueError):
            raise BetError("当前期开奖时间无效，已停止自动投注") from None
        return issue, open_time

    def build_payload(self, game_id: int, plan: BetPlan, open_time: int) -> dict:
        body = self._api(f"/api/v1/member/gameFormData/{game_id}/ht_specialCode/0/0/0")
        data = body.get("data")
        number = data.get("number") if isinstance(data, dict) else None
        special_b = number.get("specialCodeB") if isinstance(number, dict) else None
        if not isinstance(special_b, dict) or special_b.get("subType") != "guessNumberB":
            raise BetError("站点未返回特码B/specialCodeB 配置")
        if not isinstance(data, dict) or data.get("user_game_status") != 1:
            raise BetError("当前账号不可投注宾果六合")
        odds = data.get("odds")
        selected = selected_numbers(plan, open_time)
        bets = []
        for value in selected:
            price = odds.get(f"specialCodeB_guessNumberB_{value}") if isinstance(odds, dict) else None
            if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
                raise BetError(f"特码B号码 {value} 缺少有效赔率")
            bets.append({
                "amount": plan.points, "number": str(value), "odds": price,
                "group": "specialCodeB", "subGroup": "guessNumberB",
                "position": 0, "seriesType": "normal",
            })
        return {"game_id": game_id, "bet_info": bets, "odds_change": 0, "bet_type": "bet"}

    def today_profit(self) -> float:
        """Return the same live value rendered by the site's “今日结果” label."""
        game_id = self.game_id()
        body = self._api(f"/api/v1/member/issueData/{game_id}")
        data = body.get("data")
        nxt = data.get("next") if isinstance(data, dict) else None
        value = nxt.get("totalWin") if isinstance(nxt, dict) else None
        if isinstance(value, bool):
            raise BetError("issueData 缺少有效的今日盈亏 totalWin")
        try:
            result = float(value)
        except (TypeError, ValueError):
            raise BetError("issueData 缺少有效的今日盈亏 totalWin") from None
        if result != result or result in (float("inf"), float("-inf")):
            raise BetError("issueData 返回的今日盈亏无效")
        return result

    def submit(self, payload: dict) -> str:
        body = self._api("/api/v1/member/bet", "POST", payload)
        return safe_message(body.get("msg", "投注成功"), self.secrets)


class AutoBetRunner:
    def __init__(self, site: str, auth: dict, state_file: Path = BET_STATE_FILE, client=None):
        self.site = origin(site)
        self.client = client or BetClient(site, auth)
        self.state_file = Path(state_file)

    def run_once(self, plan: BetPlan, trigger_issue: str | None = None) -> BetOutcome | None:
        fingerprint = _fingerprint(self.site, plan)
        state = _read_state(self.state_file)
        if state.get("fingerprint") != fingerprint:
            state = {"fingerprint": fingerprint, "trigger_issue": None,
                     "completed": 0, "attempted": []}
        completed = state["completed"]
        active = state.get("trigger_issue") and completed < plan.count
        # Every newly observed zero is authoritative, even while an older
        # campaign is still active: discard its remaining slots and restart.
        if (trigger_issue
                and str(trigger_issue) != str(state.get("trigger_issue") or "")):
            state = {"fingerprint": fingerprint, "trigger_issue": str(trigger_issue),
                     "completed": 0, "attempted": []}
            active = True
            # Delayed campaigns must survive a restart before their first bet slot.
            _write_state(self.state_file, state)
        if not active:
            return None
        game_id = self.client.game_id()
        issue, open_time = self.client.next_issue(game_id)
        slot = issue_distance(str(state["trigger_issue"]), issue)
        if slot < plan.start_offset:
            return None
        if slot >= plan.start_offset + plan.count:
            state["completed"] = plan.count
            _write_state(self.state_file, state)
            return None
        attempted = state.setdefault("attempted", [])
        if issue in attempted:
            return None
        # Reserve before POST: a timeout/crash must not duplicate a possibly accepted order.
        attempted.append(issue)
        state["attempted"] = attempted[-500:]
        # This period is one of the N consecutive slots even if the server rejects it.
        state["completed"] = max(state["completed"], slot - plan.start_offset + 1)
        _write_state(self.state_file, state)
        points = plan.points_for_slot(slot)
        payload = self.client.build_payload(
            game_id, replace(plan, points=points), open_time
        )
        message = self.client.submit(payload)
        selected = len(payload["bet_info"])
        bets = tuple(
            (str(item["number"]), int(item["amount"]))
            for item in payload["bet_info"]
            if isinstance(item, dict) and "number" in item and "amount" in item
        )
        return BetOutcome(issue, selected, selected * points,
                          state["completed"], plan.count, message, points, bets)


def _find_game(value, key: str) -> dict | None:
    if isinstance(value, dict):
        direct = value.get(key)
        if isinstance(direct, dict) and direct.get("key") == key:
            return direct
        if value.get("key") == key:
            return value
        for child in value.values():
            found = _find_game(child, key)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_game(child, key)
            if found:
                return found
    return None


def issue_distance(trigger_issue: str, current_issue: str) -> int:
    """Issue distance for the observed 001..999 cycles (999 is followed by 001)."""
    def ordinal(value: str) -> int:
        text = str(value)
        if not text.isdigit() or len(text) < 4:
            raise BetError("网站期号格式异常，已停止自动投注")
        suffix = int(text[-3:])
        if not 1 <= suffix <= 999:
            raise BetError("网站期号尾号不在 001–999，已停止自动投注")
        return int(text[:-3]) * 999 + suffix

    distance = ordinal(current_issue) - ordinal(trigger_issue)
    if distance < 1:
        raise BetError("网站当前期号没有晚于预警期号，已停止自动投注")
    return distance


def _fingerprint(site: str, plan: BetPlan) -> str:
    raw = json.dumps({"site": site, **asdict(plan)}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _read_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    if not isinstance(value.get("attempted"), list) or type(value.get("completed")) is not int:
        return {}
    return value


def _write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    _restrict(temp)
    temp.replace(path)
    _restrict(path)
