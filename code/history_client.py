"""Read-only historical results API. No transaction endpoints are implemented."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class HistoryError(ValueError):
    pass


def origin(raw: str) -> str:
    try:
        p = urlsplit(raw.strip())
        port = p.port
    except ValueError as exc:
        raise HistoryError("网页地址格式错误") from exc
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise HistoryError("请使用不带用户名或密码的 HTTPS 网页地址")
    if port not in (None, 443):
        raise HistoryError("网页地址须使用 HTTPS 默认端口")
    return f"https://{p.hostname}"


def results_url(site: str) -> str:
    return origin(site) + "/pages/users/openResult"


def safe_message(value: object, secrets: tuple[str, ...] = ()) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[已隐藏]")
    text = re.sub(r"(?:Bearer\s+)?eyJ[A-Za-z0-9_.-]+", "[已隐藏]", text)
    return text.replace("\r", " ").replace("\n", " ")[:240]


BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
SUCCESS_CODES = {200, 40000}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HistoryClient:
    def __init__(self, site: str, auth: dict, opener=None):
        self.site = origin(site)
        self.auth = auth
        self.api = ""
        self.opener = opener or build_opener(NoRedirect())

    def _get(self, url: str, headers: dict | None = None) -> dict:
        try:
            request_headers = {
                "Accept": "application/json",
                "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/151.0.0.0 Safari/537.36"),
            }
            request_headers.update(headers or {})
            req = Request(url, headers=request_headers, method="GET")
            with self.opener.open(req, timeout=12) as response:
                data = response.read(2_000_001)
                if len(data) > 2_000_000:
                    raise HistoryError("响应过大，本轮已停止")
                body = json.loads(data)
        except HTTPError as exc:
            if exc.code in (401, 403):
                if not headers:
                    raise HistoryError("网站配置入口访问受限，请检查网页地址与网络") from None
                raise HistoryError("登录态失效或访问受限，请重新导入登录态") from None
            raise HistoryError(f"历史查询 HTTP {exc.code}，本轮未保存") from None
        except (URLError, TimeoutError, OSError):
            raise HistoryError("网络连接失败或超时，请检查地址与网络") from None
        except (ValueError, UnicodeError) as exc:
            if isinstance(exc, HistoryError):
                raise
            raise HistoryError("服务器未返回有效 JSON") from None
        if not isinstance(body, dict):
            raise HistoryError("服务器响应结构不符合约定")
        return body

    def discover(self) -> str:
        """Current site's observed /domain.json exposes the separate API domain."""
        domain = self._get(self.site + "/domain.json").get("domain")
        if not isinstance(domain, str):
            raise HistoryError("网站 domain.json 缺少 domain，未发送登录凭据")
        candidate = origin(domain)
        a, b = urlsplit(candidate).hostname, urlsplit(self.site).hostname
        if a != b and (len(a.split(".")) < 3 or len(b.split(".")) < 3
                       or a.split(".")[1:] != b.split(".")[1:]):
            raise HistoryError("API 地址与网页站点不一致，未发送登录凭据")
        self.api = candidate
        return candidate

    def fetch_page(self, day: str, page: int) -> list[dict]:
        """User supplied GET /api/v1/member/openResultList; data.data records."""
        date.fromisoformat(day)
        if type(page) is not int or page < 1:
            raise HistoryError("分页页码必须为正整数")
        if not self.api:
            self.discover()
        token = self.auth.get("token", "").strip()
        uuid = self.auth.get("uuid", "").strip()
        if not token or not uuid or any(c in token + uuid for c in "\r\n"):
            raise HistoryError("登录态字段不完整，请重新导入")
        if not token.startswith("Bearer "):
            token = "Bearer " + token
        query = urlencode({"gameKey": "bingoLh", "date": day, "page": page})
        body = self._get(self.api + "/api/v1/member/openResultList?" + query, {
            "Accept": "application/json", "Authorization": token, "uuid": uuid,
            "Device-Type": "pc", "X-Requested-With": "XMLHttpRequest",
            "Origin": self.site, "Referer": self.site + "/",
        })
        if body.get("encrypt") is True:
            raise HistoryError("当前接口启用了加密响应，本轮未写入 Excel")
        if body.get("code") not in SUCCESS_CODES:
            msg = safe_message(body.get("msg", "查询失败"), (
                token, token.removeprefix("Bearer "), uuid,
                self.auth.get("refreshToken", ""),
            ))
            raise HistoryError(f"历史查询失败：{msg}")
        data = body.get("data")
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise HistoryError("历史结果缺少 data.data 数组")
        for row in rows:
            if not isinstance(row, dict):
                raise HistoryError("历史结果行格式异常")
            issue, code = row.get("issue"), row.get("special_code")
            if not isinstance(issue, str) or not re.fullmatch(r"[0-9]{4,20}", issue):
                raise HistoryError("历史结果期号格式异常")
            if type(code) is not int or not 1 <= code <= 49:
                raise HistoryError("历史结果特码应为 1–49 的整数")
        return rows

    def fetch_day(self, day: str, limit: int = 50, cancel=None) -> list[dict]:
        """Page size is fixed at 15 and each call takes seconds, so later pages go out together."""
        if _cancelled(cancel):
            return []
        first = self.fetch_page(day, 1)
        if not first:
            return []
        rows = list(first)
        seen = {tuple(row["issue"] for row in first)}
        page_size = len(first)
        page = 2
        while page <= limit:
            if _cancelled(cancel):
                return rows
            batch = list(range(page, min(page + 8, limit + 1)))
            fetched_pages = self._fetch_pages(day, batch)
            for number in batch:
                fetched = fetched_pages[number]
                if not fetched or len(fetched) < page_size:
                    if fetched:
                        signature = tuple(row["issue"] for row in fetched)
                        if signature in seen:
                            raise HistoryError("接口重复返回同一页，已停止继续翻页")
                        rows.extend(fetched)
                    return rows
                signature = tuple(row["issue"] for row in fetched)
                if signature in seen:
                    raise HistoryError("接口重复返回同一页，已停止继续翻页")
                seen.add(signature)
                rows.extend(fetched)
            page += len(batch)
        return rows

    def _fetch_pages(self, day: str, pages: list[int]) -> dict[int, list[dict]]:
        def one(page: int) -> tuple[int, list[dict]]:
            client = HistoryClient(self.site, self.auth)
            client.api = self.api
            return page, client.fetch_page(day, page)

        with ThreadPoolExecutor(max_workers=min(8, len(pages))) as pool:
            return dict(pool.map(one, pages))


def _cancelled(cancel) -> bool:
    return cancel is not None and cancel.is_set()
