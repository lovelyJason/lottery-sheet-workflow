import unittest
from unittest.mock import patch

from external_links import open_external_url


class ExternalLinkTests(unittest.TestCase):
    def test_windows_uses_native_shell_first(self):
        with patch("external_links.sys.platform", "win32"), \
                patch("external_links.os.startfile", create=True) as started, \
                patch("external_links.QDesktopServices.openUrl") as qt_opened:
            self.assertTrue(open_external_url("http://www.ttshitu.com/user/index.html"))
        started.assert_called_once_with("http://www.ttshitu.com/user/index.html")
        qt_opened.assert_not_called()

    def test_qt_failure_falls_back_to_python_browser(self):
        with patch("external_links.sys.platform", "darwin"), \
                patch("external_links.QDesktopServices.openUrl", return_value=False), \
                patch("external_links.webbrowser.open", return_value=True) as opened:
            self.assertTrue(open_external_url("https://example.test/account"))
        opened.assert_called_once_with(
            "https://example.test/account", new=2, autoraise=True
        )

    def test_non_http_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "http"):
            open_external_url("file:///tmp/test")


if __name__ == "__main__":
    unittest.main()
