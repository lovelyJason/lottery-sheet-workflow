import os
import sys
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from debug_tools import DebugDialog, development_mode


class DebugToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_running_main_source_is_development_mode(self):
        with patch.dict(os.environ, {"LOTTERY_DEV_MODE": ""}), patch.object(sys, "argv", ["main.py"]):
            self.assertTrue(development_mode())
        with patch.dict(os.environ, {"LOTTERY_DEV_MODE": ""}), patch.object(sys, "argv", ["unittest"]):
            self.assertFalse(development_mode())

    def test_environment_can_force_development_on_or_off(self):
        with patch.dict(os.environ, {"LOTTERY_DEV_MODE": "1"}), patch.object(sys, "argv", ["main.py"]):
            self.assertTrue(development_mode())
        with patch.dict(os.environ, {"LOTTERY_DEV_MODE": "0"}), patch.object(sys, "argv", ["main.py"]):
            self.assertFalse(development_mode())

    def test_alert_debug_uses_the_real_alerter_boundary_and_reason(self):
        alerter = Mock()
        dialog = DebugDialog(alerter)
        try:
            dialog.reason.setText("测试：登录态过期")
            dialog.test_alert()
            alerter.alert.assert_called_once_with("开发模式告警测试", "测试：登录态过期")
            dialog.test_notification()
            alerter.notify.assert_called_once_with("开发模式通知测试", "测试：登录态过期")
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
