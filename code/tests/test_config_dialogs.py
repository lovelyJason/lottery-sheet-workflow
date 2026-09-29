import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QToolButton

from config_dialogs import BetDialog
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

    def test_profit_limits_follow_auto_bet_switch_visibility(self):
        with patch("config_dialogs.load_settings", return_value=Settings(
                "https://example.test", 2, 1, 10, False, 1,
                bet_points_schedule=(1, 2))):
            dialog = BetDialog()
        try:
            self.assertTrue(dialog.profit_limit.isHidden())
            self.assertTrue(dialog.loss_limit.isHidden())
            self.assertTrue(dialog.profit_limit._field_label_widget.isHidden())
            self.assertTrue(dialog.loss_limit._field_label_widget.isHidden())
            dialog.auto_bet.setChecked(True)
            self.assertFalse(dialog.profit_limit.isHidden())
            self.assertFalse(dialog.loss_limit.isHidden())
            self.assertFalse(dialog.profit_limit._field_label_widget.isHidden())
            self.assertFalse(dialog.loss_limit._field_label_widget.isHidden())
        finally:
            dialog.deleteLater()
