import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
