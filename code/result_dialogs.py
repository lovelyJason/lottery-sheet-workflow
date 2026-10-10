from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Signal, Qt, QRegularExpression, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRegularExpressionValidator, QTextCursor
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QPlainTextEdit, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from app_log import document_html, subscribe
from app_icon import ICON_JPG as ICON_PATH
from app_icon import apply_app_icon, build_qicon, set_windows_app_user_model_id
from auth_storage import clear, load, save, validate_payload
from settings_store import load_settings, save_bets, save_poll_interval, save_url
from sheet_book import import_targets, load_targets, save_targets, write_template
from theme import APP_STYLESHEET



from datetime import date

import app_log
from auth_storage import load
from balls import HOT, ball_pixmap, draw_day, is_hot, number_zodiac, parse_numbers
from history_worker import ResultFetchWorker
from settings_store import load_settings

PAGE_SIZE = 15
from shiboken6 import isValid
from ui_common import *
from ui_common import _notice


def _format_time(value) -> str:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OverflowError, OSError):
            return "时间格式异常"
    return "" if value is None else str(value)


def _worker_alive(worker) -> bool:
    try:
        return worker is not None and isValid(worker)
    except RuntimeError:
        return False


class _WorkerHold(QObject):
    """Keep a QThread alive until it has finished. Dropping the last Python
    reference deletes the C++ thread immediately, even if deleteLater is queued."""

    def __init__(self, worker) -> None:
        super().__init__()
        self.worker = worker
        self._done = False
        if worker.isFinished():
            QTimer.singleShot(0, self._finished)
        else:
            worker.finished.connect(self._finished, Qt.QueuedConnection)

    def _finished(self) -> None:
        if self._done:
            return
        self._done = True
        worker = self.worker
        try:
            worker.wait()
        except RuntimeError:
            self._drop()
            return
        try:
            worker.destroyed.connect(self._drop)
        except RuntimeError:
            self._drop()
            return
        if _worker_alive(worker):
            worker.deleteLater()
        else:
            self._drop()

    def _drop(self, *_args) -> None:
        try:
            _LIVE_WORKERS.remove(self)
        except ValueError:
            pass
        self.worker = None
        self.deleteLater()


_LIVE_WORKERS: list[_WorkerHold] = []


def _park(worker) -> None:
    if not _worker_alive(worker):
        return
    if any(hold.worker is worker for hold in _LIVE_WORKERS):
        return
    _LIVE_WORKERS.append(_WorkerHold(worker))


class TableSpinner(QWidget):
    """Indeterminate arc drawn over the table while a fetch is in flight."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start(self) -> None:
        self._angle = 0
        self.setGeometry(self.parentWidget().rect())
        self._timer.start()
        self.show()
        self.raise_()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255, 210))
        box = QRect(0, 0, 36, 36)
        box.moveCenter(self.rect().center())
        painter.setPen(QPen(QColor("#E4DCCE"), 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(box, 0, 360 * 16)
        painter.setPen(QPen(QColor("#1677D2"), 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(box, int(-self._angle * 16), 100 * 16)


class ResultDelegate(QStyledItemDelegate):
    def __init__(self, host: HistoryDialog) -> None:
        super().__init__(host)
        self.host = host

    def paint(self, painter, option, index) -> None:
        kind = index.data(Qt.UserRole)
        if kind not in ("balls", "tone", "more"):
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if kind == "balls":
            self._balls(painter, option.rect, index.data(Qt.UserRole + 1) or [])
        elif kind == "tone":
            self._tone(painter, option.rect, index.data(Qt.DisplayRole), bool(index.data(Qt.UserRole + 1)))
        else:
            self._more(painter, option.rect)
        painter.restore()

    def _balls(self, painter: QPainter, rect, pairs: list) -> None:
        ball = 24
        zodiac_w = 16
        gap = 6
        step = ball + zodiac_w + gap
        if not pairs:
            return
        total = step * len(pairs) - gap
        x = rect.x() + max(6, (rect.width() - total) / 2)
        y = rect.y() + (rect.height() - ball) / 2
        font = QFont("PingFang SC", 12)
        painter.setFont(font)
        painter.setPen(QColor("#2C2C2C"))
        for number, animal in pairs:
            painter.drawPixmap(QRect(int(x), int(y), ball, ball), ball_pixmap(number))
            painter.drawText(
                QRect(int(x + ball), rect.y(), zodiac_w, rect.height()),
                Qt.AlignCenter,
                animal,
            )
            x += step

    def _tone(self, painter: QPainter, rect, text, hot: bool) -> None:
        font = QFont("PingFang SC", 13)
        font.setBold(hot)
        painter.setFont(font)
        painter.setPen(QColor(HOT if hot else "#2C2C2C"))
        painter.drawText(rect, Qt.AlignCenter, "" if text is None else str(text))

    def _more(self, painter: QPainter, rect) -> None:
        painter.fillRect(rect, QColor("#FAFAFB"))
        loading = self.host._loading and bool(self.host._rows)
        text = self.host._more_error or ("正在加载" if loading else "加载更多")
        font = QFont("PingFang SC", 13)
        painter.setFont(font)
        painter.setPen(QColor("#C04545" if self.host._more_error else "#8E96A3"))
        if loading and not self.host._more_error:
            box = QRect(0, 0, 14, 14)
            box.moveCenter(rect.center())
            box.moveLeft(rect.center().x() - 48)
            painter.setPen(QPen(QColor("#D5D8DE"), 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(box, 0, 360 * 16)
            painter.setPen(QPen(QColor("#1677D2"), 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(box, int(-self.host._more_angle * 16), 110 * 16)
            painter.setPen(QColor("#8E96A3"))
        painter.drawText(rect, Qt.AlignCenter, text)


class HistoryDialog(QDialog):
    alert_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("历史结果")
        self.resize(1180, 680)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("历史结果")
        title.setObjectName("heading")
        root.addWidget(title)

        table = QTableWidget(2, 11)
        self.table = table
        self.empty = QLabel("")
        self.empty.setObjectName("hint")
        self.empty.setWordWrap(True)
        self.empty.hide()
        root.addWidget(self.empty)
        self.spinner = TableSpinner(table)
        table.installEventFilter(self)
        self._fetch = None
        self._closed = False
        self._in_done = False
        self._close_code = 0
        self._started = False
        self._loading = False
        self._rows: list[dict] = []
        self._page = 0
        self._has_more = True
        self._seen: set[tuple] = set()
        self._hold = False
        self._more_error = ""
        self._more_angle = 0
        self._adjusting = False
        self._more_timer = QTimer(self)
        self._more_timer.setInterval(40)
        self._more_timer.timeout.connect(self._tick_more)
        table.setItemDelegate(ResultDelegate(self))
        table.horizontalHeader().hide()
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setShowGrid(True)
        table.setWordWrap(False)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setStyleSheet(
            "QTableWidget { background:#FFFFFF; border:1px solid #E4E1E8; border-radius:8px;"
            "gridline-color:#E6E2EA; color:#2C2C2C; font-size:13px; }"
            "QTableWidget::item { padding:0px; }"
        )
        table.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._header(table, 0, 0, "期数", 2, 1)
        self._header(table, 0, 1, "开奖时间", 2, 1)
        self._header(table, 0, 2, "开奖号码", 2, 1)
        self._header(table, 0, 3, "特码", 1, 5)
        self._header(table, 0, 8, "总和", 1, 3)
        for column, text in enumerate(("特码", "单双", "大小", "生肖量", "尾数量"), start=3):
            self._header(table, 1, column, text)
        for column, text in enumerate(("总分", "单双", "大小"), start=8):
            self._header(table, 1, column, text)
        table.setRowHeight(0, 40)
        table.setRowHeight(1, 36)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        table.setColumnWidth(2, 460)
        for column, width in (
            (0, 108), (1, 168), (3, 96), (4, 56), (5, 56),
            (6, 72), (7, 72), (8, 64), (9, 56), (10, 56),
        ):
            table.setColumnWidth(column, width)
        root.addWidget(table, 1)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._started:
            self._started = True
            self._rows = []
            self._page = 0
            self._has_more = True
            self._seen = set()
            self._load_page(1)

    def _load_page(self, page: int) -> None:
        if self._closed or self._loading or not self._has_more or self._hold or page < 1 or page > 50:
            return
        settings, auth = load_settings(), load()
        if not settings.url:
            self.empty.setText("请先在主界面保存网页地址。")
            self.empty.show()
            self._has_more = False
            return
        session = getattr(self.parent(), "session_manager", None)
        if not auth and not (session and session.can_auto_relogin()):
            self.empty.setText("请先导入登录态。")
            self.empty.show()
            self._has_more = False
            return
        self._loading = True
        self._more_error = ""
        if page == 1 and not self._rows:
            self._start_loading()
        else:
            self._rebuild()
            self._more_timer.start()
        worker = ResultFetchWorker(
            settings.url, auth or {}, date.today().isoformat(), page,
            session=session,
        )
        worker.succeeded.connect(self._loaded)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._release_fetch)
        self._fetch = worker
        worker.start()

    def _loaded(self, payload: dict) -> None:
        if self._closed:
            return
        self._stop_loading()
        self._more_timer.stop()
        self._loading = False
        rows = payload.get("rows") or []
        page = payload.get("page", 0)
        if not rows:
            self._has_more = False
        else:
            signature = tuple(row.get("issue") for row in rows)
            if signature in self._seen:
                self._has_more = False
            else:
                self._seen.add(signature)
                self._rows.extend(rows)
                self._page = page
                if len(rows) < PAGE_SIZE or page >= 50:
                    self._has_more = False
        self._rebuild()
        if not self._rows:
            self.empty.setText("今天还没有开奖结果。")
            self.empty.show()
        else:
            self.empty.hide()
        app_log.info(f"历史结果第 {page} 页：{len(rows)} 条")
        QTimer.singleShot(0, self._fill_if_short)

    def _failed(self, text: str) -> None:
        if self._closed:
            return
        self._stop_loading()
        self._more_timer.stop()
        self._loading = False
        app_log.error(text)
        self.alert_requested.emit("历史结果查询失败", text)
        if self._rows:
            self._more_error = text
            self._hold = True
            self._rebuild()
            return
        self.empty.setText(text)
        self.empty.show()

    def _on_scroll(self, value: int) -> None:
        if self._adjusting:
            return
        bar = self.table.verticalScrollBar()
        if value < bar.maximum() - 80:
            self._hold = False
            self._more_error = ""
        if bar.maximum() > 0 and value >= bar.maximum() - 24:
            self._load_page(self._page + 1)

    def _fill_if_short(self) -> None:
        if self._closed:
            return
        bar = self.table.verticalScrollBar()
        if self._has_more and not self._hold and bar.maximum() <= 8:
            self._load_page(self._page + 1)

    def _tick_more(self) -> None:
        self._more_angle = (self._more_angle + 24) % 360
        row = 2 + len(self._rows)
        if row < self.table.rowCount():
            self.table.viewport().update(self.table.visualRect(self.table.model().index(row, 0)))

    def _start_loading(self) -> None:
        self.empty.hide()
        self.spinner.start()

    def _stop_loading(self) -> None:
        self.spinner.stop()
        self._more_timer.stop()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.table and event.type() == QEvent.Resize and self.spinner.isVisible():
            self.spinner.setGeometry(self.table.rect())
        return super().eventFilter(watched, event)

    def _release_fetch(self) -> None:
        worker = self._fetch
        self._fetch = None
        _park(worker)

    def _detach_fetch(self) -> None:
        worker = self._fetch
        self._fetch = None
        if not _worker_alive(worker):
            return
        try:
            worker.cancel.set()
            for signal, slot in (
                (worker.succeeded, self._loaded),
                (worker.failed, self._failed),
                (worker.finished, self._release_fetch),
            ):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        except RuntimeError:
            return
        _park(worker)

    def done(self, code: int) -> None:
        if self._in_done:
            return
        self._closed = True
        self._has_more = False
        self._detach_fetch()
        self._stop_loading()
        self._in_done = True
        try:
            super().done(code)
        finally:
            self._in_done = False

    def set_results(self, rows: list[dict]) -> None:
        if rows:
            self.empty.hide()
        self._rows = list(rows)
        self._has_more = False
        self._more_error = ""
        self._rebuild()

    def _rebuild(self) -> None:
        bar = self.table.verticalScrollBar()
        previous = bar.value()
        extra = 1 if self._has_more or self._more_error else 0
        self._adjusting = True
        self.table.clearSpans()
        self.table.setRowCount(2 + len(self._rows) + extra)
        self.table.setSpan(0, 0, 2, 1)
        self.table.setSpan(0, 1, 2, 1)
        self.table.setSpan(0, 2, 2, 1)
        self.table.setSpan(0, 3, 1, 5)
        self.table.setSpan(0, 8, 1, 3)
        try:
            for offset, record in enumerate(self._rows):
                self._fill_row(2 + offset, record)
            if extra:
                self._fill_more(2 + len(self._rows))
        finally:
            self._adjusting = False
            bar.setValue(min(previous, bar.maximum()))

    def _fill_row(self, row: int, record: dict) -> None:
        day = draw_day(record)
        self.table.setRowHeight(row, 48)
        self._text(row, 0, record.get("issue", ""))
        self._text(row, 1, _format_time(record.get("open_time")))
        numbers = QTableWidgetItem()
        numbers.setData(Qt.UserRole, "balls")
        numbers.setData(
            Qt.UserRole + 1,
            [(number, number_zodiac(number, day)) for number in parse_numbers(record.get("numbers"))],
        )
        self.table.setItem(row, 2, numbers)
        special = record.get("special_code")
        spec = QTableWidgetItem()
        spec.setData(Qt.UserRole, "balls")
        if isinstance(special, int) and 1 <= special <= 49:
            spec.setData(Qt.UserRole + 1, [(special, number_zodiac(special, day))])
        self.table.setItem(row, 3, spec)
        for column, key in ((4, "special_code_ds"), (5, "special_code_dx"), (9, "totalDs"), (10, "totalDx")):
            text = "" if record.get(key) is None else str(record.get(key))
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            item.setData(Qt.UserRole, "tone")
            item.setData(Qt.UserRole + 1, is_hot(text))
            self.table.setItem(row, column, item)
        for column, key in ((6, "zodiacNum"), (7, "tailNum"), (8, "total")):
            self._text(row, column, record.get(key, ""))

    def _fill_more(self, row: int) -> None:
        self.table.setRowHeight(row, 44)
        item = QTableWidgetItem(self._more_error or "加载更多")
        item.setData(Qt.UserRole, "more")
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 0, item)
        self.table.setSpan(row, 0, 1, 11)

    def _text(self, row: int, column: int, value) -> None:
        item = QTableWidgetItem("" if value is None else str(value))
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, column, item)

    def _header(self, table: QTableWidget, row: int, column: int, text: str, row_span: int = 1, column_span: int = 1) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(Qt.ItemIsEnabled)
        item.setBackground(QColor("#F3F1F4"))
        item.setForeground(QColor("#3C3C3C"))
        table.setItem(row, column, item)
        if row_span > 1 or column_span > 1:
            table.setSpan(row, column, row_span, column_span)


class LogDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("运行日志")
        self.resize(900, 560)
        self.setMinimumSize(720, 420)
        self.setStyleSheet(
            "QDialog { background:#101722; }"
            "QTextEdit#console {"
            "background:#101722; color:#E8EDF4; border:none;"
            "padding:0; margin:0; font-family:Menlo, Consolas, monospace; font-size:13px;"
            "}"
            "QTextEdit#console QScrollBar:vertical { background:#101722; width:10px; margin:0; }"
            "QTextEdit#console QScrollBar::handle:vertical { background:#3A4A62; border-radius:5px; min-height:28px; }"
            "QTextEdit#console QScrollBar::add-line:vertical, QTextEdit#console QScrollBar::sub-line:vertical { height:0; }"
            "QTextEdit#console QScrollBar::add-page:vertical, QTextEdit#console QScrollBar::sub-page:vertical { background:#101722; }"
            "QWidget#logActions { background: transparent; }"
            "QPushButton#logLink {"
            "background: transparent; border: none; border-radius: 0;"
            "color: #8E9AAB; padding: 0 2px; margin: 0;"
            "font-size: 13px; font-weight: 400; min-height: 0;"
            "}"
            "QPushButton#logLink:hover { color: #E8EDF4; background: transparent; }"
            "QPushButton#logLink:pressed { color: #FFFFFF; background: transparent; }"
            "QPushButton#logLink:focus { border: none; background: transparent; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.view = QTextEdit()
        self.view.setObjectName("console")
        self.view.setReadOnly(True)
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.setAcceptDrops(False)
        self.view.setContextMenuPolicy(Qt.NoContextMenu)
        self.view.document().setDocumentMargin(14)
        self.view.installEventFilter(self)
        self.view.viewport().installEventFilter(self)
        self.view.cursorPositionChanged.connect(self._stick_cursor)
        self._placing = False
        self._placing_actions = False
        root.addWidget(self.view, 1)
        self.actions = QWidget(self)
        self.actions.setObjectName("logActions")
        self.actions.setAutoFillBackground(False)
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(16)
        open_button = hug(QPushButton("打开日志"))
        clear_button = hug(QPushButton("清除日志"))
        for button in (open_button, clear_button):
            button.setObjectName("logLink")
            button.setFlat(True)
            button.setMinimumHeight(0)
            button.setFocusPolicy(Qt.NoFocus)
        open_button.clicked.connect(self._open_log)
        clear_button.clicked.connect(self._clear_log)
        actions.addWidget(open_button)
        actions.addWidget(clear_button)
        self._cancel = subscribe(self._on_line)
        self._render()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._place_actions()
        self.view.setFocus(Qt.OtherFocusReason)
        self._stick_cursor()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_actions()

    def _place_actions(self) -> None:
        if self._placing_actions:
            return
        self._placing_actions = True
        try:
            self.actions.adjustSize()
            inset = 14
            self.actions.move(
                max(0, self.width() - self.actions.width() - inset),
                max(0, self.height() - self.actions.height() - inset),
            )
            self.actions.raise_()
            self.view.setViewportMargins(0, 0, 0, self.actions.height() + inset)
        finally:
            self._placing_actions = False

    def _open_log(self) -> None:
        try:
            app_log.open_in_editor()
        except OSError as exc:
            _notice(self, "打开失败", f"无法用文本编辑器打开日志：{exc}", warning=True)

    def eventFilter(self, watched, event) -> bool:
        if watched in (self.view, self.view.viewport()) and event.type() in (
            QEvent.KeyPress,
            QEvent.KeyRelease,
            QEvent.InputMethod,
            QEvent.ShortcutOverride,
            QEvent.MouseButtonPress,
            QEvent.MouseButtonDblClick,
            QEvent.MouseButtonRelease,
        ):
            self._stick_cursor()
            return True
        return super().eventFilter(watched, event)

    def _render(self) -> None:
        self._placing = True
        self.view.setHtml(document_html())
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        self.view.setTextCursor(cursor)
        self._placing = False
        self.view.setFocus(Qt.OtherFocusReason)

    def _stick_cursor(self) -> None:
        if self._placing:
            return
        end = QTextCursor(self.view.document())
        end.movePosition(QTextCursor.End)
        if self.view.textCursor().position() == end.position():
            return
        self._placing = True
        self.view.setTextCursor(end)
        self._placing = False

    def _on_line(self, _level: str, _message: str) -> None:
        self._render()

    def _clear_log(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("清除运行日志")
        box.setText("确定清除全部运行日志吗？")
        box.setInformativeText("当前日志和轮转备份都会删除，此操作不可撤销。")
        cancel = hug(box.addButton("取消", QMessageBox.RejectRole))
        confirm = hug(box.addButton("清除", QMessageBox.DestructiveRole), "danger")
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        if box.clickedButton() is not confirm:
            return
        try:
            app_log.clear()
        except OSError as exc:
            _notice(self, "清除失败", f"日志文件删除失败：{exc}", warning=True)

    def done(self, code: int) -> None:
        self._cancel()
        super().done(code)
