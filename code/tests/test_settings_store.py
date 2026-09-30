import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import settings_store


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.patches = [
            patch.object(settings_store, "APP_DIR", self.folder),
            patch.object(settings_store, "SETTINGS_FILE", self.folder / "settings.json"),
            patch.object(settings_store, "site_day", return_value="2026-09-29"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_bet_window_and_profit_limits_are_saved(self):
        settings_store.save_bets("5", ["3", "4", "5", "6", "7"], True, "2", "500", "300")
        value = settings_store.load_settings()
        self.assertEqual(value.bet_start_offset, 3)
        self.assertEqual(value.bet_count, 5)
        self.assertEqual(value.bet_points, 3)
        self.assertEqual(value.bet_points_schedule, (3, 4, 5, 6, 7))
        self.assertEqual(value.profit_limit, 500)
        self.assertEqual(value.loss_limit, 300)

    def test_manual_profit_refresh_halts_only_after_configured_threshold(self):
        settings_store.save_bets("3", ["1", "2", "3"], True, "1", "500", "300")
        self.assertEqual(settings_store.save_profit_snapshot(-299), (False, ""))
        halted, reason = settings_store.save_profit_snapshot(-300)
        self.assertTrue(halted)
        self.assertIn("亏损 300", reason)
        value = settings_store.load_settings()
        self.assertEqual(value.profit_halt_date, "2026-09-29")
        self.assertEqual(value.today_profit, -300)

    def test_legacy_settings_default_to_next_issue_and_no_limits(self):
        settings_store.SETTINGS_FILE.write_text(
            '{"url":"https://example.test","bet_count":3,"bet_points":1}',
            encoding="utf-8",
        )
        value = settings_store.load_settings()
        self.assertEqual(value.bet_start_offset, 1)
        self.assertIsNone(value.profit_limit)
        self.assertIsNone(value.loss_limit)

    def test_zero_delay_means_the_immediate_next_issue(self):
        settings_store.save_bets("3", ["1", "1", "1"], True, "0")
        self.assertEqual(settings_store.load_settings().bet_start_offset, 1)

    def test_every_bet_period_requires_its_own_points(self):
        with self.assertRaisesRegex(ValueError, "分别填写"):
            settings_store.save_bets("3", ["1", "2"], True, "0")

    def test_history_and_profit_intervals_are_saved_separately(self):
        self.assertEqual(settings_store.save_poll_intervals("20", "45"), (20, 45))
        value = settings_store.load_settings()
        self.assertEqual(value.poll_interval, 20)
        self.assertEqual(value.profit_poll_interval, 45)

    def test_profit_halt_is_latched_for_the_rest_of_china_day(self):
        settings_store.save_bets("1", ["1"], True, "0", "500", "300")
        halted, original = settings_store.save_profit_snapshot(-350)
        self.assertTrue(halted)
        halted, reason = settings_store.save_profit_snapshot(-10)
        self.assertTrue(halted)
        self.assertEqual(reason, original)
        value = settings_store.load_settings()
        self.assertEqual(value.today_profit, -10)
        self.assertEqual(value.profit_halt_date, "2026-09-29")


if __name__ == "__main__":
    unittest.main()
