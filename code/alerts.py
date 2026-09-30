"""Visible and audible runtime alarms for macOS and Windows."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from app_icon import build_qicon


class SystemAlerter(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.alarm_file = Path(__file__).resolve().parent / "assets" / "alarm.wav"
        self._sound_process = None
        self.tray = QSystemTrayIcon(build_qicon(), self)
        self.tray.setToolTip("黄金万两运行告警")
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        if parent is not None:
            parent.destroyed.connect(self.stop_alarm)

    def alert(self, title: str, reason: str) -> None:
        text = str(reason).strip() or "未知异常"
        self.alarm()
        self.notify(title, text)

    def notify(self, title: str, reason: str) -> None:
        text = str(reason).strip() or "未知异常"
        if sys.platform == "darwin":
            script = (
                f'display notification "{self._apple_text(text)}" '
                f'with title "{self._apple_text(str(title))}"'
            )
            try:
                subprocess.run(
                    ["/usr/bin/osascript", "-e", script],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=2, check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
            return
        if self.tray.isVisible():
            self.tray.showMessage(str(title), text, QSystemTrayIcon.Warning, 15_000)

    def alarm(self) -> None:
        """Play the configured alert clip, pre-rendered as three repetitions."""
        self.stop_alarm()
        if self.alarm_file.is_file() and sys.platform == "darwin":
            try:
                self._sound_process = subprocess.Popen(
                    ["/usr/bin/afplay", str(self.alarm_file)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                QTimer.singleShot(13_000, self._reap_alarm)
                return
            except OSError:
                pass
        if sys.platform == "win32":
            try:
                import winsound
                if self.alarm_file.is_file():
                    winsound.PlaySound(
                        str(self.alarm_file),
                        winsound.SND_FILENAME | winsound.SND_ASYNC,
                    )
                    return
            except (ImportError, RuntimeError):
                pass
        app = QApplication.instance()
        if app is not None:
            app.beep()

    def stop_alarm(self) -> None:
        process, self._sound_process = self._sound_process, None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=0.5)
            except OSError:
                pass
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.5)
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except (ImportError, RuntimeError):
                pass

    @staticmethod
    def _apple_text(value: str) -> str:
        return (str(value).replace("\\", "\\\\").replace('"', '\\"')
                .replace("\r", " ").replace("\n", " "))

    def _reap_alarm(self) -> None:
        process = self._sound_process
        if process is not None and process.poll() is not None:
            process.wait()
            self._sound_process = None
