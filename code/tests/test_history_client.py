import io
import json
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from history_client import HistoryClient, HistoryError, results_url

class Opener:
    def __init__(self, *values):
        self.values = iter(values)
        self.requests = []
    def open(self, request, timeout):
        self.requests.append(request)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(json.dumps(value).encode())

AUTH = {"token": "Bearer TEST_ACCESS", "uuid": "TEST_DEVICE", "refreshToken": "TEST_REFRESH"}
DOMAIN = {"domain": "https://api.example.test"}
ROW = {"issue": "115054996", "special_code": 33}
def body(rows=None):
    return {"code": 200, "encrypt": False, "data": {"data": [ROW] if rows is None else rows}}

class ClientTests(unittest.TestCase):
    def test_join_discovers_distinct_api_and_exact_contract(self):
        self.assertEqual(results_url("https://web.example.test/somewhere?x=1"),
                         "https://web.example.test/pages/users/openResult")
        op = Opener(DOMAIN, body())
        client = HistoryClient("https://web.example.test/", AUTH, op)
        self.assertEqual(client.fetch_page("2026-09-28", 1), [ROW])
        req = op.requests[1]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.full_url, "https://api.example.test/api/v1/member/openResultList?gameKey=bingoLh&date=2026-09-28&page=1")
        self.assertEqual(req.get_header("Authorization"), AUTH["token"])
        self.assertTrue(req.get_header("User-agent"))
        self.assertNotIn("Refresh-authorization", req.headers)
        self.assertEqual(req.get_header("Origin"), "https://web.example.test")
    def test_unrelated_domain_receives_no_credentials(self):
        op = Opener({"domain": "https://other.invalid"})
        with self.assertRaises(HistoryError):
            HistoryClient("https://web.example.test", AUTH, op).fetch_page("2026-09-28", 1)
        self.assertEqual(len(op.requests), 1)
        self.assertIsNone(op.requests[0].get_header("Authorization"))
    def test_encrypted_or_business_error_not_success(self):
        for payload in ({"code":200,"encrypt":True}, {"code":500,"msg":"积分不足,投注失败","data":[]},
                        {"code":200,"data":[]}, body([{"issue":"1000","special_code":True}])):
            with self.subTest(payload=payload), self.assertRaises(HistoryError):
                HistoryClient("https://web.example.test", AUTH, Opener(DOMAIN,payload)).fetch_page("2026-09-28",1)
    def test_sensitive_server_message_redacted(self):
        with self.assertRaises(HistoryError) as caught:
            HistoryClient("https://web.example.test",AUTH,Opener(DOMAIN,
                {"code":401,"msg":"TEST_ACCESS TEST_DEVICE TEST_REFRESH"})).fetch_page("2026-09-28",1)
        for secret in ("TEST_ACCESS","TEST_DEVICE","TEST_REFRESH"):
            self.assertNotIn(secret,str(caught.exception))
    def test_bad_url_and_no_redirect(self):
        for url in ("http://web.example.test", "https://user:pass@web.example.test", "https://web.example.test:99"):
            with self.assertRaises(HistoryError):
                HistoryClient(url, AUTH)
        redirect=HTTPError("https://api.example.test",302,"redirect",{},None)
        with self.assertRaises(HistoryError):
            HistoryClient("https://web.example.test",AUTH,Opener(DOMAIN,redirect)).fetch_page("2026-09-28",1)
    def test_site_success_code_40000(self):
        payload = {"code": 40000, "encrypt": False, "msg": "成功", "data": {"data": [ROW]}}
        client = HistoryClient("https://web.example.test", AUTH, Opener(DOMAIN, payload))
        self.assertEqual(client.fetch_page("2026-09-28", 1), [ROW])

    def test_expired_page_is_retried_from_that_page_after_relogin(self):
        renewed = {
            "token": "Bearer NEW_ACCESS", "uuid": "NEW_DEVICE",
            "refreshToken": "NEW_REFRESH",
        }
        session = unittest.mock.Mock()
        session.renew.return_value = renewed
        opener = Opener(DOMAIN, {"code": 4001, "msg": "expired"}, body())
        client = HistoryClient(
            "https://web.example.test", AUTH, opener, session=session,
            stage="历史补录",
        )
        self.assertEqual(client.fetch_page("2026-09-28", 3), [ROW])
        session.renew.assert_called_once()
        self.assertEqual(opener.requests[-1].get_header("Authorization"), "Bearer NEW_ACCESS")
        self.assertTrue(opener.requests[-1].full_url.endswith("page=3"))

    def test_empty_is_valid(self):
        client=HistoryClient("https://web.example.test",AUTH,Opener(DOMAIN,body([])))
        self.assertEqual(client.fetch_page("2026-09-28",1),[])

def _rows(start, count):
    return [{"issue": f"{start + i:04d}", "special_code": 1} for i in range(count)]

class FetchDayTests(unittest.TestCase):
    def test_later_pages_run_together_and_stop_at_short_page(self):
        client = HistoryClient("https://web.example.test", AUTH)
        client.api = "https://api.example.test"
        current = peak = 0
        lock = threading.Lock()

        def fake(self, day, page):
            nonlocal current, peak
            with lock:
                current += 1
                peak = max(peak, current)
            try:
                time.sleep(0.05)
                if page <= 2:
                    return _rows(page * 100, 2)
                if page == 3:
                    return _rows(300, 1)
                return _rows(page * 100, 2)
            finally:
                with lock:
                    current -= 1

        with patch.object(HistoryClient, "fetch_page", fake):
            rows = client.fetch_day("2026-09-28", limit=10)
        self.assertEqual([row["issue"] for row in rows], ["0100", "0101", "0200", "0201", "0300"])
        self.assertGreaterEqual(peak, 2)

if __name__ == "__main__":
    unittest.main()
