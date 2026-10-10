from __future__ import annotations

import sys
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget,
)

import app_log
from alerts import SystemAlerter
from app_icon import apply_app_icon, build_qicon, set_windows_app_user_model_id
from auth_storage import load
from config_dialogs import BetDialog, RunDialog
from debug_tools import DebugDialog, development_mode
from login_dialog import LoginDialog
from result_dialogs import HistoryDialog, LogDialog
from profit_worker import ProfitWorker
from settings_store import load_settings, save_profit_snapshot, site_day
from resource_status import ResourceStatus
from session_manager import SessionManager
from sheet_panel import SheetPanel
from theme import APP_STYLESHEET, CONFIG_BG
from toast import Toast
from ui_common import enable_terminal_interrupt, hug, set_unread
from version import APP_TITLE, APP_VERSION
from web_session import AuthenticatedBrowserWindow, BrowserSessionWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.debug_button = None
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(760, 720)
        self.setWindowIcon(build_qicon())
        self.session_manager = SessionManager(self)
        self.session_manager.expired.connect(self._session_expired)
        self.session_manager.restored.connect(self._session_restored)
        self.session_manager.failed.connect(self._session_failed)
        self.session_manager.retrying.connect(self._session_retrying)
        canvas = QWidget()
        canvas.setObjectName("canvas")
        canvas.setAttribute(Qt.WA_StyledBackground, True)
        canvas.setStyleSheet(f"QWidget#canvas {{ background: {CONFIG_BG}; }}")
        root = QVBoxLayout(canvas)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)
        self.sheet_panel = SheetPanel(self, session_manager=self.session_manager)
        self.history_panel = self.sheet_panel.history_panel
        self.alerter = SystemAlerter(self)
        self.history_panel.alert_requested.connect(self.alerter.alert)
        self.history_panel.profit_checked.connect(self._automatic_profit_succeeded)
        self.profit_worker = None
        self.browser_session_worker = None
        self.browser_window = None
        self._profit_automatic = False
        self._profit_was_halted = False
        self.profit_timer = QTimer(self)
        self.profit_timer.timeout.connect(
            lambda: self.refresh_profit(automatic=True)
        )
        root.addWidget(self.sheet_panel, 1)
        self.login_dialog = LoginDialog(self, self.session_manager)
        self.login_dialog.changed.connect(self.refresh_login_badge)
        self.login_dialog.login_idle.connect(self._close_when_idle)
        root.addWidget(self._build_entries())
        self._closing = False
        self.history_panel.idle.connect(self._close_when_idle)
        self.history_panel.state_changed.connect(self._sync_controls)
        self.setCentralWidget(canvas)
        self.toast = Toast(self)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().addWidget(ResourceStatus(self), 1)
        self.refresh_login_badge()
        self.refresh_bet_badge()
        self.refresh_run_badge()
        self._configure_profit_timer()
        self.resize(800, 720)
        if development_mode():
            self._create_debug_button()

    def _create_debug_button(self) -> None:
        self.debug_button = QPushButton("调试", self)
        self.debug_button.setObjectName("floatingDebugButton")
        self.debug_button.setToolTip("开发模式：打开运行功能调试工具")
        self.debug_button.setFixedSize(62, 38)
        self.debug_button.setStyleSheet(
            "QPushButton#floatingDebugButton {"
            "background:#E74C3C;color:white;border:none;border-radius:19px;"
            "font-weight:700;padding:0 10px;}"
            "QPushButton#floatingDebugButton:hover {background:#C0392B;}"
        )
        self.debug_button.clicked.connect(self.open_debug_dialog)
        self.debug_button.raise_()
        self._position_debug_button()

    def _position_debug_button(self) -> None:
        if self.debug_button is not None:
            margin = 18
            status_height = self.statusBar().sizeHint().height()
            self.debug_button.move(
                self.width() - self.debug_button.width() - margin,
                self.height() - self.debug_button.height() - 66 - status_height,
            )
            self.debug_button.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_debug_button()
        if hasattr(self, "toast"):
            self.toast.reposition()

    def _session_expired(self, stage: str) -> None:
        message = "登录状态已失效，正在自动续登中"
        app_log.warn(f"{message}；等待恢复步骤：{stage}")
        self.toast.show_message(message, "error", 5000)

    def _session_restored(self, stage: str) -> None:
        message = "登录成功" if stage == "手动登录" else f"登录成功，正在恢复{stage}"
        app_log.info(message)
        self.toast.show_message(message, "success", 5000)
        self.login_dialog.refresh()
        self.refresh_login_badge()

    def _session_failed(self, reason: str) -> None:
        app_log.error(reason)
        self.toast.show_message(reason, "error", 5000)

    def _session_retrying(self, reason: str, retry_index: int, maximum: int) -> None:
        app_log.warn(
            f"{reason}，正在重试第{retry_index}次（最多{maximum}次）"
        )

    def open_debug_dialog(self) -> None:
        DebugDialog(self.alerter, self).exec()

    def _build_entries(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(8)
        self.bet_btn = hug(QPushButton("投注参数"))
        self.bet_btn.clicked.connect(self.open_bet_dialog)
        self.login_btn = hug(QPushButton("登录管理"))
        self.login_btn.clicked.connect(self.open_login_dialog)
        self.run_btn = hug(QPushButton("运行配置"))
        self.run_btn.clicked.connect(self.open_run_dialog)
        history = hug(QPushButton("查看历史结果"))
        history.clicked.connect(self.open_history)
        self.open_site_btn = hug(QPushButton("打开已登录网站"), "primary")
        self.open_site_btn.clicked.connect(self.open_authenticated_site)
        logs = hug(QPushButton("查看日志"))
        logs.clicked.connect(lambda: LogDialog(self).exec())
        self.profit_label = QLabel("今日盈亏：—")
        self.profit_label.setObjectName("hint")
        self.profit_refresh = hug(QPushButton("刷新盈亏"))
        self.profit_refresh.clicked.connect(self.refresh_profit)
        layout.addWidget(self.login_btn)
        layout.addWidget(self.bet_btn)
        layout.addWidget(self.run_btn)
        layout.addWidget(self.open_site_btn)
        layout.addWidget(history)
        layout.addWidget(logs)
        layout.addStretch(1)
        layout.addWidget(self.profit_label)
        layout.addWidget(self.profit_refresh)
        return row

    def _sync_controls(self, active: bool) -> None:
        self.login_dialog.set_active(active)
        self.bet_btn.setEnabled(not active)
        self.run_btn.setEnabled(not active)
        self.profit_refresh.setEnabled(self.profit_worker is None)

    def open_login_dialog(self) -> None:
        self.login_dialog.set_active(self.history_panel.busy or self.history_panel.running)
        self.login_dialog.exec()
        self.refresh_login_badge()

    def open_history(self) -> None:
        dialog = HistoryDialog(self)
        dialog.alert_requested.connect(self.alerter.alert)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def open_authenticated_site(self) -> None:
        if self.browser_session_worker is not None:
            return
        settings, auth = load_settings(), load()
        if not settings.url:
            self._browser_open_failed("请先在“登录管理”保存网页地址")
            return
        if not auth and not self.session_manager.can_auto_relogin():
            self._browser_open_failed("请先在“登录管理”完成登录配置")
            return
        self.open_site_btn.setEnabled(False)
        self.open_site_btn.setText("正在打开…")
        worker = BrowserSessionWorker(
            settings.url, auth or {}, self.session_manager, self
        )
        self.browser_session_worker = worker
        worker.succeeded.connect(self._browser_open_ready)
        worker.failed.connect(self._browser_open_failed)
        worker.finished.connect(self._browser_open_finished)
        worker.start()

    def _browser_open_ready(self, session: dict) -> None:
        try:
            window = AuthenticatedBrowserWindow(
                session["url"], session["storage"], self
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self._browser_open_failed(str(exc))
            return
        self.browser_window = window
        window.destroyed.connect(lambda: setattr(self, "browser_window", None))
        window.show()
        window.raise_()
        window.activateWindow()
        app_log.info("已在内置浏览器中打开网站并写入当前登录态")

    def _browser_open_failed(self, reason: str) -> None:
        message = "打开网站失败：" + reason
        app_log.error(message)
        self.toast.show_message(message, "error", 5000)

    def _browser_open_finished(self) -> None:
        worker, self.browser_session_worker = self.browser_session_worker, None
        if worker is not None:
            worker.deleteLater()
        self.open_site_btn.setText("打开已登录网站")
        self.open_site_btn.setEnabled(True)
        if self._closing:
            self._close_when_idle()

    def closeEvent(self, event) -> None:
        login_busy = (
            self.login_dialog.login_worker is not None
            and self.login_dialog.login_worker.isRunning()
        )
        if (self.history_panel.busy
                or (self.profit_worker and self.profit_worker.isRunning())
                or (self.browser_session_worker
                    and self.browser_session_worker.isRunning())
                or login_busy):
            self._closing = True
            self.history_panel.stop_polling()
            event.ignore()
            return
        self.history_panel.running = False
        self.history_panel.timer.stop()
        self.profit_timer.stop()
        self.login_dialog.reject()
        if self.browser_window is not None:
            self.browser_window.close()
        super().closeEvent(event)

    def _close_when_idle(self) -> None:
        login_busy = (
            self.login_dialog.login_worker is not None
            and self.login_dialog.login_worker.isRunning()
        )
        if self._closing and not self.history_panel.busy and not (
                self.profit_worker and self.profit_worker.isRunning()) and not (
                self.browser_session_worker
                and self.browser_session_worker.isRunning()) and not login_busy:
            self.close()

    def refresh_profit(self, _checked: bool = False, automatic: bool = False) -> None:
        if self.profit_worker is not None:
            return
        settings, auth = load_settings(), load()
        if not auth and not self.session_manager.can_auto_relogin():
            self._profit_failed("请先在“登录管理”导入单账号登录态")
            return
        if not settings.url:
            self._profit_failed("请先在“登录管理”保存网页地址")
            return
        self.profit_label.setText("今日盈亏：查询中…")
        self.profit_refresh.setEnabled(False)
        self._profit_automatic = automatic
        self._profit_was_halted = settings.profit_halt_date == site_day()
        self.profit_worker = ProfitWorker(
            settings.url, auth or {}, self, session=self.session_manager
        )
        self.profit_worker.succeeded.connect(self._profit_succeeded)
        self.profit_worker.failed.connect(self._profit_failed)
        self.profit_worker.finished.connect(self._profit_finished)
        self.profit_worker.start()

    def _profit_succeeded(self, value: float) -> None:
        try:
            halted, reason = save_profit_snapshot(value)
        except (OSError, ValueError) as exc:
            self._profit_failed(str(exc))
            return
        shown = f"{value:g}"
        self._show_profit(value, halted)
        app_log.info(
            f"今日盈亏已{'自动' if self._profit_automatic else '手动'}刷新：{shown}"
        )
        if halted and not self._profit_was_halted:
            app_log.warn(reason + "，今日自动投注已停止")
            self.alerter.alert("盈亏停止投注", reason)

    def _automatic_profit_succeeded(self, value: float, halted: bool, reason: str) -> None:
        self._show_profit(value, halted)
        app_log.info(f"今日盈亏已自动检查：{value:g}")
        if halted:
            app_log.warn(reason + "，今日自动投注已停止")
            self.alerter.alert("盈亏停止投注", reason)

    def _show_profit(self, value: float, halted: bool) -> None:
        self.profit_label.setText(
            f"今日盈亏：{value:g}" + ("（已停投）" if halted else "")
        )

    def _profit_failed(self, reason: str) -> None:
        self.profit_label.setText("今日盈亏：查询失败")
        app_log.error(reason)
        self.alerter.alert("盈亏查询失败", reason)

    def _profit_finished(self) -> None:
        worker, self.profit_worker = self.profit_worker, None
        self._profit_automatic = False
        self._profit_was_halted = False
        if worker is not None:
            worker.deleteLater()
        self.profit_refresh.setEnabled(True)
        if self._closing:
            self._close_when_idle()

    def refresh_login_badge(self) -> None:
        set_unread(
            self.login_btn,
            load() is None and not self.session_manager.can_auto_relogin(),
        )

    def refresh_bet_badge(self) -> None:
        settings = load_settings()
        ready = (settings.bet_count is not None
                 and len(settings.bet_points_schedule) == settings.bet_count)
        set_unread(self.bet_btn, not ready)
        if settings.profit_date == site_day() and settings.today_profit is not None:
            suffix = "（已停投）" if settings.profit_halt_date == site_day() else ""
            self.profit_label.setText(f"今日盈亏：{settings.today_profit:g}{suffix}")

    def refresh_run_badge(self) -> None:
        settings = load_settings()
        ready = (settings.poll_interval is not None
                 and settings.profit_poll_interval is not None)
        set_unread(self.run_btn, not ready)

    def _configure_profit_timer(self) -> None:
        interval = load_settings().profit_poll_interval
        if interval and interval <= 2_147_483:
            self.profit_timer.start(interval * 1000)
        else:
            self.profit_timer.stop()

    def open_run_dialog(self) -> None:
        RunDialog(self).exec()
        self.refresh_run_badge()
        self._configure_profit_timer()
        self.history_panel._controls()

    def open_bet_dialog(self) -> None:
        BetDialog(self).exec()
        self.refresh_bet_badge()


def main() -> int:
    set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName("黄金万两")
    app.setApplicationVersion(APP_VERSION)
    app.setApplicationDisplayName(APP_TITLE)
    enable_terminal_interrupt()
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    font = QFont()
    font.setFamilies(["PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI", "Segoe UI"])
    font.setPointSize(13)
    app.setFont(font)
    apply_app_icon(app)
    window = MainWindow()
    window.show()
    apply_app_icon(app)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
