import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from config_dialogs import BetDialog, RunDialog
from settings_store import Settings


class BetDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_delay_help_bubble_explains_restart_and_examples(self):
        with patch("config_dialogs.load_settings", return_value=Settings(
                "https://example.test", 3, 1, 10, True, 2,
                bet_points_schedule=(1, 2, 5))):
            dialog = BetDialog()
        try:
            helps = [button for button in dialog.findChildren(QToolButton)
                     if button.objectName() == "fieldHelp" and "取消旧轮次" in button.toolTip()]
            self.assertEqual(len(helps), 1)
            self.assertEqual(helps[0].text(), "?")
            self.assertIn("119", helps[0].toolTip())
            self.assertEqual(dialog.bet_delay.text(), "1")
            self.assertEqual([edit.text() for edit in dialog.point_edits], ["1", "2", "5"])
            dialog.bet_count.setText("4")
            self.assertEqual(len(dialog.point_edits), 4)
            self.assertEqual([edit.text() for edit in dialog.point_edits[:3]], ["1", "2", "5"])
        finally:
            dialog.deleteLater()

    def test_run_dialog_has_separate_history_and_profit_intervals(self):
        with patch("config_dialogs.load_settings", return_value=Settings(
                "https://example.test", 2, 1, 10,
                profit_poll_interval=25)):
            dialog = RunDialog()
        try:
            self.assertEqual(dialog.interval.text(), "10")
            self.assertEqual(dialog.profit_interval.text(), "25")
            labels = [label.text() for label in dialog.findChildren(QLabel)]
            self.assertIn("查询与下注轮询时间间隔", labels)
            self.assertIn("查询盈亏值时间间隔", labels)
            with patch("config_dialogs.save_poll_intervals",
                       return_value=(12, 30)) as save:
                dialog.interval.setText("12")
                dialog.profit_interval.setText("30")
                dialog._save()
            save.assert_called_once_with("12", "30")
        finally:
            dialog.deleteLater()

    def test_profit_limits_follow_auto_bet_switch_visibility(self):
        with patch("config_dialogs.load_settings", return_value=Settings(
                "https://example.test", 2, 1, 10, False, 1,
                bet_points_schedule=(1, 2))):
            dialog = BetDialog()
        try:
            dialog.show()
            self.assertTrue(dialog.form_panel.isHidden())
            self.assertFalse(dialog.bet_delay.isVisible())
            self.assertFalse(dialog.bet_count.isVisible())
            self.assertFalse(dialog.points_scroll.isVisible())
            self.assertFalse(dialog.profit_limit.isVisible())
            self.assertFalse(dialog.loss_limit.isVisible())
            dialog.auto_bet.setChecked(True)
            self.assertFalse(dialog.form_panel.isHidden())
            self.assertTrue(dialog.bet_delay.isVisible())
            self.assertTrue(dialog.bet_count.isVisible())
            self.assertTrue(dialog.points_scroll.isVisible())
            self.assertTrue(dialog.profit_limit.isVisible())
            self.assertTrue(dialog.loss_limit.isVisible())
        finally:
            dialog.deleteLater()
