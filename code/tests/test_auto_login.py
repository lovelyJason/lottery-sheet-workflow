import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from auto_login import (
    AutoLoginError, LoginClient, LoginCredentials, TtshituSolver,
    load_credentials, save_credentials,
)
from session_errors import SessionExpiredError
from session_manager import SessionManager


class Opener:
    def __init__(self, *values):
        self.values = iter(values)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(json.dumps(value).encode())


CONFIG = LoginCredentials("site-user", "site-password", "captcha-user", "captcha-password")
DOMAIN = {"domain": "https://api.example.test"}


class CredentialTests(unittest.TestCase):
    def test_credentials_are_private_and_auto_relogin_defaults_on(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credentials.json"
            self.assertTrue(load_credentials(path).auto_relogin)
            save_credentials(CONFIG, path)
            self.assertEqual(load_credentials(path), CONFIG)
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_old_credentials_default_to_ten_login_retries(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credentials.json"
            path.write_text(json.dumps({
                "site_username": "site-user",
                "site_password": "site-password",
                "captcha_username": "captcha-user",
                "captcha_password": "captcha-password",
                "auto_relogin": True,
            }), encoding="utf-8")
            self.assertEqual(load_credentials(path).login_retry_count, 10)

    def test_login_retry_count_is_saved_and_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credentials.json"
            configured = LoginCredentials(
                "site-user", "site-password", "captcha-user",
                "captcha-password", True, 6,
            )
            save_credentials(configured, path)
            self.assertEqual(load_credentials(path).login_retry_count, 6)
            for invalid in (0, 101, True):
                with self.subTest(invalid=invalid), self.assertRaisesRegex(
                    AutoLoginError, "重试次数"
                ):
                    save_credentials(LoginCredentials(
                        "site-user", "site-password", "captcha-user",
                        "captcha-password", True, invalid,
                    ), path)

    def test_all_four_credentials_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(AutoLoginError, "打码平台密码"):
                save_credentials(
                    LoginCredentials("site", "password", "captcha", ""),
                    Path(temporary) / "credentials.json",
                )


class CaptchaTests(unittest.TestCase):
    def test_ttshitu_numeric_contract_strips_data_uri_prefix(self):
        opener = Opener({
            "success": True, "code": "0", "message": "success",
            "data": {"result": "7646", "id": "result-id"},
        })
        result = TtshituSolver(opener).solve(
            "data:image/png;base64,YWJjZA==", CONFIG
        )
        self.assertEqual(result, "7646")
        request, timeout = opener.requests[0]
        payload = json.loads(request.data)
        self.assertEqual(timeout, 60)
        self.assertEqual(payload, {
            "username": "captcha-user", "password": "captcha-password",
            "typeid": "1", "image": "YWJjZA==",
        })

    def test_ttshitu_error_reason_is_preserved(self):
        opener = Opener({"success": False, "code": "-1", "message": "余额不足"})
        with self.assertRaisesRegex(AutoLoginError, "余额不足"):
            TtshituSolver(opener).solve("YWJjZA==", CONFIG)


class LoginProtocolTests(unittest.TestCase):
    def test_captcha_then_login_saves_observed_jwt_fields(self):
        token, refresh = "T" * 80, "R" * 80
        opener = Opener(
            DOMAIN,
            {"code": 200, "data": {
                "key": "$2y$10$captcha-key",
                "base64": "data:image/png;base64,YWJjZA==",
            }},
            {"code": 200, "encrypt": False, "data": {
                "jwtInfo": {"token": token, "refreshToken": refresh}
            }},
        )
        solver = Mock()
        solver.solve.return_value = "7646"
        auth = LoginClient(
            "https://web.example.test/", opener=opener, solver=solver
        ).login(CONFIG, "device-uuid-1234")
        self.assertEqual(auth, {
            "token": token, "refreshToken": refresh, "uuid": "device-uuid-1234"
        })
        request, timeout = opener.requests[-1]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.example.test/api/v1/member/login")
        self.assertEqual(timeout, 15)
        self.assertEqual(payload["username"], "site-user")
        self.assertEqual(payload["password"], "site-password")
        self.assertEqual(payload["code"], "7646")
        self.assertEqual(payload["key"], "$2y$10$captcha-key")
        self.assertEqual(payload["cf-turnstile-response"], "")
        self.assertEqual(request.get_header("Uuid"), "device-uuid-1234")

    def test_check_classifies_server_auth_code(self):
        client = LoginClient(
            "https://web.example.test", Opener(DOMAIN, {"code": 4001, "msg": "过期"})
        )
        with self.assertRaises(SessionExpiredError):
            client.check({"token": "TOKEN", "uuid": "DEVICE"})

    def test_check_returns_current_user_information(self):
        user_info = {"id": 123, "status": 1, "username": "member"}
        client = LoginClient(
            "https://web.example.test",
            Opener(DOMAIN, {"code": 200, "data": user_info}),
        )
        self.assertEqual(
            client.check({"token": "TOKEN", "uuid": "DEVICE"}), user_info
        )

    def test_login_401_keeps_the_server_failure_reason(self):
        opener = Opener(
            DOMAIN,
            {"code": 200, "data": {
                "key": "captcha-key", "base64": "YWJjZA==",
            }},
            {"code": 401, "msg": "账号或密码错误", "data": []},
        )
        solver = Mock()
        solver.solve.return_value = "3088"
        client = LoginClient(
            "https://web.example.test", opener=opener, solver=solver
        )
        with self.assertRaisesRegex(AutoLoginError, "账号或密码错误"):
            client.login(CONFIG, "device-uuid-1234")


class SessionManagerTests(unittest.TestCase):
    def test_renew_logs_in_once_and_persists_new_auth(self):
        fresh = {"token": "N" * 80, "refreshToken": "R" * 80, "uuid": "device-id"}
        client = Mock()
        client.login.return_value = fresh
        factory = Mock(return_value=client)
        manager = SessionManager(login_factory=factory)
        saved = Mock()
        with patch("session_manager.load_credentials", return_value=CONFIG), \
                patch("session_manager.load", return_value=None), \
                patch("session_manager.save", saved):
            result = manager.renew(
                "https://web.example.test", {"token": "OLD", "uuid": "device-id"},
                "历史补录",
            )
        self.assertEqual(result, fresh)
        saved.assert_called_once_with(fresh)
        client.login.assert_called_once_with(CONFIG, "device-id")

    def test_browser_session_returns_valid_auth_and_user_info(self):
        auth = {"token": "N" * 80, "refreshToken": "R" * 80, "uuid": "device-id"}
        user_info = {"id": 123, "status": 1}
        client = Mock()
        client.check.return_value = user_info
        manager = SessionManager(login_factory=Mock(return_value=client))
        self.assertEqual(
            manager.prepare_browser_session(
                "https://web.example.test", auth, "打开网站"
            ),
            (auth, user_info),
        )
        client.check.assert_called_once_with(auth)

    def test_renew_retries_twice_then_resumes_without_failure(self):
        fresh = {"token": "N" * 80, "refreshToken": "R" * 80, "uuid": "device-id"}
        config = LoginCredentials(
            "site-user", "site-password", "captcha-user", "captcha-password",
            True, 10,
        )
        client = Mock()
        client.login.side_effect = [
            AutoLoginError("登录失败：验证码错误"),
            AutoLoginError("登录失败：验证码错误"),
            fresh,
        ]
        manager = SessionManager(login_factory=Mock(return_value=client))
        retries, failures, restored = [], [], []
        manager.retrying.connect(lambda *args: retries.append(args))
        manager.failed.connect(failures.append)
        manager.restored.connect(restored.append)
        with patch("session_manager.load_credentials", return_value=config), \
                patch("session_manager.load", return_value=None), \
                patch("session_manager.save") as saved, \
                patch("session_manager.sleep") as delay:
            result = manager.renew(
                "https://web.example.test", {"token": "OLD", "uuid": "device-id"},
                "自动投注",
            )
        self.assertEqual(result, fresh)
        self.assertEqual(client.login.call_count, 3)
        self.assertEqual(retries, [
            ("登录失败：验证码错误", 1, 10),
            ("登录失败：验证码错误", 2, 10),
        ])
        self.assertEqual(failures, [])
        self.assertEqual(restored, ["自动投注"])
        self.assertEqual(delay.call_count, 2)
        saved.assert_called_once_with(fresh)

    def test_renew_stops_only_after_retry_limit_is_exhausted(self):
        config = LoginCredentials(
            "site-user", "site-password", "captcha-user", "captcha-password",
            True, 2,
        )
        client = Mock()
        client.login.side_effect = AutoLoginError("登录失败：验证码错误")
        manager = SessionManager(login_factory=Mock(return_value=client))
        retries, failures = [], []
        manager.retrying.connect(lambda *args: retries.append(args))
        manager.failed.connect(failures.append)
        with patch("session_manager.load_credentials", return_value=config), \
                patch("session_manager.load", return_value=None), \
                patch("session_manager.sleep"), \
                self.assertRaisesRegex(AutoLoginError, "已达到最大重试次数 2"):
            manager.renew(
                "https://web.example.test", {"token": "OLD", "uuid": "device-id"},
                "历史补录",
            )
        self.assertEqual(client.login.call_count, 3)
        self.assertEqual([item[1] for item in retries], [1, 2])
        self.assertEqual(len(failures), 1)
        self.assertIn("验证码错误", failures[0])


if __name__ == "__main__":
    unittest.main()
