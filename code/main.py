from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget,
)

from auth_storage import clear, load, save, validate_payload


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


class ImportDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导入单账号登录态")
        self.resize(620, 390)
        root = QVBoxLayout(self)
        tip = QLabel("粘贴完整的 Local Storage → user JSON，或包含 token、refreshToken、uuid 的 JSON。\n登录态仅保存到本机，不会上传；不要粘贴密码。")
        tip.setWordWrap(True)
        root.addWidget(tip)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('{"token":"Bearer ...","refreshToken":"...","uuid":"..."}')
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        root.addWidget(self.editor)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#b42318;")
        root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
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
        self.resize(620, 420)
        root = QVBoxLayout(self)
        text = QLabel("""<b>Chrome 获取步骤</b><br>
1. 在 Chrome 打开目标网站并确认已经登录。<br>
2. 按 F12，打开 <b>Application</b>（应用）面板。<br>
3. 左侧进入 <b>Storage → Local Storage</b>，选择目标网站域名。<br>
4. 找到键名 <b>user</b>，复制右侧 Value 的完整 JSON。<br>
5. 回到本程序点击“导入登录态”，粘贴并确认。<br><br>
<b>注意</b><br>
不要复制密码，不要把 token 发到聊天或截图中。登录态失效后重新复制 user 值导入即可。<br>
当前网站主要使用 Local Storage，不是 Cookie。""")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(text)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        root.addWidget(close, alignment=Qt.AlignRight)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("开奖数据工作台")
        self.resize(700, 430)
        root = QVBoxLayout()
        title = QLabel("单账号登录态")
        title.setStyleSheet("font-size:20px;font-weight:600;")
        root.addWidget(title)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.detail = QLineEdit()
        self.detail.setReadOnly(True)
        root.addWidget(self.detail)
        import_btn = QPushButton("导入登录态")
        import_btn.clicked.connect(self.import_auth)
        root.addWidget(import_btn)
        guide_btn = QPushButton("如何获取登录态")
        guide_btn.clicked.connect(lambda: GuideDialog(self).exec())
        root.addWidget(guide_btn)
        clear_btn = QPushButton("清除本机登录态")
        clear_btn.clicked.connect(self.clear_auth)
        root.addWidget(clear_btn)
        root.addStretch()
        box = QWidget(); box.setLayout(root); self.setCentralWidget(box)
        self.refresh()

    def refresh(self) -> None:
        payload = load()
        if not payload:
            self.status.setText("状态：未导入登录态")
            self.detail.clear()
            return
        self.status.setText("状态：已导入单个账号登录态")
        self.detail.setText(f"token: {mask(payload['token'])}    refreshToken: {mask(payload['refreshToken'])}    uuid: {mask(payload['uuid'])}    token 过期时间: {jwt_exp(payload['token'])}")

    def import_auth(self) -> None:
        dialog = ImportDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.payload:
            save(dialog.payload)
            self.refresh()
            QMessageBox.information(self, "导入成功", "登录态已保存到本机。")

    def clear_auth(self) -> None:
        if QMessageBox.question(self, "确认清除", "确定删除本机保存的登录态吗？") == QMessageBox.Yes:
            clear(); self.refresh()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow(); window.show()
    sys.exit(app.exec())
