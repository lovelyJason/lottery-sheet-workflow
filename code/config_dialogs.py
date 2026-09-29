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
    QPushButton, QPlainTextEdit, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget,
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

class Switch(QAbstractButton):
    def __init__(self) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setChecked(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 26)
        self.toggled.connect(self.update)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1677D2") if self.isChecked() else QColor("#D5CBBA"))
        painter.drawRoundedRect(0, 3, 44, 20, 10, 10)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(24 if self.isChecked() else 2, 4, 18, 18)
        painter.end()


class BetDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("投注参数")
        self.setMinimumWidth(540)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.unread = unread_mark()
        title = QLabel("投注参数")
        title.setObjectName("heading")
        self.badge = QLabel("")
        self.badge.setObjectName("badge")
        self.badge.setProperty("state", "ready")
        self.badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.hide()
        head.addWidget(self.unread, alignment=Qt.AlignVCenter)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.badge)
        root.addLayout(head)

        self.status = QLabel(
            "D 列每次归零都会重启投注轮次；可设置跳过多少期后再连续投注。"
        )
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        form = QGridLayout()
        form.setContentsMargins(0, 4, 0, 4)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        form.setColumnStretch(1, 1)
        self.bet_delay = self._field(
            form, 0, "延后期数", allow_zero=True,
            help_text=(
                "每次 D 列出现 0，都会立即取消旧轮次剩余计划并重新计数。\n\n"
                "延后 0 期：从触发后的下一期开始。\n"
                "延后 1 期：跳过下一期，从第 2 期开始。\n"
                "例如 119 期为 0，延后 1 期、连投 3 期：投注 121–123；"
                "若 123 期再次为 0，则重新投注 125–127。"
            ),
        )
        self.bet_count = self._field(form, 1, "连续投注期数")
        points_caption = QWidget()
        points_caption_row = QHBoxLayout(points_caption)
        points_caption_row.setContentsMargins(0, 0, 0, 0)
        points_caption_row.setSpacing(6)
        points_label = QLabel("每期每注积分")
        points_label.setObjectName("caption")
        points_label.setMinimumWidth(108)
        points_help = QToolButton()
        points_help.setText("?")
        points_help.setObjectName("fieldHelp")
        points_help.setToolTip(
            "连续投注多少期，就为多少期分别设置积分。\n\n"
            "例如连投 3 期，依次填写 1、2、5：第 1 个投注期每个号码投 1 分，"
            "第 2 个投注期每个号码投 2 分，第 3 个投注期每个号码投 5 分。\n"
            "出现新的 D=0 后，积分也从第 1 期配置重新开始。"
        )
        points_help.setFixedSize(22, 22)
        points_help.setCursor(Qt.WhatsThisCursor)
        points_help.setStyleSheet(
            "QToolButton#fieldHelp {background:#E5F2FF;color:#1677D2;"
            "border:1px solid #A9D2F5;border-radius:11px;font-weight:700;}"
            "QToolButton#fieldHelp:hover {background:#1677D2;color:white;border-color:#1677D2;}"
        )
        points_caption_row.addWidget(points_label)
        points_caption_row.addWidget(points_help)
        points_caption_row.addStretch(1)
        self.points_scroll = QScrollArea()
        self.points_scroll.setObjectName("pointsScroll")
        self.points_scroll.setWidgetResizable(True)
        self.points_scroll.setFrameShape(QFrame.NoFrame)
        self.points_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.points_scroll.setMinimumWidth(292)
        self.points_scroll.setMaximumHeight(202)
        self.points_scroll.setMinimumHeight(62)
        self.points_container = QWidget()
        self.points_container.setObjectName("pointsContainer")
        self.points_container.setAttribute(Qt.WA_StyledBackground, True)
        self.points_grid = QGridLayout(self.points_container)
        self.points_grid.setContentsMargins(12, 10, 12, 10)
        self.points_grid.setHorizontalSpacing(14)
        self.points_grid.setVerticalSpacing(8)
        self.points_scroll.setWidget(self.points_container)
        self.point_edits: list[QLineEdit] = []
        form.addWidget(points_caption, 2, 0, alignment=Qt.AlignTop)
        form.addWidget(self.points_scroll, 2, 1)
        self.profit_limit = self._field(form, 3, "盈利达到停止")
        self.profit_limit.setPlaceholderText("可留空")
        self.loss_limit = self._field(form, 4, "亏损达到停止")
        self.loss_limit.setPlaceholderText("填正数，可留空")
        auto_caption = QLabel("是否自动投注")
        auto_caption.setObjectName("caption")
        auto_caption.setMinimumWidth(108)
        self.auto_bet = Switch()
        form.addWidget(auto_caption, 5, 0)
        form.addWidget(self.auto_bet, 5, 1, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        root.addLayout(form)
        self.bet_count.textChanged.connect(self._sync_point_fields)
        self.auto_bet.toggled.connect(self._sync_auto_fields)

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        root.addWidget(self.error)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        save_btn = hug(QPushButton("保存参数"), "primary")
        save_btn.clicked.connect(self._save)
        close_btn = hug(QPushButton("关闭"))
        close_btn.clicked.connect(self.accept)
        actions.addWidget(save_btn)
        actions.addStretch(1)
        actions.addWidget(close_btn)
        root.addLayout(actions)
        self._load()
        self.adjustSize()

    def _field(self, grid: QGridLayout, row: int, label: str,
               allow_zero: bool = False, help_text: str = "") -> QLineEdit:
        caption = QLabel(label)
        caption.setObjectName("caption")
        caption.setMinimumWidth(108)
        label_widget = caption
        if help_text:
            label_widget = QWidget()
            label_row = QHBoxLayout(label_widget)
            label_row.setContentsMargins(0, 0, 0, 0)
            label_row.setSpacing(6)
            help_button = QToolButton()
            help_button.setText("?")
            help_button.setObjectName("fieldHelp")
            help_button.setToolTip(help_text)
            help_button.setFixedSize(22, 22)
            help_button.setCursor(Qt.WhatsThisCursor)
            help_button.setStyleSheet(
                "QToolButton#fieldHelp {background:#E5F2FF;color:#1677D2;"
                "border:1px solid #A9D2F5;border-radius:11px;font-weight:700;}"
                "QToolButton#fieldHelp:hover {background:#1677D2;color:white;border-color:#1677D2;}"
            )
            label_row.addWidget(caption)
            label_row.addWidget(help_button)
            label_row.addStretch(1)
        edit = QLineEdit()
        edit.setPlaceholderText("0或正整数" if allow_zero else "正整数")
        edit.setFixedWidth(160)
        edit.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(QRegularExpression.anchoredPattern(
                    r"\d{1,9}" if allow_zero else r"[1-9]\d{0,8}"
                ))
            )
        )
        edit.setInputMethodHints(Qt.ImhDigitsOnly)
        grid.addWidget(label_widget, row, 0)
        grid.addWidget(edit, row, 1)
        edit._field_label_widget = label_widget
        return edit

    def _load(self) -> None:
        settings = load_settings()
        self.bet_delay.setText(str(max(0, settings.bet_start_offset - 1)))
        self.bet_count.setText("" if settings.bet_count is None else str(settings.bet_count))
        self._set_point_values(settings.bet_points_schedule)
        self.profit_limit.setText("" if settings.profit_limit is None else str(settings.profit_limit))
        self.loss_limit.setText("" if settings.loss_limit is None else str(settings.loss_limit))
        self.auto_bet.setChecked(settings.auto_bet)
        self._sync_auto_fields(settings.auto_bet)
        self._show_status(
            settings.bet_count is not None
            and len(settings.bet_points_schedule) == settings.bet_count
        )

    def _sync_auto_fields(self, enabled: bool) -> None:
        for edit in (self.profit_limit, self.loss_limit):
            edit.setVisible(enabled)
            edit._field_label_widget.setVisible(enabled)

    def _sync_point_fields(self, text: str) -> None:
        if not text.isdigit():
            return
        count = int(text)
        if count < 1 or count > 100:
            return
        current = [edit.text() for edit in self.point_edits]
        while self.points_grid.count():
            item = self.points_grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.point_edits = []
        for index in range(count):
            label = QLabel(f"第 {index + 1} 个投注期")
            label.setObjectName("caption")
            edit = QLineEdit()
            edit.setPlaceholderText("每注积分")
            edit.setFixedWidth(148)
            edit.setValidator(QRegularExpressionValidator(
                QRegularExpression(QRegularExpression.anchoredPattern(r"[1-9]\d{0,8}"))
            ))
            edit.setInputMethodHints(Qt.ImhDigitsOnly)
            if index < len(current):
                edit.setText(current[index])
            self.points_grid.addWidget(label, index, 0)
            self.points_grid.addWidget(edit, index, 1)
            self.point_edits.append(edit)
        visible_rows = min(count, 4)
        self.points_scroll.setFixedHeight(visible_rows * 44 + 20)

    def _set_point_values(self, values) -> None:
        for edit, value in zip(self.point_edits, values):
            edit.setText(str(value))

    def _show_status(self, saved: bool) -> None:
        self.unread.setVisible(not saved)
        set_badge(self.badge, saved, "已保存")
        self.error.hide()
        self.status.setText(
            "已保存：每次 D=0 都会重启轮次，并按延后期数和连续期数投注。"
            if saved else "请设置延后期数、连续期数和每注积分；盈亏停止值可以留空。"
        )
        self.status.show()

    def _save(self) -> None:
        try:
            count, points = save_bets(
                self.bet_count.text(), [edit.text() for edit in self.point_edits],
                self.auto_bet.isChecked(),
                self.bet_delay.text(), self.profit_limit.text(), self.loss_limit.text(),
            )
        except ValueError as exc:
            self.status.hide()
            self.error.setText(str(exc))
            self.error.show()
            self.unread.show()
            set_badge(self.badge, False)
            return
        self.bet_count.setText(str(count))
        self._set_point_values(points)
        self._show_status(True)


class RunDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("运行配置")
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.unread = unread_mark()
        title = QLabel("运行配置")
        title.setObjectName("heading")
        self.badge = QLabel("")
        self.badge.setObjectName("badge")
        self.badge.setProperty("state", "ready")
        self.badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.hide()
        head.addWidget(self.unread, alignment=Qt.AlignVCenter)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.badge)
        root.addLayout(head)

        self.status = QLabel("只能填正整数。")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        form = QGridLayout()
        form.setContentsMargins(0, 4, 0, 4)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        caption = QLabel("轮询时间间隔")
        caption.setObjectName("caption")
        caption.setMinimumWidth(108)
        self.interval = QLineEdit()
        self.interval.setPlaceholderText("正整数")
        self.interval.setFixedWidth(120)
        self.interval.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(QRegularExpression.anchoredPattern(r"[1-9]\d{0,8}"))
            )
        )
        self.interval.setInputMethodHints(Qt.ImhDigitsOnly)
        suffix = QLabel("秒")
        suffix.setObjectName("caption")
        field = QHBoxLayout()
        field.setContentsMargins(0, 0, 0, 0)
        field.setSpacing(8)
        field.addWidget(self.interval)
        field.addWidget(suffix)
        field.addStretch(1)
        form.addWidget(caption, 0, 0)
        form.addLayout(field, 0, 1)
        root.addLayout(form)

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        root.addWidget(self.error)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        save_btn = hug(QPushButton("保存"), "primary")
        save_btn.clicked.connect(self._save)
        close_btn = hug(QPushButton("关闭"))
        close_btn.clicked.connect(self.accept)
        actions.addWidget(save_btn)
        actions.addStretch(1)
        actions.addWidget(close_btn)
        root.addLayout(actions)
        self._load()
        self.adjustSize()

    def _load(self) -> None:
        settings = load_settings()
        self.interval.setText("" if settings.poll_interval is None else str(settings.poll_interval))
        self._show_status(settings.poll_interval is not None)

    def _show_status(self, saved: bool) -> None:
        self.unread.setVisible(not saved)
        set_badge(self.badge, saved, "已保存")
        self.error.hide()
        self.status.setText("已保存在这台电脑。" if saved else "只能填正整数。")
        self.status.show()

    def _save(self) -> None:
        try:
            interval = save_poll_interval(self.interval.text())
        except ValueError as exc:
            self.status.hide()
            self.error.setText(str(exc))
            self.error.show()
            self.unread.show()
            set_badge(self.badge, False)
            return
        self.interval.setText(str(interval))
        self._show_status(True)
