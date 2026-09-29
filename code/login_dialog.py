"""Single-account session management, independent of the home polling surface."""
from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from account_dialogs import ImportDialog, GuideDialog
from auth_storage import clear, load, save
from settings_store import load_settings, save_url
from ui_common import hug, jwt_exp, mask, set_badge


class LoginDialog(QDialog):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self.setWindowTitle("登录管理")
        self.setMinimumWidth(660)
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
        self.refresh()
        self.url_edit.setText(load_settings().url)
        self.adjustSize()

    def set_active(self, active: bool) -> None:
        self.active = active
        for control in (self.import_btn, self.url_edit, self.url_save):
            control.setEnabled(not active)
        self.clear_btn.setEnabled(not active and load() is not None)
        self.import_btn.setToolTip("请先在首页停止轮询，再更换登录态" if active else "")

    def showEvent(self, event) -> None:
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

    def refresh(self) -> None:
        self._show_payload(load())
        self.set_active(self.active)

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

