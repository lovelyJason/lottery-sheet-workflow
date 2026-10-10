"""Authenticated in-app browser backed by the Qt WebEngine Chromium runtime."""
from __future__ import annotations

import json
from urllib.parse import urlsplit, urlunsplit

from PySide6.QtCore import QThread, QUrl, Signal, Qt
from PySide6.QtGui import QAction
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar

from history_client import safe_message


GAME_PATH = "/pages/game/bingoLh"


def game_url(site: str) -> str:
    parsed = urlsplit(site.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("请先在“登录管理”保存正确的网页地址")
    return urlunsplit((parsed.scheme, parsed.netloc, GAME_PATH, "lang=zh-cn", ""))


def browser_storage_payload(auth: dict, user_info: dict) -> dict:
    token = str(auth.get("token", "")).strip()
    refresh = str(auth.get("refreshToken", "")).strip()
    device_uuid = str(auth.get("uuid", "")).strip()
    if not token or not refresh or not device_uuid:
        raise ValueError("登录态不完整，请重新登录")
    if not isinstance(user_info, dict) or not user_info:
        raise ValueError("网站未返回用户信息，请重新登录")
    if not token.startswith("Bearer "):
        token = "Bearer " + token
    return {
        "userInfo": dict(user_info),
        "userStatus": True,
        "token": token,
        "refreshToken": refresh,
        "showNotice": True,
        "uuid": device_uuid,
        "encryptStatus": False,
        "orderSiderStatus": False,
        "pwdExpired": 0,
        "loginFailTimes": 0,
    }


def storage_script(origin: str, payload: dict) -> str:
    encoded_origin = json.dumps(origin, ensure_ascii=False)
    encoded_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        "(() => { try {"
        f"if (location.origin !== {encoded_origin}) return;"
        f"localStorage.setItem('user', JSON.stringify({encoded_payload}));"
        "} catch (_) {} })();"
    )


class BrowserSessionWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, site: str, auth: dict, session, parent=None):
        super().__init__(parent)
        self.site = site
        self.auth = dict(auth)
        self.session = session

    def run(self) -> None:
        try:
            auth, user_info = self.session.prepare_browser_session(
                self.site, self.auth, "打开网站"
            )
            self.succeeded.emit({
                "url": game_url(self.site),
                "storage": browser_storage_payload(auth, user_info),
            })
        except (OSError, ValueError) as exc:
            secrets = tuple(str(value) for value in self.auth.values())
            self.failed.emit(safe_message(str(exc), secrets))
        except Exception:
            self.failed.emit("打开网站失败，请检查网页地址和登录配置")
        finally:
            self.auth = {}


class AuthenticatedBrowserWindow(QMainWindow):
    def __init__(self, url: str, storage: dict, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("黄金万两 - 已登录网页")
        self.resize(1180, 820)
        self.profile = QWebEngineProfile(QApplication.instance())
        self.profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        self.view = QWebEngineView(self)
        self.page = QWebEnginePage(self.profile, self.view)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        self._add_toolbar()
        target = QUrl(url)
        parsed = urlsplit(url)
        target_origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        script = QWebEngineScript()
        script.setName("lottery-session")
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(storage_script(target_origin, storage))
        self.profile.scripts().insert(script)
        self.view.titleChanged.connect(
            lambda title: self.setWindowTitle(title or "黄金万两 - 已登录网页")
        )
        self.view.setUrl(target)

    def _add_toolbar(self) -> None:
        toolbar = QToolBar("网页导航", self)
        toolbar.setMovable(False)
        reload_action = QAction("刷新", self)
        reload_action.triggered.connect(self.view.reload)
        toolbar.addAction(reload_action)
        self.addToolBar(toolbar)

    def closeEvent(self, event) -> None:
        self.profile.clearHttpCache()
        replacement = QWebEnginePage(self.view)
        self.view.setPage(replacement)
        self.page.deleteLater()
        self.profile.deleteLater()
        super().closeEvent(event)
