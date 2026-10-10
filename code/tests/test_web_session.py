import unittest
from unittest.mock import Mock

from PySide6.QtTest import QSignalSpy

from web_session import (
    BrowserSessionWorker, browser_storage_payload, game_url, storage_script,
)


AUTH = {
    "token": "T" * 80,
    "refreshToken": "R" * 80,
    "uuid": "device-uuid",
}
USER_INFO = {"id": 123, "status": 1, "username": "member"}


class WebSessionTests(unittest.TestCase):
    def test_game_url_uses_saved_site_origin(self):
        self.assertEqual(
            game_url("https://web.example.test/pages/users/openResult"),
            "https://web.example.test/pages/game/bingoLh?lang=zh-cn",
        )

    def test_browser_payload_matches_site_local_storage_shape(self):
        payload = browser_storage_payload(AUTH, USER_INFO)
        self.assertEqual(payload["token"], "Bearer " + AUTH["token"])
        self.assertEqual(payload["refreshToken"], AUTH["refreshToken"])
        self.assertEqual(payload["uuid"], "device-uuid")
        self.assertEqual(payload["userInfo"], USER_INFO)
        self.assertTrue(payload["userStatus"])
        script = storage_script("https://web.example.test", payload)
        self.assertIn("location.origin", script)
        self.assertIn("localStorage.setItem('user'", script)
        self.assertIn("https://web.example.test", script)

    def test_worker_fetches_user_info_before_opening(self):
        session = Mock()
        session.prepare_browser_session.return_value = (AUTH, USER_INFO)
        worker = BrowserSessionWorker(
            "https://web.example.test", AUTH, session
        )
        succeeded, failed = QSignalSpy(worker.succeeded), QSignalSpy(worker.failed)
        worker.run()
        self.assertEqual(succeeded.count(), 1)
        self.assertEqual(failed.count(), 0)
        emitted = succeeded.at(0)[0]
        self.assertEqual(
            emitted["url"],
            "https://web.example.test/pages/game/bingoLh?lang=zh-cn",
        )
        self.assertEqual(emitted["storage"]["userInfo"], USER_INFO)


if __name__ == "__main__":
    unittest.main()
