"""Developer-only floating diagnostics. Never shown in normal production mode."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ui_common import hug


DEV_ENV = "LOTTERY_DEV_MODE"


def development_mode() -> bool:
    value = os.environ.get(DEV_ENV, "").strip().lower()
    if value:
        return value in {"1", "true", "yes", "on"}
    if "--dev" in sys.argv[1:]:
        return True
    # Running main.py from source is the normal developer workflow. Packaged
    # executables (PyInstaller/etc.) stay production-only unless explicitly enabled.
    return not getattr(sys, "frozen", False) and Path(sys.argv[0]).name == "main.py"


class DebugDialog(QDialog):
    def __init__(self, alerter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.alerter = alerter
        self.setWindowTitle("开发调试")
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel("告警功能调试")
        title.setObjectName("heading")
        root.addWidget(title)
        hint = QLabel("点击后会播放与正式异常相同的提示音，并弹出包含下方原因的系统通知。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.reason = QLineEdit("这是开发模式告警测试：网络连接失败或登录态已过期")
        self.reason.setPlaceholderText("输入测试错误原因")
        root.addWidget(self.reason)

        actions = QHBoxLayout()
        alarm = hug(QPushButton("测试警报声"), "primary")
        alarm.clicked.connect(self.alerter.alarm)
        notification = hug(QPushButton("测试系统通知"))
        notification.clicked.connect(self.test_notification)
        test = hug(QPushButton("全部测试"))
        test.clicked.connect(self.test_alert)
        stop = hug(QPushButton("停止警报"))
        stop.clicked.connect(self.alerter.stop_alarm)
        close = hug(QPushButton("关闭"))
        close.clicked.connect(self.accept)
        actions.addWidget(alarm)
        actions.addWidget(notification)
        actions.addWidget(test)
        actions.addWidget(stop)
        actions.addStretch(1)
        actions.addWidget(close)
        root.addLayout(actions)

    def test_alert(self) -> None:
        reason = self.reason.text().strip() or "开发模式测试异常"
        self.alerter.alert("开发模式告警测试", reason)

    def test_notification(self) -> None:
        reason = self.reason.text().strip() or "开发模式测试异常"
        self.alerter.notify("开发模式通知测试", reason)
