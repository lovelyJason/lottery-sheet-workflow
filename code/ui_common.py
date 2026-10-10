from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, QRegularExpression, QTimer
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


def mask(value: str) -> str:
    if len(value) <= 12:
        return "*" * len(value)
    return value[:6] + "…" + value[-6:]


def jwt_exp(token: str) -> str:
    try:
        raw = token.removeprefix("Bearer ").split(".")[1]
        pad = "=" * (-len(raw) % 4)
        import base64
        claims = json.loads(base64.urlsafe_b64decode(raw + pad))
        exp = claims.get("exp")
        if isinstance(exp, (int, float)):
            return datetime.fromtimestamp(exp, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, IndexError, KeyError, TypeError, json.JSONDecodeError):
        pass
    return "未解析"


def _notice(parent: QWidget, title: str, text: str, warning: bool = False) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning if warning else QMessageBox.Information)
    box.setWindowTitle(title)
    box.setText(text)
    hug(box.addButton("确定", QMessageBox.AcceptRole))
    box.exec()


def enable_terminal_interrupt() -> None:
    """Let Ctrl+C use the window's stop-and-wait path during Excel writes."""
    app = QApplication.instance()
    def close_windows(_signum, _frame):
        for window in app.topLevelWidgets():
            if isinstance(window, QMainWindow):
                window.close()
    signal.signal(signal.SIGINT, close_windows)
    timer = QTimer(app)
    timer.timeout.connect(lambda: None)
    timer.start(200)
    app._interrupt_timer = timer


def polish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def set_badge(label: QLabel, ready: bool, text: str = "") -> None:
    label.setProperty("state", "ready" if ready else "empty")
    if ready:
        label.setText(text)
        label.setMinimumSize(0, 0)
        label.setMaximumSize(16777215, 16777215)
        label.show()
    else:
        label.hide()
    polish(label)
    if ready:
        # Fusion can briefly collapse a padded QLabel to the layout's bare
        # content height after a dynamic-property repolish.  Keep the status
        # pill tall enough for both its text and background to be visible.
        label.setMinimumHeight(24)
        label.adjustSize()


def unread_icon() -> QIcon:
    logical = 8
    scale = 2
    pixmap = QPixmap(logical * scale, logical * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#A7ADB6"))
    painter.drawEllipse(0, 0, logical, logical)
    painter.end()
    return QIcon(pixmap)


def set_unread(button: QPushButton, pending: bool) -> None:
    if pending:
        button.setIcon(unread_icon())
        button.setIconSize(QSize(8, 8))
        return
    button.setIcon(QIcon())


def unread_mark() -> QLabel:
    mark = QLabel("")
    mark.setPixmap(unread_icon().pixmap(QSize(8, 8)))
    mark.setFixedSize(8, 8)
    return mark


def hug(button: QPushButton, role: str | None = None) -> QPushButton:
    button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    button.setCursor(Qt.PointingHandCursor)
    if role:
        button.setProperty("role", role)
        polish(button)
    return button


def rounded_pixmap(size: int, radius: int = 16) -> QPixmap | None:
    if not ICON_PATH.is_file():
        return None
    screen = QApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen is not None else 1.0
    source = QPixmap(str(ICON_PATH))
    if source.isNull():
        return None
    side = max(1, int(round(size * dpr)))
    scaled = source.scaled(side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (scaled.width() - side) // 2)
    y = max(0, (scaled.height() - side) // 2)
    scaled = scaled.copy(x, y, side, side)
    result = QPixmap(side, side)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing, True)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, side, side, radius * dpr, radius * dpr)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    result.setDevicePixelRatio(dpr)
    return result

