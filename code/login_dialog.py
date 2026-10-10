"""Single-account session management, independent of the home polling surface."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from account_dialogs import ImportDialog, GuideDialog
from auth_storage import clear, load, save
from auto_login import (
    LoginCredentials, clear_credentials, load_credentials, save_credentials,
)
from config_dialogs import Switch
from session_manager import SessionManager
from settings_store import load_settings, save_url
from ui_common import hug, jwt_exp, mask, set_badge


ASSET_DIR = Path(__file__).resolve().parent / "assets"
EYE_ICON = ASSET_DIR / "password-eye.svg"
EYE_OFF_ICON = ASSET_DIR / "password-eye-off.svg"
TTSHITU_USER_URL = "http://www.ttshitu.com/user/index.html"


class LoginNowWorker(QThread):
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, manager: SessionManager, site: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.site = site

    def run(self) -> None:
        try:
            self.manager.login_now(self.site)
            self.succeeded.emit()
        except (OSError, ValueError) as exc:
            self.failed.emit(str(exc))


class LoginDialog(QDialog):
    changed = Signal()
    login_idle = Signal()

    def __init__(self, parent=None, session_manager: SessionManager | None = None):
        super().__init__(parent)
        self.active = False
        self.login_worker = None
        self.session_manager = session_manager or SessionManager(self)
        self.setWindowTitle("登录管理")
        self.setMinimumWidth(720)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)
        title = QLabel("登录管理")
        title.setObjectName("heading")
        root.addWidget(title)
        root.addWidget(self._build_card())
        close = hug(QPushButton("关闭"))
        close.clicked.connect(self.accept)
        root.addWidget(close, alignment=Qt.AlignRight)
        self._load_credential_fields()
        self.refresh()
        self.url_edit.setText(load_settings().url)
        self.adjustSize()

    def set_active(self, active: bool) -> None:
        self.active = active
        enabled = not active and self.login_worker is None
        for control in (
            self.import_btn, self.url_edit, self.url_save,
            self.site_username, self.site_password,
            self.captcha_username, self.captcha_password,
            self.auto_relogin, self.login_retry_count, self.credentials_save,
            self.credentials_clear, self.login_now,
        ):
            control.setEnabled(enabled)
        self.clear_btn.setEnabled(not active and load() is not None)
        self.credentials_clear.setEnabled(
            enabled and load_credentials().ready
        )
        self.import_btn.setToolTip("请先在首页停止轮询，再更换登录态" if active else "")

    def showEvent(self, event) -> None:
        self._load_credential_fields()
        self.refresh()
        self.url_edit.setText(load_settings().url)
        self.set_active(self.active)
        super().showEvent(event)

    def _build_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        head = QHBoxLayout()
        self.badge = QLabel("")
        self.badge.setObjectName("badge")
        self.badge.setProperty("state", "empty")
        self.badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.badge.setAlignment(Qt.AlignCenter)
        head.addWidget(self.badge)
        self.auto_badge = QLabel("")
        self.auto_badge.setObjectName("badge")
        self.auto_badge.setProperty("state", "ready")
        self.auto_badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.auto_badge.setAlignment(Qt.AlignCenter)
        head.addWidget(self.auto_badge)
        head.addStretch(1)
        layout.addLayout(head)

        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        self.field_box = QWidget()
        grid = QGridLayout(self.field_box)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        self.values: dict[str, QLabel] = {}
        for row, (key, label) in enumerate((
            ("token", "token"),
            ("refreshToken", "refreshToken"),
            ("uuid", "uuid"),
            ("exp", "过期时间"),
        )):
            caption = QLabel(label)
            caption.setObjectName("caption")
            caption.setMinimumWidth(108)
            value = QLabel("—")
            value.setObjectName("value")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(caption, row, 0)
            grid.addWidget(value, row, 1)
            self.values[key] = value
        layout.addWidget(self.field_box)

        url_row = QHBoxLayout()
        url_row.setSpacing(10)
        url_caption = QLabel("网页地址")
        url_caption.setObjectName("caption")
        url_caption.setMinimumWidth(108)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://")
        self.url_edit.setClearButtonEnabled(True)
        self.url_save = hug(QPushButton("保存地址"))
        self.url_save.clicked.connect(self.save_site_url)
        url_row.addWidget(url_caption)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.url_save)
        layout.addLayout(url_row)

        self.url_status = QLabel("地址会变，和登录态分开保存。")
        self.url_status.setObjectName("hint")
        self.url_status.setWordWrap(True)
        layout.addWidget(self.url_status)
        self.url_error = QLabel("")
        self.url_error.setObjectName("error")
        self.url_error.setWordWrap(True)
        self.url_error.hide()
        layout.addWidget(self.url_error)

        credential_rule = QWidget()
        credential_rule.setObjectName("rule")
        credential_rule.setFixedHeight(1)
        credential_rule.setAttribute(Qt.WA_StyledBackground, True)
        layout.addWidget(credential_rule)

        credentials_title = QLabel("自动续登配置")
        credentials_title.setObjectName("sectionLabel")
        layout.addWidget(credentials_title)
        credential_box = QWidget()
        credential_grid = QGridLayout(credential_box)
        credential_grid.setContentsMargins(0, 0, 0, 0)
        credential_grid.setHorizontalSpacing(12)
        credential_grid.setVerticalSpacing(10)
        credential_grid.setColumnStretch(1, 1)
        credential_grid.setColumnStretch(3, 1)
        self.site_username = self._credential_input(
            credential_grid, 0, 0, "网站账号", "请输入网站账号"
        )
        self.site_password = self._credential_input(
            credential_grid, 0, 2, "网站密码", "请输入网站密码", True
        )
        self.captcha_username = self._credential_input(
            credential_grid, 1, 0, "打码账号", "ttshitu 平台账号"
        )
        self.captcha_password = self._credential_input(
            credential_grid, 1, 2, "打码密码", "请输入打码平台密码", True
        )
        layout.addWidget(credential_box)

        auto_row = QHBoxLayout()
        auto_label = QLabel("开启自动续登")
        auto_label.setObjectName("autoLoginTitle")
        self.auto_relogin = Switch()
        self.auto_relogin.setChecked(True)
        self.auto_relogin.setToolTip("默认开启；登录失效后自动打码、登录并恢复中断步骤")
        auto_row.addWidget(auto_label)
        auto_row.addWidget(self.auto_relogin)
        auto_row.addSpacing(22)
        retry_label = QLabel("登录失败重试次数")
        retry_label.setObjectName("autoLoginTitle")
        self.login_retry_count = QSpinBox()
        self.login_retry_count.setRange(1, 100)
        self.login_retry_count.setValue(10)
        self.login_retry_count.setSuffix(" 次")
        self.login_retry_count.setToolTip("首次登录失败后的最大重试次数")
        auto_row.addWidget(retry_label)
        auto_row.addWidget(self.login_retry_count)
        auto_row.addStretch(1)
        layout.addLayout(auto_row)
        auto_note = QLabel(
            "默认开启。启动任务及运行过程中若登录失效，程序会自动识别验证码、"
            "重新登录，并从失败的补录、查询或投注步骤继续。"
            "单次失败会按配置继续重试，耗尽次数后才停止任务。"
        )
        auto_note.setObjectName("hint")
        auto_note.setWordWrap(True)
        layout.addWidget(auto_note)
        self.credentials_error = QLabel("")
        self.credentials_error.setObjectName("error")
        self.credentials_error.setWordWrap(True)
        self.credentials_error.hide()
        layout.addWidget(self.credentials_error)

        credential_actions = QHBoxLayout()
        credential_actions.setSpacing(10)
        self.credentials_save = hug(QPushButton("保存账号配置"))
        self.credentials_save.clicked.connect(self.save_login_credentials)
        self.open_captcha_site = hug(QPushButton("打开打码网站"))
        self.open_captcha_site.setToolTip("在默认浏览器中打开 ttshitu 用户中心")
        self.open_captcha_site.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(TTSHITU_USER_URL))
        )
        self.login_now = hug(QPushButton("立即登录"), "primary")
        self.login_now.clicked.connect(self.start_login)
        self.credentials_clear = hug(QPushButton("清除账号配置"), "danger")
        self.credentials_clear.clicked.connect(self.clear_login_credentials)
        credential_actions.addWidget(self.credentials_save)
        credential_actions.addWidget(self.open_captcha_site)
        credential_actions.addWidget(self.login_now)
        credential_actions.addStretch(1)
        credential_actions.addWidget(self.credentials_clear)
        layout.addLayout(credential_actions)

        rule = QWidget()
        rule.setObjectName("rule")
        rule.setFixedHeight(1)
        rule.setAttribute(Qt.WA_StyledBackground, True)
        layout.addWidget(rule)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.import_btn = hug(QPushButton("导入登录态"), "primary")
        self.import_btn.clicked.connect(self.import_auth)
        self.guide_btn = hug(QPushButton("如何获取登录态"))
        self.guide_btn.clicked.connect(lambda: GuideDialog(self).exec())
        self.clear_btn = hug(QPushButton("清除本机登录态"), "danger")
        self.clear_btn.clicked.connect(self.clear_auth)
        actions.addWidget(self.import_btn)
        actions.addWidget(self.guide_btn)
        actions.addStretch(1)
        actions.addWidget(self.clear_btn)
        layout.addLayout(actions)
        return card

    @staticmethod
    def _credential_input(grid: QGridLayout, row: int, column: int,
                          label: str, placeholder: str,
                          password: bool = False) -> QLineEdit:
        caption = QLabel(label)
        caption.setObjectName("caption")
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setClearButtonEnabled(not password)
        if password:
            field.setEchoMode(QLineEdit.Password)
            toggle = field.addAction(QIcon(str(EYE_ICON)), QLineEdit.TrailingPosition)
            toggle.setToolTip("显示密码")

            def toggle_password(_checked=False, edit=field, action=toggle):
                visible = edit.echoMode() == QLineEdit.Password
                edit.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
                edit.setProperty("passwordVisible", visible)
                action.setIcon(QIcon(str(EYE_OFF_ICON if visible else EYE_ICON)))
                action.setToolTip("隐藏密码" if visible else "显示密码")

            toggle.triggered.connect(toggle_password)
        grid.addWidget(caption, row, column)
        grid.addWidget(field, row, column + 1)
        return field

    def refresh(self) -> None:
        self._show_payload(load())
        config = load_credentials()
        set_badge(self.auto_badge, config.ready, "自动续登已配置")
        self.credentials_clear.setEnabled(not self.active and config.ready)
        self.set_active(self.active)

    def _load_credential_fields(self) -> None:
        config = load_credentials()
        self.site_username.setText(config.site_username)
        self.captcha_username.setText(config.captcha_username)
        self.site_password.setText(config.site_password)
        self.captcha_password.setText(config.captcha_password)
        self.auto_relogin.setChecked(config.auto_relogin)
        self.login_retry_count.setValue(config.login_retry_count)

    def _show_payload(self, payload: dict[str, Any] | None) -> None:
        ready = payload is not None
        set_badge(self.badge, ready, "已导入")
        if not ready:
            self.hint.setText("还没有登录态。在浏览器的 Local Storage 里复制 user JSON，再导入。")
            self.field_box.hide()
            self.clear_btn.setEnabled(False)
            return
        self.hint.setText("已保存 1 个账号。下面只显示脱敏片段，完整内容留在本机文件里。")
        self.values["token"].setText(mask(payload["token"]))
        self.values["refreshToken"].setText(mask(payload["refreshToken"]))
        self.values["uuid"].setText(mask(payload["uuid"]))
        self.values["exp"].setText(jwt_exp(payload["token"]))
        self.field_box.show()
        self.clear_btn.setEnabled(True)
        if self.isVisible():
            hint_h = self.sizeHint().height()
            if self.height() < hint_h:
                self.resize(max(self.width(), 600), hint_h)

    def _show_url_status(self, saved: bool) -> None:
        self.url_error.hide()
        self.url_status.setText("地址已保存在这台电脑。" if saved else "地址会变，和登录态分开保存。")
        self.url_status.show()

    def save_site_url(self) -> None:
        if self.active:
            return
        try:
            self.url_edit.setText(save_url(self.url_edit.text()))
        except ValueError as exc:
            self.url_status.hide()
            self.url_error.setText(str(exc))
            self.url_error.show()
            return
        self._show_url_status(saved=True)
        self.changed.emit()

    def save_login_credentials(self) -> bool:
        if self.active:
            return False
        config = LoginCredentials(
            site_username=self.site_username.text().strip(),
            site_password=self.site_password.text(),
            captcha_username=self.captcha_username.text().strip(),
            captcha_password=self.captcha_password.text(),
            auto_relogin=self.auto_relogin.isChecked(),
            login_retry_count=self.login_retry_count.value(),
        )
        try:
            save_credentials(config)
        except (OSError, ValueError) as exc:
            self.credentials_error.setText(str(exc))
            self.credentials_error.show()
            return False
        self.credentials_error.hide()
        self._load_credential_fields()
        self.refresh()
        self.changed.emit()
        return True

    def start_login(self) -> None:
        if self.active or self.login_worker is not None:
            return
        if not self.save_login_credentials():
            return
        try:
            site = save_url(self.url_edit.text())
        except ValueError as exc:
            self.url_status.hide()
            self.url_error.setText(str(exc))
            self.url_error.show()
            return
        self.url_edit.setText(site)
        self._show_url_status(saved=True)
        self.login_now.setText("登录中…")
        self._set_login_controls(False)
        worker = LoginNowWorker(self.session_manager, site, self)
        self.login_worker = worker
        worker.succeeded.connect(self._login_succeeded)
        worker.failed.connect(self._login_failed)
        worker.finished.connect(self._login_finished)
        worker.start()

    def _login_succeeded(self) -> None:
        self.credentials_error.hide()
        self.refresh()
        self.changed.emit()

    def _login_failed(self, reason: str) -> None:
        self.credentials_error.setText(reason)
        self.credentials_error.show()

    def _login_finished(self) -> None:
        worker, self.login_worker = self.login_worker, None
        if worker is not None:
            worker.deleteLater()
        self.login_now.setText("立即登录")
        self._set_login_controls(not self.active)
        self.login_idle.emit()

    def _set_login_controls(self, enabled: bool) -> None:
        for control in (
            self.site_username, self.site_password,
            self.captcha_username, self.captcha_password,
            self.auto_relogin, self.login_retry_count, self.credentials_save,
            self.credentials_clear, self.login_now,
        ):
            control.setEnabled(enabled)

    def clear_login_credentials(self) -> None:
        if self.active:
            return
        clear_credentials()
        self._load_credential_fields()
        self.refresh()
        self.changed.emit()

    def import_auth(self) -> None:
        if self.active:
            return
        dialog = ImportDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.payload:
            save(dialog.payload)
            self.refresh()
            self.changed.emit()
            QMessageBox.information(self, "导入成功", "登录态已保存到本机。")

    def clear_auth(self) -> None:
        if self.active:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("确认清除")
        box.setText("确定删除本机保存的登录态吗？")
        yes = box.addButton("清除", QMessageBox.YesRole)
        no = box.addButton("取消", QMessageBox.NoRole)
        hug(yes, "danger")
        hug(no)
        box.setDefaultButton(no)
        box.exec()
        if box.clickedButton() is yes:
            clear()
            self.refresh()
            self.changed.emit()

