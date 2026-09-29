import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import china_time


class ChinaTimeTests(unittest.TestCase):
    def test_missing_timezone_database_uses_china_standard_time(self):
        with patch("china_time.ZoneInfo", side_effect=KeyError("Asia/Shanghai")):
            zone = china_time.china_zone()
        self.assertEqual(
            zone.utcoffset(datetime(2026, 9, 29, tzinfo=timezone.utc)),
            china_time.CHINA_OFFSET.utcoffset(None),
        )


if __name__ == "__main__":
    unittest.main()
