"""Login controls keep their behavior after moving out of the home window."""
from contextlib import ExitStack
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog
from login_dialog import LoginDialog
from settings_store import Settings


class LoginDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.payload = {"token": "test-session-placeholder", "refreshToken": "test-refresh-placeholder",
                        "uuid": "test-uuid-placeholder"}
        self.auth = self.stack.enter_context(patch("login_dialog.load", return_value=None))
        self.stack.enter_context(patch("login_dialog.load_settings", return_value=Settings(
            "https://web.example.test", None, None, 30)))
        self.dialog = LoginDialog()
        self.addCleanup(self.dialog.deleteLater)
        self.addCleanup(self.dialog.close)

    def test_import_retains_single_account_save_and_masks_values(self):
        with patch("login_dialog.ImportDialog") as imported, \
                patch("login_dialog.save") as save, \
                patch("login_dialog.QMessageBox.information"):
            imported.return_value.exec.return_value = QDialog.Accepted
            imported.return_value.payload = self.payload
            self.auth.return_value = self.payload
            changed = QSignalSpy(self.dialog.changed)
            self.dialog.import_btn.click()
            save.assert_called_once_with(self.payload)
            self.assertEqual(changed.count(), 1)
            self.assertNotEqual(self.dialog.values["token"].text(), self.payload["token"])
            self.assertTrue(self.dialog.clear_btn.isEnabled())

    def test_address_save_and_inline_validation(self):
        changed = QSignalSpy(self.dialog.changed)
        self.dialog.url_edit.setText("https://new.example.test/")
        with patch("login_dialog.save_url", return_value="https://new.example.test") as save:
            self.dialog.url_save.click()
            save.assert_called_once_with("https://new.example.test/")
        self.assertEqual(self.dialog.url_edit.text(), "https://new.example.test")
        self.assertEqual(changed.count(), 1)
        with patch("login_dialog.save_url", side_effect=ValueError("地址格式错误")):
            self.dialog.url_save.click()
        self.assertEqual(changed.count(), 1)
        self.assertEqual(self.dialog.url_error.text(), "地址格式错误")
        self.assertFalse(self.dialog.url_error.isHidden())

    def test_polling_guards_mutations_but_guide_stays_enabled(self):
        self.auth.return_value = self.payload
        self.dialog.set_active(True)
        with patch("login_dialog.save_url") as url, \
                patch("login_dialog.ImportDialog") as imported, \
                patch("login_dialog.clear") as clear:
            self.dialog.save_site_url()
            self.dialog.import_auth()
            self.dialog.clear_auth()
            url.assert_not_called()
            imported.assert_not_called()
            clear.assert_not_called()
        self.assertFalse(self.dialog.clear_btn.isEnabled())
        self.assertTrue(self.dialog.guide_btn.isEnabled())
        self.dialog.set_active(False)
        self.assertTrue(self.dialog.import_btn.isEnabled())
        self.assertTrue(self.dialog.url_edit.isEnabled())
        self.assertTrue(self.dialog.clear_btn.isEnabled())

    def test_cancelled_import_does_not_save_or_signal(self):
        changed = QSignalSpy(self.dialog.changed)
        with patch("login_dialog.ImportDialog") as imported, patch("login_dialog.save") as save:
            imported.return_value.exec.return_value = QDialog.Rejected
            self.dialog.import_btn.click()
            save.assert_not_called()
            self.assertEqual(changed.count(), 0)
