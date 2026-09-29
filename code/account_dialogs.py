from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, QRegularExpression
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap, QRegularExpressionValidator, QTextCursor
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QPlainTextEdit, QSizePolicy, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from app_log import document_html, subscribe
from app_icon import ICON_JPG as ICON_PATH
from app_icon import apply_app_icon, build_qicon, set_windows_app_user_model_id
from auth_storage import clear, load, save, validate_payload
from settings_store import load_settings, save_bets, save_poll_interval, save_url
from sheet_book import import_targets, load_targets, save_targets, write_template
from theme import APP_STYLESHEET



from ui_common import *
from ui_common import _notice

class ImportDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导入单账号登录态")
        self.setMinimumWidth(520)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)
        title = QLabel("导入登录态")
        title.setObjectName("heading")
        root.addWidget(title)
        tip = QLabel("粘贴完整的 Local Storage → user JSON，或包含 token、refreshToken、uuid 的 JSON。\n登录态仅保存到本机，不会上传；不要粘贴密码。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        root.addWidget(tip)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('{"token":"Bearer ...","refreshToken":"...","uuid":"..."}')
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setMinimumHeight(180)
        root.addWidget(self.editor, 1)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = buttons.button(QDialogButtonBox.Ok)
        cancel = buttons.button(QDialogButtonBox.Cancel)
        ok.setText("导入")
        cancel.setText("取消")
        hug(ok, "primary")
        hug(cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons, alignment=Qt.AlignRight)
        self.adjustSize()
        self.payload: dict[str, Any] | None = None

    def _accept(self) -> None:
        try:
            self.payload = validate_payload(self.editor.toPlainText())
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class GuideDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("如何获取登录态")
        self.setMinimumWidth(480)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)
        title = QLabel("如何获取登录态")
        title.setObjectName("heading")
        root.addWidget(title)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        text = QLabel(
            "<b>Chrome 获取步骤</b><ol>"
            "<li>在“登录管理”中保存网页地址，用 Chrome 打开并确认已经登录。</li>"
            "<li>按 F12，打开 <b>Application</b>（应用）面板。</li>"
            "<li>左侧进入 <b>Storage → Local Storage</b>，选择目标网站域名。</li>"
            "<li>找到键名 <b>user</b>，复制右侧 Value 的完整 JSON。</li>"
            "<li>回到本程序点击「导入登录态」，粘贴并确认。</li>"
            "</ol><b>注意</b><br>"
            "不要复制密码，不要把 token 发到聊天或截图中。登录态失效后重新复制 user 值导入即可。<br>"
            "当前网站主要使用 Local Storage，不是 Cookie。"
        )
        text.setObjectName("hint")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_layout.addWidget(text)
        root.addWidget(card)
        close = hug(QPushButton("关闭"), "primary")
        close.clicked.connect(self.accept)
        root.addWidget(close, alignment=Qt.AlignRight)
        self.adjustSize()


