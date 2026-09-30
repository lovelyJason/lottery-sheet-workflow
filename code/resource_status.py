"""Bottom status tiles: usage turns the bar green, amber, then red."""

from __future__ import annotations

import os

try:
    import psutil
except ImportError:
    psutil = None

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QSizePolicy, QVBoxLayout, QWidget,
)

SAFE = "#2BB673"
WARN = "#F2A826"
DANGER = "#E95151"
TRACK = "#E7E1D6"
LABEL = "#5E6876"
VALUE = "#1C2430"


def traffic_color(percent: float, *, healthy_when_high: bool) -> str:
    level = percent if healthy_when_high else 100 - percent
    if level <= 20:
        return DANGER
    if level <= 50:
        return WARN
    return SAFE


def _memory_text(num_bytes: float) -> str:
    megabytes = num_bytes / (1024 * 1024)
    if megabytes >= 1024:
        return f"{megabytes / 1024:.1f} GB"
    if megabytes >= 100:
        return f"{megabytes:.0f} MB"
    return f"{megabytes:.1f} MB"


class _Tile(QFrame):
    def __init__(self, caption: str, healthy_when_high: bool, *, bar: bool) -> None:
        super().__init__()
        self._healthy_when_high = healthy_when_high
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 2, 10, 2)
        layout.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.led = QLabel()
        self.led.setFixedSize(8, 8)
        caption_label = QLabel(caption)
        caption_label.setStyleSheet(f"color:{LABEL};font-size:11px;font-weight:700;")
        self.value = QLabel("—")
        value_font = QFont()
        value_font.setFamilies(["Menlo", "Consolas", "monospace"])
        value_font.setPointSize(10)
        value_font.setBold(True)
        self.value.setFont(value_font)
        self.value.setStyleSheet(f"color:{VALUE};")
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.led, alignment=Qt.AlignVCenter)
        top.addWidget(caption_label)
        top.addWidget(self.value)
        layout.addLayout(top)
        self.bar = None
        if bar:
            self.bar = QProgressBar()
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
            self.bar.setTextVisible(False)
            self.bar.setFixedHeight(6)
            self.bar.setMinimumWidth(148)
            layout.addWidget(self.bar)
        self._paint(SAFE)

    def _paint(self, color: str) -> None:
        self.led.setStyleSheet(
            f"background:{color};border-radius:4px;border:1px solid rgba(0,0,0,0.08);"
        )
        if self.bar is not None:
            self.bar.setStyleSheet(
                "QProgressBar {background:" + TRACK + ";border:none;border-radius:3px;}"
                "QProgressBar::chunk {background:" + color + ";border-radius:3px;}"
            )

    def show_metric(self, percent: float | None, text: str) -> None:
        if percent is None:
            self.value.setText("—")
            if self.bar is not None:
                self.bar.setValue(0)
            self._paint(LABEL)
            return
        clamped = max(0.0, min(100.0, percent))
        self.value.setText(text)
        if self.bar is not None:
            self.bar.setValue(int(round(clamped)))
        self._paint(traffic_color(clamped, healthy_when_high=self._healthy_when_high))


class ResourceStatus(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("resourceStatus")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(8)
        self.app_memory = _Tile("本程序内存", healthy_when_high=False, bar=False)
        self.free_memory = _Tile("剩余内存", healthy_when_high=True, bar=True)
        self.app_cpu = _Tile("本程序 CPU", healthy_when_high=False, bar=False)
        self.free_cpu = _Tile("剩余 CPU", healthy_when_high=True, bar=True)
        for tile in (self.app_memory, self.free_memory, self.app_cpu, self.free_cpu):
            row.addWidget(tile, alignment=Qt.AlignVCenter)
        row.addStretch(1)
        self._process = None
        if psutil is not None:
            try:
                self._process = psutil.Process(os.getpid())
                self._process.cpu_percent(interval=None)
                psutil.cpu_percent(interval=None)
            except Exception:
                self._process = None
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        QTimer.singleShot(400, self.refresh)

    def refresh(self) -> None:
        if psutil is None or self._process is None:
            return
        try:
            memory = psutil.virtual_memory()
            rss = self._process.memory_info().rss
            used = 0.0 if memory.total <= 0 else rss / memory.total * 100
            self.app_memory.show_metric(used, _memory_text(rss))
            free = 0.0 if memory.total <= 0 else memory.available / memory.total * 100
            self.free_memory.show_metric(free, _memory_text(memory.available))
        except Exception:
            self.app_memory.show_metric(None, "—")
            self.free_memory.show_metric(None, "—")
        try:
            app_cpu = self._process.cpu_percent(interval=None)
            self.app_cpu.show_metric(app_cpu, f"{app_cpu:.1f}%")
        except Exception:
            self.app_cpu.show_metric(None, "—")
        try:
            free_cpu = max(0.0, 100.0 - psutil.cpu_percent(interval=None))
            self.free_cpu.show_metric(free_cpu, f"{free_cpu:.0f}%")
        except Exception:
            self.free_cpu.show_metric(None, "—")
