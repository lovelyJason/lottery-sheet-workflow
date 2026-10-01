"""GUI lifecycle regressions; no network or real credentials/configuration used."""
from contextlib import ExitStack
from datetime import datetime
import os
from pathlib import Path
import tempfile
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from main import MainWindow
from result_dialogs import HistoryDialog, _worker_alive
from settings_store import Settings


class HistoryGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        if not isinstance(cls.app, QApplication):
            raise RuntimeError("Run GUI tests separately from QCoreApplication-only tests")
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        temporary = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = Path(temporary) / "results_已完成.xlsx"
        self.path.touch()
        self.entered, self.release = Event(), Event()
        self.auth = {"token": "test-access-token", "refreshToken": "test-refresh-token",
                     "uuid": "test-uuid"}
        self.settings = Settings("https://web.example.test", None, None, 60)
        for target, result in (
            ("main.load", self.auth),
            ("main.load_settings", self.settings),
            ("login_dialog.load", self.auth),
            ("login_dialog.load_settings", self.settings),
            ("history_panel.load", self.auth),
            ("history_panel.load_settings", self.settings),
            ("history_panel.load_config", {"workbook": str(self.path)}),
        ):
            self.stack.enter_context(patch(target, return_value=result))
        self.stack.enter_context(patch("history_panel.save_config"))
        self.stack.enter_context(patch("app_log.info"))
        self.stack.enter_context(patch("app_log.error"))
        self.sync = Mock()
        self.sync.needs_more.return_value = False
        self.sync.apply.return_value = SimpleNamespace(written=1, ambiguous=0)
        self.stack.enter_context(patch("history_worker.WorkbookSync", return_value=self.sync))
        client = self.stack.enter_context(patch("history_worker.HistoryClient"))
        client.return_value.fetch_page.side_effect = self._fetch
        self.window = MainWindow()
        self.panel = self.window.history_panel
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self._shutdown)

    def _fetch(self, day, page):
        self.entered.set()
        if not self.release.wait(3):
            raise AssertionError("Test failed to release fake API")
        return [{"issue": "115054989", "special_code": 18, "open_time": 1790603700}]

    def _until(self, condition, timeout=2):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertTrue(condition(), "Timed out waiting for Qt lifecycle state")

    def _shutdown(self):
        self.panel.stop_polling()
        self.release.set()
        if self.panel.worker is not None:
            self.panel.worker.wait(4000)
        self.app.processEvents()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _assert_locked(self, locked):
        for control in (self.window.login_dialog.import_btn, self.window.login_dialog.clear_btn,
                        self.window.login_dialog.url_edit, self.window.login_dialog.url_save,
                        self.window.sheet_panel.template_btn,
                        self.panel.choose, self.panel.use_copy, self.panel.today):
            self.assertEqual(control.isEnabled(), not locked)
        self.assertTrue(self.window.login_btn.isEnabled())

    def test_configuration_is_visible_on_home_and_login_is_dialog(self):
        sheet = self.window.sheet_panel
        self.assertNotIsInstance(sheet, QDialog)
        self.assertIs(sheet.history_panel, self.panel)
        self.assertTrue(self.window.centralWidget().isAncestorOf(sheet))
        self.assertTrue(self.panel.isVisible())
        self.assertFalse(self.window.login_dialog.isVisible())
        self.assertEqual(self.window.login_btn.text(), "登录管理")
        self.assertTrue(self.window.login_dialog.isAncestorOf(self.window.login_dialog.url_edit))
        self.assertGreaterEqual(self.window.width(), 760)
        self.assertGreaterEqual(self.window.height(), 600)
        buttons = [b.text() for b in self.window.centralWidget().findChildren(QPushButton)]
        self.assertEqual(buttons.count("开始"), 1)
        self.assertNotIn("立即补录", buttons)
        self.assertNotIn("开始轮询", buttons)
        self.assertNotIn("开奖配置", buttons)
        self.assertNotIn("导入登录态", buttons)
        self.assertFalse(any("关闭此窗口不停止轮询" in label.text()
                             for label in self.window.findChildren(QLabel)))
        self.assertIsNone(self.window.debug_button)

    def test_development_mode_shows_floating_debug_button(self):
        with patch.dict(os.environ, {"LOTTERY_DEV_MODE": "1"}):
            window = MainWindow()
        try:
            window.show()
            self.app.processEvents()
            self.assertIsNotNone(window.debug_button)
            self.assertTrue(window.debug_button.isVisible())
            self.assertEqual(window.debug_button.text(), "调试")
            self.assertGreater(window.debug_button.x(), window.width() // 2)
        finally:
            window.close()
            window.deleteLater()

    def test_login_entry_opens_dialog(self):
        observed = []
        def inspect_and_close():
            observed.append(self.window.login_dialog.isVisible())
            self.window.login_dialog.reject()
        QTimer.singleShot(0, inspect_and_close)
        self.window.login_btn.click()
        self.assertEqual(observed, [True])
        self.assertTrue(self.panel.isVisible())

    def test_close_login_keeps_polling_and_stop_is_on_home(self):
        dialog = self.window.login_dialog
        self.panel.start.click()
        self._until(self.entered.is_set)
        dialog.show()
        self.app.processEvents()
        self._assert_locked(True)
        dialog.reject()
        self.assertTrue(self.panel.running)
        self.assertFalse(self.panel.worker.cancel.is_set())
        self.assertTrue(self.panel.isVisible())
        self.assertTrue(self.panel.stop.isEnabled())
        self.panel.stop.click()
        self.release.set()
        self._until(lambda: not self.panel.busy)
        self.assertFalse(self.panel.timer.isActive())
        self.sync.apply.assert_not_called()
        self._assert_locked(False)

    def test_action_buttons_hug_text_and_date_toggle(self):
        from PySide6.QtWidgets import QSizePolicy
        self.app.processEvents()
        for button in (self.panel.choose,
                       self.panel.start, self.panel.stop, self.panel.open_page):
            self.assertEqual(button.sizePolicy().horizontalPolicy(), QSizePolicy.Fixed)
            self.assertLess(button.width(), 200)
        self.panel.today.setChecked(True)
        self.assertFalse(self.panel.day.isEnabled())
        self.panel.today.setChecked(False)
        self.assertTrue(self.panel.day.isEnabled())

    def test_close_waits_for_worker_and_cancels_without_write(self):
        self.panel._launch()
        self._until(self.entered.is_set)
        self.assertFalse(self.window.close())
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.panel.worker.cancel.is_set())
        self.release.set()
        self._until(lambda: not self.panel.busy and not self.window.isVisible())
        self.sync.apply.assert_not_called()
        self.sync.close.assert_called_once()
        self.assertFalse(self.panel.timer.isActive())

    def test_one_shot_locks_controls_until_finished_then_unlocks(self):
        self._assert_locked(False)
        self.panel._launch()
        self._until(self.entered.is_set)
        self._assert_locked(True)
        self.release.set()
        self._until(lambda: not self.panel.busy)
        self._assert_locked(False)
        self.sync.apply.assert_called_once()
        self.sync.close.assert_called_once()
        self.assertFalse(self.panel.timer.isActive())

    def test_poll_schedules_next_query_and_keeps_controls_locked(self):
        self.panel.start.click()
        self._until(self.entered.is_set)
        self._assert_locked(True)
        self.release.set()
        self._until(lambda: not self.panel.busy)
        self.sync.apply.assert_called_once()
        self.sync.close.assert_called_once()
        self.assertTrue(self.panel.timer.isActive())
        self.assertEqual(self.panel.timer.interval(), 60_000)
        self.assertEqual(self.panel.last_rows[0]["special_code"], 18)
        self._assert_locked(True)
        self.panel.stop_polling()
        self.assertFalse(self.panel.timer.isActive())
        self._assert_locked(False)

    def test_start_immediate_then_timer_requests_again_without_overlap(self):
        self.panel.start.click()
        self._until(self.entered.is_set)
        self.panel._start()
        self.release.set()
        self._until(lambda: not self.panel.busy)
        self.assertEqual(self.sync.apply.call_count, 1)
        self.panel.timer.start(1)
        self._until(lambda: self.sync.apply.call_count == 2 and not self.panel.busy)
        self.panel.stop.click()
        self.assertFalse(self.panel.timer.isActive())

    def test_start_with_missing_interval_does_not_launch(self):
        with patch("history_panel.load_settings", return_value=Settings(
                "https://web.example.test", None, None, None)):
            self.panel.start.click()
        self.assertFalse(self.panel.running)
        self.assertFalse(self.panel.busy)
        self.assertIn("轮询间隔", self.panel.note.text())

    def test_empty_daily_sheet_is_fetched_before_bet_targets_are_calculated(self):
        settings = Settings(
            "https://web.example.test", 3, 40, 60,
            auto_bet=True, bet_start_offset=1,
            bet_points_schedule=(40, 40, 40),
        )
        with patch("history_panel.load_settings", return_value=settings), \
                patch("history_panel.HistoryWorker") as worker:
            self.panel._launch()

        worker.assert_called_once()
        plan = worker.call_args.args[5]
        self.assertEqual(plan.point_schedule, (40, 40, 40))
        self.assertIsNone(plan.tail)
        self.assertIsNone(plan.zodiac)
        worker.return_value.start.assert_called_once()
        self.assertNotIn("H1", self.panel.note.text())
        self.panel.worker = None
        self.panel._controls()

    def test_run_settings_refresh_the_home_interval(self):
        settings = Settings("https://web.example.test", None, None, 17,
                            profit_poll_interval=23)
        with patch("main.RunDialog") as dialog, \
                patch("history_panel.load_settings", return_value=settings), \
                patch("main.load_settings", return_value=settings):
            self.window.run_btn.click()
        dialog.return_value.exec.assert_called_once()
        self.assertEqual(self.panel.interval_label.text(), "间隔 17 秒")
        self.assertTrue(self.window.profit_timer.isActive())
        self.assertEqual(self.window.profit_timer.interval(), 23_000)

    def test_profit_timer_refreshes_home_value_without_history_or_bet(self):
        settings = Settings("https://web.example.test", None, None, 60,
                            auto_bet=False, profit_poll_interval=1)
        refresh = Mock()
        self.window.refresh_profit = refresh
        with patch("main.load_settings", return_value=settings):
            self.window._configure_profit_timer()
        self._until(lambda: refresh.called)
        refresh.assert_called_with(automatic=True)
        self.window.profit_timer.stop()

    def test_history_close_during_fetch_keeps_the_thread(self):
        from unittest.mock import patch
        dialog = HistoryDialog(self.window)
        try:
            with patch("result_dialogs.load_settings", return_value=self.settings), patch(
                "result_dialogs.load", return_value=self.auth
            ):
                dialog.show()
                self._until(self.entered.is_set)
            worker = dialog._fetch
            self.assertIsNotNone(worker)
            dialog.reject()
            self.app.processEvents()
            self.assertFalse(dialog.isVisible())
            self.assertTrue(worker.isRunning())
            self.assertTrue(_worker_alive(worker))
        finally:
            self.release.set()
            if dialog._fetch is not None:
                dialog._fetch.wait(4000)
            self.app.processEvents()
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()

    def test_history_loading_is_a_spinner(self):
        dialog = HistoryDialog(self.window)
        try:
            self.assertFalse(dialog.empty.isVisible())
            self.assertNotIn("正在", dialog.empty.text())
            dialog._start_loading()
            self.assertFalse(dialog.spinner.isHidden())
            self.assertFalse(dialog.empty.isVisible())
            dialog._stop_loading()
            self.assertTrue(dialog.spinner.isHidden())
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_history_timestamp_uses_local_time_not_fixed_offset(self):
        dialog = HistoryDialog(self.window)
        try:
            dialog.set_results([{"issue": "115054989", "open_time": 1790603700}])
            expected = datetime.fromtimestamp(1790603700).strftime("%Y-%m-%d %H:%M:%S")
            self.assertEqual(dialog.table.item(2, 1).text(), expected)
        finally:
            dialog.close()
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
