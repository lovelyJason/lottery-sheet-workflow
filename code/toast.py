"""Small Ant Design-style top message used for session recovery feedback."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel
from PySide6.QtGui import QColor


class Toast(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(9)
        self.icon = QLabel("!")
        self.icon.setObjectName("toastIcon")
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(20, 20)
        self.text = QLabel("")
        self.text.setObjectName("toastText")
        layout.addWidget(self.icon)
        layout.addWidget(self.text)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(20, 38, 60, 70))
        self.setGraphicsEffect(shadow)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, message: str, kind: str = "error",
                     duration_ms: int = 5000) -> None:
        self.setProperty("kind", kind)
        self.icon.setText("✓" if kind == "success" else "!")
        self.text.setText(message)
        self.style().unpolish(self)
        self.style().polish(self)
        for child in (self.icon, self.text):
            child.style().unpolish(child)
            child.style().polish(child)
        self.adjustSize()
        self.reposition()
        self.raise_()
        self.show()
        self.timer.start(duration_ms)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(max(16, (parent.width() - self.width()) // 2), 24)

