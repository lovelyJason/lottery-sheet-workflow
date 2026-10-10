"""Single-flight automatic login shared by all background API workers."""
from __future__ import annotations

from threading import RLock

from PySide6.QtCore import QObject, Signal

from auth_storage import load, save
from auto_login import AutoLoginError, LoginClient, load_credentials
from session_errors import SessionExpiredError


class SessionManager(QObject):
    expired = Signal(str)
    restored = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None, login_factory=LoginClient):
        super().__init__(parent)
        self._lock = RLock()
        self._login_factory = login_factory

    def can_auto_relogin(self) -> bool:
        config = load_credentials()
        return config.auto_relogin and config.ready

    def ensure_valid(self, site: str, auth: dict | None, stage: str) -> dict:
        current = dict(auth or {})
        if not current:
            return self.renew(site, current, stage)
        try:
            self._login_factory(site).check(current)
            return current
        except SessionExpiredError:
            return self.renew(site, current, stage)

    def renew(self, site: str, failed_auth: dict | None, stage: str) -> dict:
        failed_auth = dict(failed_auth or {})
        with self._lock:
            latest = load()
            failed_token = str(failed_auth.get("token", ""))
            if latest and (
                    not failed_token or latest.get("token") != failed_token):
                return latest
            config = load_credentials()
            if not config.auto_relogin:
                reason = "登录状态已失效，自动续登未开启"
                self.failed.emit(reason)
                raise AutoLoginError(reason)
            if not config.ready:
                reason = "登录状态已失效，自动续登配置不完整"
                self.failed.emit(reason)
                raise AutoLoginError(reason)
            self.expired.emit(stage)
            try:
                old_uuid = str((latest or failed_auth).get("uuid", ""))
                auth = self._login_factory(site).login(config, old_uuid)
                save(auth)
            except (OSError, ValueError) as exc:
                reason = "自动续登失败：" + str(exc)
                self.failed.emit(reason)
                raise AutoLoginError(reason) from exc
            self.restored.emit(stage)
            return auth

    def login_now(self, site: str) -> dict:
        """Force a fresh credential login from the management dialog."""
        with self._lock:
            config = load_credentials()
            if not config.ready:
                reason = "自动续登配置不完整，请先保存账号密码"
                self.failed.emit(reason)
                raise AutoLoginError(reason)
            try:
                current = load() or {}
                auth = self._login_factory(site).login(
                    config, str(current.get("uuid", ""))
                )
                save(auth)
            except (OSError, ValueError) as exc:
                reason = str(exc)
                if not reason.startswith("登录失败："):
                    reason = "登录失败：" + reason
                self.failed.emit(reason)
                raise AutoLoginError(reason) from exc
            self.restored.emit("手动登录")
            return auth

