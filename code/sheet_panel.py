from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from history_panel import HistoryPanel
from sheet_book import write_template
from theme import DRAW_CONFIG_STYLE
from ui_common import hug, set_badge, unread_mark, _notice

class SheetPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("drawConfig")
        self.setStyleSheet(DRAW_CONFIG_STYLE)
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("configTabs")
        self.history_panel = HistoryPanel(self)
        self.tabs.addTab(self.history_panel, "历史补录")
        details = QWidget()
        self.tabs.addTab(details, "表格信息与模板")
        outer.addWidget(self.tabs, 1)
        root = QVBoxLayout(details)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)
        root.setAlignment(Qt.AlignTop)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.unread = unread_mark()
        title = QLabel("表格信息")
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

        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        self.box = QWidget()
        grid = QGridLayout(self.box)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        self.tail = self._value(grid, 0, "H1 尾数")
        self.zodiac = self._value(grid, 1, "I1 生肖")
        self.source = self._value(grid, 2, "来源")
        root.addWidget(self.box)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        template_btn = hug(QPushButton("下载 Excel 模板"))
        template_btn.clicked.connect(self._download)
        self.template_btn = template_btn
        actions.addWidget(template_btn)
        actions.addStretch(1)
        root.addLayout(actions)
        self.history_panel.state_changed.connect(self._sync_controls)
        self.history_panel.workbook_changed.connect(self.refresh)
        self.refresh()

    def _sync_controls(self, active: bool) -> None:
        self.template_btn.setEnabled(not active)

    def showEvent(self, event) -> None:
        self.refresh()
        self.history_panel._controls()
        super().showEvent(event)

    def _value(self, grid: QGridLayout, row: int, label: str) -> QLabel:
        caption = QLabel(label)
        caption.setObjectName("caption")
        caption.setMinimumWidth(88)
        value = QLabel("—")
        value.setObjectName("value")
        value.setTextFormat(Qt.PlainText)
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(caption, row, 0)
        grid.addWidget(value, row, 1)
        return value

    def refresh(self) -> None:
        path = self.history_panel.config.get("workbook", "")
        ready = False
        hint = "请先在“历史补录”选择 Excel，这里会自动显示同一份表格的信息。"
        if path:
            try:
                workbook = load_workbook(path, data_only=True, read_only=True)
                try:
                    sheet = workbook["记录"] if "记录" in workbook.sheetnames else workbook.worksheets[0]
                    tail, zodiac = sheet["H1"].value, sheet["I1"].value
                finally:
                    workbook.close()
                self.tail.setText(str(tail) if tail is not None else "—")
                self.zodiac.setText(str(zodiac) if zodiac is not None else "—")
                self.source.setText(Path(path).name)
                self.source.setToolTip(path)
                ready = True
                hint = "读取当前补录文件的 H1 / I1；公式无缓存时显示 —，请用 Excel 计算并保存。"
            except Exception:
                hint = "所选 Excel 暂时不可读，请检查文件或在“历史补录”重新选择。"
        self.unread.setVisible(not ready)
        set_badge(self.badge, ready, "已绑定")
        self.hint.setText(hint)
        self.box.setVisible(ready)

    def _download(self) -> None:
        downloads = Path.home() / "Downloads"
        folder = downloads if downloads.is_dir() else Path.home()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 Excel 模板",
            str(folder / "生肖投注记录模板.xlsx"),
            "Excel (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            write_template(Path(path))
        except OSError as exc:
            _notice(self, "保存失败", str(exc) or "模板没有写入", warning=True)
            return
        _notice(
            self,
            "模板已保存",
            "只需填写期数和特码。新开奖的尾数对上当前 H，或生肖对上当前 I 时，这一期的 D 列会自动变成 0。",
        )


