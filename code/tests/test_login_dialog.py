"""Login controls keep their behavior after moving out of the home window."""
from contextlib import ExitStack
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit
from login_dialog import LoginDialog
from auto_login import LoginCredentials
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
        self.credentials = self.stack.enter_context(
            patch("login_dialog.load_credentials", return_value=LoginCredentials())
        )
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

    def test_auto_relogin_credentials_are_configured_in_the_dialog(self):
        self.assertTrue(self.dialog.auto_relogin.isChecked())
        self.assertEqual(self.dialog.login_retry_count.value(), 10)
        self.dialog.site_username.setText("site-user")
        self.dialog.site_password.setText("site-password")
        self.dialog.captcha_username.setText("captcha-user")
        self.dialog.captcha_password.setText("captcha-password")
        self.dialog.login_retry_count.setValue(7)
        with patch("login_dialog.save_credentials") as save:
            self.assertTrue(self.dialog.save_login_credentials())
        saved = save.call_args.args[0]
        self.assertEqual(saved.site_username, "site-user")
        self.assertEqual(saved.site_password, "site-password")
        self.assertEqual(saved.captcha_username, "captcha-user")
        self.assertEqual(saved.captcha_password, "captcha-password")
        self.assertTrue(saved.auto_relogin)
        self.assertEqual(saved.login_retry_count, 7)

    def test_retry_count_loads_and_is_locked_while_polling(self):
        configured = LoginCredentials(
            "site-user", "site-password", "captcha-user", "captcha-password",
            True, 4,
        )
        self.credentials.return_value = configured
        self.dialog._load_credential_fields()
        self.assertEqual(self.dialog.login_retry_count.value(), 4)
        self.dialog.set_active(True)
        self.assertFalse(self.dialog.login_retry_count.isEnabled())
        self.dialog.set_active(False)
        self.assertTrue(self.dialog.login_retry_count.isEnabled())

    def test_saved_passwords_stay_in_fields_and_eye_toggles_visibility(self):
        configured = LoginCredentials(
            "site-user", "site-password", "captcha-user", "captcha-password"
        )
        self.credentials.return_value = configured
        self.dialog._load_credential_fields()
        for field, expected in (
            (self.dialog.site_password, "site-password"),
            (self.dialog.captcha_password, "captcha-password"),
        ):
            self.assertEqual(field.text(), expected)
            self.assertEqual(field.echoMode(), QLineEdit.Password)
            self.assertEqual(len(field.actions()), 1)
            field.actions()[0].trigger()
            self.assertEqual(field.echoMode(), QLineEdit.Normal)
            self.assertEqual(field.text(), expected)
            field.actions()[0].trigger()
            self.assertEqual(field.echoMode(), QLineEdit.Password)

    def test_open_captcha_site_uses_reliable_external_link_opener(self):
        with patch("login_dialog.open_external_url", return_value=True) as opened:
            self.dialog.open_captcha_site.click()
        opened.assert_called_once_with("http://www.ttshitu.com/user/index.html")

    def test_open_captcha_site_shows_a_visible_error(self):
        with patch("login_dialog.open_external_url", return_value=False):
            self.dialog.open_captcha_site.click()
        self.assertFalse(self.dialog.credentials_error.isHidden())
        self.assertIn("打开打码网站失败", self.dialog.credentials_error.text())

    def test_ready_badges_keep_visible_text_height(self):
        configured = LoginCredentials(
            "site-user", "site-password", "captcha-user", "captcha-password"
        )
        self.auth.return_value = self.payload
        self.credentials.return_value = configured
        self.dialog.refresh()
        self.app.processEvents()
        self.assertEqual(self.dialog.badge.text(), "已导入")
        self.assertEqual(self.dialog.auto_badge.text(), "自动续登已配置")
        self.assertGreaterEqual(self.dialog.badge.height(), 24)
        self.assertGreaterEqual(self.dialog.auto_badge.height(), 24)
