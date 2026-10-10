import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import app_log


class AppLogTests(unittest.TestCase):
    def setUp(self):
        self.original = list(app_log._lines)
        app_log._lines.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        app_log._lines[:] = self.original

    def test_write_persists_china_timestamp_and_renders_it_after_level(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.log"
            with patch("app_log.LOG_FILE", path), \
                 patch("app_log.datetime") as clock:
                clock.now.return_value = datetime(2026, 9, 29, 21, 8, 7)
                app_log.info("自动投注成功")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "[2026-09-29 21:08:07] INFO --- 自动投注成功\n",
            )
            rendered = app_log.document_html()
            self.assertLess(rendered.index("INFO"), rendered.index("2026-09-29 21:08:07"))
            self.assertIn("margin:0 0 4px 0; line-height:140%", rendered)

    def test_saved_log_can_be_loaded_after_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.log"
            path.write_text(
                "[2026-09-29 20:01:02] ERROR --- 积分不足,投注失败\n",
                encoding="utf-8",
            )
            app_log._load_history(path)
        self.assertEqual(
            app_log.history(),
            [("2026-09-29 20:01:02", "ERROR", "积分不足,投注失败")],
        )

    def test_clear_removes_active_rotated_files_and_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.log"
            rotated = path.with_suffix(".log.1")
            path.write_text("active", encoding="utf-8")
            rotated.write_text("rotated", encoding="utf-8")
            app_log._lines.append(("2026-09-29 20:01:02", "INFO", "消息"))
            with patch("app_log.LOG_FILE", path):
                app_log.clear()
            self.assertFalse(path.exists())
            self.assertFalse(rotated.exists())
            self.assertEqual(app_log.history(), [])

    def test_editor_command_uses_the_system_text_editor(self):
        path = Path("/tmp/runtime.log")
        with patch("app_log.sys.platform", "win32"):
            self.assertEqual(app_log.editor_command(path), ["notepad.exe", str(path)])
        with patch("app_log.sys.platform", "darwin"):
            self.assertEqual(app_log.editor_command(path), ["open", "-e", str(path)])

    def test_open_in_editor_creates_missing_file_and_launches_editor(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.log"
            with patch("app_log.LOG_FILE", path), patch("app_log.subprocess.Popen") as launched:
                app_log.open_in_editor()
            self.assertTrue(path.is_file())
            launched.assert_called_once_with(app_log.editor_command(path))

    def test_log_dialog_is_edge_to_edge_with_corner_actions(self):
        from PySide6.QtWidgets import QApplication, QLabel, QPushButton

        from result_dialogs import LogDialog

        app = QApplication.instance() or QApplication([])
        dialog = LogDialog()
        try:
            dialog.show()
            app.processEvents()
            texts = [label.text() for label in dialog.findChildren(QLabel)]
            self.assertNotIn("运行日志", texts)
            self.assertFalse(any("历史日志会自动保留" in text for text in texts))
            self.assertFalse(any("持久化记录中" in text for text in texts))
            self.assertFalse(any(text.startswith("日志文件") for text in texts))
            margins = dialog.layout().contentsMargins()
            self.assertEqual((margins.left(), margins.top(), margins.right(), margins.bottom()), (0, 0, 0, 0))
            self.assertEqual(dialog.view.geometry().x(), 0)
            self.assertEqual(dialog.view.geometry().y(), 0)
            self.assertEqual(dialog.view.width(), dialog.width())
            self.assertEqual(dialog.view.height(), dialog.height())
            clear = next(button for button in dialog.findChildren(QPushButton) if button.text() == "清除日志")
            open_log = next(button for button in dialog.findChildren(QPushButton) if button.text() == "打开日志")
            clear_corner = clear.mapTo(dialog, clear.rect().bottomRight())
            open_corner = open_log.mapTo(dialog, open_log.rect().bottomRight())
            self.assertGreater(clear_corner.x(), dialog.width() - 30)
            self.assertGreater(clear_corner.y(), dialog.height() - 30)
            self.assertLess(open_corner.x(), clear_corner.x())
        finally:
            dialog.done(0)


if __name__ == "__main__":
    unittest.main()
