"""Credential storage, image-captcha recognition and the site's login protocol."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from uuid import uuid4

from auth_storage import APP_DIR, _restrict
from history_client import BROWSER, NoRedirect, origin, safe_message
from session_errors import AUTH_EXPIRED_CODES, SessionExpiredError


CREDENTIALS_FILE = APP_DIR / "login_credentials.json"
TTSHITU_ENDPOINT = "https://api.ttshitu.com/predict"
MAX_RESPONSE_BYTES = 2_000_000


class AutoLoginError(ValueError):
    """A secret-free, user-facing automatic-login error."""


@dataclass(frozen=True)
class LoginCredentials:
    site_username: str = ""
    site_password: str = ""
    captcha_username: str = ""
    captcha_password: str = ""
    auto_relogin: bool = True

    @property
    def ready(self) -> bool:
        return all((
            self.site_username.strip(), self.site_password,
            self.captcha_username.strip(), self.captcha_password,
        ))


def load_credentials(path: Path = CREDENTIALS_FILE) -> LoginCredentials:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LoginCredentials()
    if not isinstance(raw, dict):
        return LoginCredentials()
    return LoginCredentials(
        site_username=_text(raw.get("site_username")),
        site_password=_text(raw.get("site_password")),
        captcha_username=_text(raw.get("captcha_username")),
        captcha_password=_text(raw.get("captcha_password")),
        auto_relogin=raw.get("auto_relogin") is not False,
    )


def save_credentials(credentials: LoginCredentials,
                     path: Path = CREDENTIALS_FILE) -> None:
    if not credentials.site_username.strip():
        raise AutoLoginError("请填写网站账号")
    if not credentials.site_password:
        raise AutoLoginError("请填写网站密码")
    if not credentials.captcha_username.strip():
        raise AutoLoginError("请填写打码平台账号")
    if not credentials.captcha_password:
        raise AutoLoginError("请填写打码平台密码")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(asdict(credentials), ensure_ascii=False), encoding="utf-8"
    )
    _restrict(temp)
    temp.replace(path)
    _restrict(path)


def clear_credentials(path: Path = CREDENTIALS_FILE) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


class TtshituSolver:
    """ttshitu JSON API, using numeric type 1 for the site's four-digit image."""

    def __init__(self, opener=None, endpoint: str = TTSHITU_ENDPOINT):
        self.opener = opener or build_opener(NoRedirect())
        self.endpoint = endpoint

    def solve(self, image: str, credentials: LoginCredentials) -> str:
        encoded = _base64_payload(image)
        body = self._post({
            "username": credentials.captcha_username.strip(),
            "password": credentials.captcha_password,
            "typeid": "1",
            "image": encoded,
        })
        if body.get("success") is not True:
            raise AutoLoginError(
                "验证码识别失败：" + safe_message(
                    body.get("message", "打码平台请求失败"),
                    (credentials.captcha_username, credentials.captcha_password,
                     credentials.site_username, credentials.site_password),
                )
            )
        data = body.get("data")
        result = data.get("result") if isinstance(data, dict) else None
        result = str(result or "").strip()
        if not re.fullmatch(r"[0-9]{4}", result):
            raise AutoLoginError("打码平台返回的验证码不是4位数字")
        return result

    def _post(self, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.endpoint, data=data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json;charset=UTF-8",
                "User-Agent": BROWSER,
            }, method="POST",
        )
        return _open_json(self.opener, request, 60, "打码平台")


class LoginClient:
    """Observed getVerifyCode -> captcha -> member/login sequence."""

    def __init__(self, site: str, opener=None, solver=None):
        self.site = origin(site)
        self.api = ""
        self.opener = opener or build_opener(NoRedirect())
        self.solver = solver or TtshituSolver()

    def discover(self) -> str:
        body = self._request(self.site + "/domain.json", authenticated=False)
        domain = body.get("domain")
        if not isinstance(domain, str):
            raise AutoLoginError("网站 domain.json 缺少 API 地址")
        candidate = origin(domain)
        from urllib.parse import urlsplit
        a, b = urlsplit(candidate).hostname, urlsplit(self.site).hostname
        if a != b and (len(a.split(".")) < 3 or len(b.split(".")) < 3
                       or a.split(".")[1:] != b.split(".")[1:]):
            raise AutoLoginError("API 地址与网页站点不一致，未发送账号密码")
        self.api = candidate
        return candidate

    def check(self, auth: dict) -> None:
        if not self.api:
            self.discover()
        body = self._request(
            self.api + "/api/v1/member/getUserInfo", auth=auth,
            authenticated=True,
        )
        self._require_success(body, "登录状态检查失败", auth_check=True)

    def login(self, credentials: LoginCredentials, device_uuid: str = "") -> dict:
        if not credentials.ready:
            raise AutoLoginError("自动续登配置不完整，请填写网站和打码平台账号密码")
        if not self.api:
            self.discover()
        device_uuid = _valid_uuid(device_uuid) or uuid4().hex
        captcha = self._request(
            self.api + "/api/v1/common/getVerifyCode",
            auth={"uuid": device_uuid}, authenticated=False,
        )
        self._require_success(captcha, "获取验证码失败")
        data = captcha.get("data")
        if not isinstance(data, dict):
            raise AutoLoginError("验证码接口缺少 data")
        key, image = data.get("key"), data.get("base64")
        if not isinstance(key, str) or not key or not isinstance(image, str):
            raise AutoLoginError("验证码接口缺少图片或 key")
        code = self.solver.solve(image, credentials)
        payload = {
            "username": credentials.site_username.strip(),
            "password": credentials.site_password,
            "code": code,
            "key": key,
            "lang": "en",
            "uuid": device_uuid,
            "cf-turnstile-response": "",
        }
        body = self._request(
            self.api + "/api/v1/member/login", method="POST",
            payload=payload, auth={"uuid": device_uuid}, authenticated=False,
        )
        self._require_success(body, "登录失败", (
            credentials.site_username, credentials.site_password,
            credentials.captcha_username, credentials.captcha_password,
        ))
        result = body.get("data")
        jwt = result.get("jwtInfo") if isinstance(result, dict) else None
        token = jwt.get("token") if isinstance(jwt, dict) else None
        refresh = jwt.get("refreshToken") if isinstance(jwt, dict) else None
        if not isinstance(token, str) or len(token.strip()) < 40:
            raise AutoLoginError("登录成功响应缺少 token")
        if not isinstance(refresh, str) or len(refresh.strip()) < 40:
            raise AutoLoginError("登录成功响应缺少 refreshToken")
        return {
            "token": token.strip(),
            "refreshToken": refresh.strip(),
            "uuid": device_uuid,
        }

    def _request(self, url: str, method: str = "GET", payload: dict | None = None,
                 auth: dict | None = None, authenticated: bool = False) -> dict:
        auth = auth or {}
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Device-Type": "pc", "Origin": self.site,
            "Referer": self.site + "/", "User-Agent": BROWSER,
            "X-Requested-With": "XMLHttpRequest",
        }
        device_uuid = str(auth.get("uuid", "")).strip()
        if device_uuid:
            headers["uuid"] = device_uuid
        if authenticated:
            token = str(auth.get("token", "")).strip()
            if not token or not device_uuid:
                raise SessionExpiredError("登录状态不存在或已失效")
            headers["Authorization"] = token if token.startswith("Bearer ") else "Bearer " + token
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            return _open_json(self.opener, request, 15, "网站登录")
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise SessionExpiredError("登录状态已失效") from None
            raise

    @staticmethod
    def _require_success(body: dict, prefix: str,
                         secrets: tuple[str, ...] = (),
                         auth_check: bool = False) -> None:
        code = body.get("code")
        if auth_check and code in AUTH_EXPIRED_CODES:
            raise SessionExpiredError(
                safe_message(body.get("msg", "登录状态已失效"), secrets)
            )
        if code not in (200, 40000):
            reason = safe_message(body.get("msg", prefix), secrets)
            raise AutoLoginError(f"{prefix}：{reason}")
        if body.get("encrypt") is True:
            raise AutoLoginError(prefix + "：接口返回了加密数据")


def _open_json(opener, request: Request, timeout: int, label: str) -> dict:
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError:
        raise
    except (URLError, TimeoutError, OSError) as exc:
        raise AutoLoginError(label + "网络连接失败或超时") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise AutoLoginError(label + "响应过大")
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise AutoLoginError(label + "未返回有效 JSON") from exc
    if not isinstance(body, dict):
        raise AutoLoginError(label + "响应结构异常")
    return body


def _base64_payload(value: str) -> str:
    text = value.strip()
    if "," in text and text.lower().startswith("data:image/"):
        text = text.split(",", 1)[1]
    if not text or len(text) > 4_500_000:
        raise AutoLoginError("验证码图片为空或过大")
    if not re.fullmatch(r"[A-Za-z0-9+/=\r\n]+", text):
        raise AutoLoginError("验证码图片不是有效 Base64")
    return text.replace("\r", "").replace("\n", "")


def _valid_uuid(value: object) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"[A-Za-z0-9-]{8,80}", text) else ""


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""

