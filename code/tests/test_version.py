import unittest

from version import APP_TITLE, APP_VERSION


class VersionTests(unittest.TestCase):
    def test_version_is_single_source_for_v123_package(self):
        self.assertEqual(APP_VERSION, "1.2.3")
        self.assertEqual(APP_TITLE, "黄金万两 v1.2.3")


if __name__ == "__main__":
    unittest.main()
