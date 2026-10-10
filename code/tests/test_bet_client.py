import tempfile
import unittest
import io
import json
from pathlib import Path
from unittest.mock import Mock, patch

from bet_client import (
    AutoBetRunner, BetClient, BetError, BetNetworkError, BetPlan, issue_distance,
    selected_numbers, zodiac_numbers,
)


class Opener:
    def __init__(self, *values):
        self.values = iter(values)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return io.BytesIO(json.dumps(next(self.values)).encode())


class SelectionTests(unittest.TestCase):
    def test_site_2026_monkey_and_tail_two_match_observed_ui(self):
        timestamp = 1790610600
        self.assertEqual(zodiac_numbers("猴", timestamp), {11, 23, 35, 47})
        selected = selected_numbers(BetPlan(1, 3, "2", "猴"), timestamp)
        self.assertEqual(len(selected), 40)
        for excluded in (2, 11, 12, 22, 23, 32, 35, 42, 47):
            self.assertNotIn(excluded, selected)

    def test_invalid_target_stops_before_order(self):
        with self.assertRaises(BetError):
            selected_numbers(BetPlan(1, 1, None, None), 1790610600)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "bet-state.json"
        self.client = Mock()
        self.client.game_id.return_value = 270048
        self.client.next_issue.return_value = ("115055012", 1790610600)
        self.client.build_payload.return_value = {
            "bet_info": [{"group": "specialCodeB", "subGroup": "guessNumberB"}] * 40
        }
        self.client.submit.return_value = "投注成功"
        self.plan = BetPlan(2, 3, "2", "猴")

    def test_same_issue_is_at_most_once(self):
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        outcome = runner.run_once(self.plan, "115055011", "115055011")
        self.assertEqual(outcome.total_points, 120)
        self.assertEqual(outcome.completed, 1)
        self.assertIsNone(runner.run_once(self.plan, None, "115055011"))
        self.client.submit.assert_called_once()

    def test_issue_is_reserved_even_when_submit_fails(self):
        self.client.submit.side_effect = BetError("积分不足,投注失败")
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        with self.assertRaisesRegex(BetError, "积分不足"):
            runner.run_once(self.plan, "115055011", "115055011")
        self.client.submit.reset_mock()
        self.client.submit.side_effect = None
        self.assertIsNone(runner.run_once(self.plan, None, "115055011"))
        self.client.submit.assert_not_called()

    def test_no_zero_trigger_means_no_bet(self):
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        self.assertIsNone(runner.run_once(self.plan, None, "115055011"))
        self.client.game_id.assert_not_called()

    def test_exactly_n_consecutive_slots_then_waits_for_next_zero(self):
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        for index, issue in enumerate(("115055012", "115055013"), 1):
            self.client.next_issue.return_value = (issue, 1790610600 + index * 300)
            outcome = runner.run_once(
                self.plan, "115055011" if index == 1 else None,
                str(int(issue) - 1),
            )
            self.assertEqual(outcome.completed, index)
        self.client.next_issue.return_value = ("115055014", 1790611500)
        self.assertIsNone(runner.run_once(self.plan, "115055011", "115055013"))
        self.assertEqual(self.client.submit.call_count, 2)

    def test_rejected_period_still_consumes_one_of_n_slots(self):
        self.client.submit.side_effect = BetError("积分不足,投注失败")
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        with self.assertRaises(BetError):
            runner.run_once(self.plan, "115055011", "115055011")
        self.client.submit.side_effect = None
        self.client.next_issue.return_value = ("115055013", 1790610900)
        outcome = runner.run_once(self.plan, None, "115055012")
        self.assertEqual(outcome.completed, 2)
        self.client.next_issue.return_value = ("115055014", 1790611200)
        self.assertIsNone(runner.run_once(self.plan, None, "115055013"))

    def test_start_offset_selects_the_requested_issue_window(self):
        plan = BetPlan(3, 3, "2", "猴", start_offset=2)
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        self.client.next_issue.return_value = ("115055012", 1790610600)
        self.assertIsNone(runner.run_once(plan, "115055011", "115055011"))
        self.client.submit.assert_not_called()
        for expected, issue in enumerate(("115055013", "115055014", "115055015"), 1):
            self.client.next_issue.return_value = (issue, 1790610600 + expected * 300)
            outcome = runner.run_once(plan, None, str(int(issue) - 1))
            self.assertEqual(outcome.completed, expected)
        self.client.next_issue.return_value = ("115055016", 1790611800)
        self.assertIsNone(runner.run_once(plan, None, "115055015"))
        self.assertEqual(self.client.submit.call_count, 3)

    def test_issue_distance_handles_999_to_001_boundary(self):
        self.assertEqual(issue_distance("115054999", "115055001"), 1)
        self.assertEqual(issue_distance("115054998", "115055002"), 3)

    def test_new_zero_restarts_an_active_campaign_and_discards_old_remainder(self):
        plan = BetPlan(6, 3, "2", "猴", start_offset=2)  # delay one issue
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        self.client.next_issue.return_value = ("115055120", 1790610600)
        self.assertIsNone(runner.run_once(plan, "115055119", "115055119"))
        for issue in ("115055121", "115055122", "115055123"):
            self.client.next_issue.return_value = (issue, 1790610600)
            self.assertIsNotNone(runner.run_once(plan, None, str(int(issue) - 1)))
        # Result 123 is another zero: old planned 124 is cancelled, and the
        # new delay skips 124 before the new campaign starts at 125.
        self.client.next_issue.return_value = ("115055124", 1790610600)
        self.assertIsNone(runner.run_once(plan, "115055123", "115055123"))
        self.client.next_issue.return_value = ("115055125", 1790610600)
        outcome = runner.run_once(plan, None, "115055124")
        self.assertEqual(outcome.completed, 1)
        submitted_issues = [
            call.args[0] for call in self.client.submit.call_args_list
        ]
        self.assertEqual(len(submitted_issues), 4)

    def test_new_zero_cannot_bet_an_issue_already_used_by_previous_campaign(self):
        old_plan = BetPlan(3, 40, "6", "蛇", 1, (40, 40, 40))
        new_plan = BetPlan(3, 40, "9", "蛇", 1, (40, 40, 40))
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)

        self.client.next_issue.return_value = ("115055402", 1790610600)
        self.assertIsNotNone(runner.run_once(old_plan, "115055401", "115055401"))

        # The betting endpoint advances before result 402 reaches history.
        self.client.next_issue.return_value = ("115055403", 1790610900)
        self.assertIsNotNone(runner.run_once(old_plan, None, "115055402"))

        # Result 402 then arrives as another zero and starts a new campaign.
        # Issue 403 was already submitted by the old campaign and must remain
        # globally reserved when the campaign/rule fingerprint changes.
        self.client.next_issue.return_value = ("115055403", 1790610900)
        self.assertIsNone(runner.run_once(new_plan, "115055402", "115055402"))
        self.assertEqual(self.client.submit.call_count, 2)

    def test_stale_history_blocks_old_campaign_from_betting_ahead(self):
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        self.client.next_issue.return_value = ("115055403", 1790610900)

        outcome = runner.run_once(
            self.plan, "115055401", latest_result_issue="115055401"
        )

        self.assertIsNone(outcome)
        self.client.build_payload.assert_not_called()
        self.client.submit.assert_not_called()

    def test_consecutive_zero_waits_for_result_then_uses_only_new_campaign(self):
        old_plan = BetPlan(3, 40, "6", "蛇", 1, (40, 40, 40))
        new_plan = BetPlan(3, 40, "9", "蛇", 1, (40, 40, 40))
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)

        self.client.next_issue.return_value = ("115055402", 1790610600)
        first = runner.run_once(old_plan, "115055401", "115055401")

        # Betting has advanced to 403 while history still ends at 401.
        self.client.next_issue.return_value = ("115055403", 1790610900)
        self.assertIsNone(runner.run_once(old_plan, None, "115055401"))

        # Once result 402 arrives and is another zero, only the restarted
        # campaign is allowed to submit the still-open issue 403.
        restarted = runner.run_once(new_plan, "115055402", "115055402")

        self.assertEqual((first.issue, restarted.issue), ("115055402", "115055403"))
        self.assertEqual(restarted.completed, 1)
        self.assertEqual(self.client.submit.call_count, 2)

    def test_each_period_uses_its_own_points_schedule(self):
        plan = BetPlan(3, 1, "2", "猴", 1, (1, 2, 5))
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        observed = []
        for index, issue in enumerate(("115055120", "115055121", "115055122"), 1):
            self.client.next_issue.return_value = (issue, 1790610600)
            outcome = runner.run_once(
                plan, "115055119" if index == 1 else None,
                str(int(issue) - 1),
            )
            used_plan = self.client.build_payload.call_args.args[1]
            observed.append((used_plan.points, outcome.points, outcome.total_points))
        self.assertEqual(observed, [(1, 1, 40), (2, 2, 80), (5, 5, 200)])


class ClientContractTests(unittest.TestCase):
    def test_today_profit_retries_network_failure_five_times_then_succeeds(self):
        client = BetClient(
            "https://web.example.test", {"token": "TOKEN", "uuid": "UUID"}
        )
        failures = [BetNetworkError("timeout")] * 5
        with patch.object(
                client, "_today_profit_once", side_effect=[*failures, -1177.0]
        ) as query, patch("bet_client.sleep") as sleep:
            self.assertEqual(client.today_profit(), -1177.0)

        self.assertEqual(query.call_count, 6)
        self.assertEqual(sleep.call_count, 5)

    def test_today_profit_does_not_retry_non_network_error(self):
        client = BetClient(
            "https://web.example.test", {"token": "TOKEN", "uuid": "UUID"}
        )
        with patch.object(
                client, "_today_profit_once", side_effect=BetError("登录态失效")
        ) as query, patch("bet_client.sleep") as sleep, self.assertRaisesRegex(
                BetError, "登录态失效"):
            client.today_profit()

        query.assert_called_once()
        sleep.assert_not_called()

    def test_today_profit_reports_when_all_five_retries_fail(self):
        client = BetClient(
            "https://web.example.test", {"token": "TOKEN", "uuid": "UUID"}
        )
        with patch.object(
                client, "_today_profit_once",
                side_effect=BetNetworkError("timeout"),
        ) as query, patch("bet_client.sleep") as sleep, self.assertRaisesRegex(
                BetNetworkError, "已重试5次"):
            client.today_profit()

        self.assertEqual(query.call_count, 6)
        self.assertEqual(sleep.call_count, 5)

    def test_today_profit_uses_same_issue_data_total_win_as_webpage(self):
        opener = Opener(
            {"domain": "https://api.example.test"},
            {"code": 200, "encrypt": False, "data": {
                "game_list": {"bingo": {"list": {
                    "bingoLh": {"key": "bingoLh", "id": 270048}
                }}}
            }},
            {"code": 200, "encrypt": False, "data": {
                "next": {"nextIssue": "115055012", "totalWin": "-431.5"}
            }},
        )
        client = BetClient(
            "https://web.example.test", {"token": "TOKEN", "uuid": "UUID"}, opener
        )
        self.assertEqual(client.today_profit(), -431.5)
        self.assertTrue(opener.requests[-1].full_url.endswith(
            "/api/v1/member/issueData/270048"
        ))

    def test_live_contract_builds_only_special_code_b(self):
        odds = {f"specialCodeB_guessNumberB_{n}": 48.65 for n in range(1, 50)}
        opener = Opener(
            {"domain": "https://api.example.test"},
            {"code": 200, "encrypt": False, "data": {
                "game_list": {"bingo": {"list": {"bingoLh": {"key": "bingoLh", "id": 270048}}}}
            }},
            {"code": 200, "encrypt": False, "data": {"next": {
                "nextIssue": "115055012", "open_time": 1790610600,
                "status": 1, "game_status": 1,
            }}},
            {"code": 200, "encrypt": False, "data": {
                "number": {"specialCodeB": {"subType": "guessNumberB"}},
                "odds": odds, "user_game_status": 1,
            }},
            {"code": 200, "encrypt": False, "msg": "投注成功", "data": []},
        )
        with tempfile.TemporaryDirectory() as temporary:
            auth = {"token": "TOKEN", "refreshToken": "REFRESH", "uuid": "UUID"}
            client = BetClient("https://web.example.test", auth, opener)
            outcome = AutoBetRunner("https://web.example.test", auth,
                                    Path(temporary) / "state.json", client).run_once(
                                        BetPlan(1, 2, "2", "猴"),
                                        "115055011", "115055011")
        self.assertEqual(outcome.selected, 40)
        posted = json.loads(opener.requests[-1].data)
        self.assertEqual(outcome.bets, tuple(
            (item["number"], item["amount"]) for item in posted["bet_info"]
        ))
        self.assertEqual(posted["game_id"], 270048)
        self.assertTrue(posted["bet_info"])
        self.assertTrue(all(item["group"] == "specialCodeB" for item in posted["bet_info"]))
        self.assertTrue(all(item["subGroup"] == "guessNumberB" for item in posted["bet_info"]))
        self.assertNotIn("2", {item["number"] for item in posted["bet_info"]})

    def test_expired_bet_post_relogs_and_retries_that_exact_post(self):
        odds = {f"specialCodeB_guessNumberB_{n}": 48.65 for n in range(1, 50)}
        opener = Opener(
            {"domain": "https://api.example.test"},
            {"code": 200, "data": {"game_list": {"bingo": {"list": {
                "bingoLh": {"key": "bingoLh", "id": 270048}
            }}}}},
            {"code": 200, "data": {"next": {
                "nextIssue": "115055012", "open_time": 1790610600,
                "status": 1, "game_status": 1,
            }}},
            {"code": 200, "data": {
                "number": {"specialCodeB": {"subType": "guessNumberB"}},
                "odds": odds, "user_game_status": 1,
            }},
            {"code": 4001, "msg": "登录状态已失效"},
            {"code": 200, "msg": "投注成功", "data": []},
        )
        renewed = {"token": "NEW", "refreshToken": "NEW_REFRESH", "uuid": "NEW_UUID"}
        session = Mock()
        session.renew.return_value = renewed
        auth = {"token": "OLD", "refreshToken": "OLD_REFRESH", "uuid": "OLD_UUID"}
        with tempfile.TemporaryDirectory() as temporary:
            client = BetClient(
                "https://web.example.test", auth, opener,
                session=session, stage="自动投注",
            )
            outcome = AutoBetRunner(
                "https://web.example.test", auth,
                Path(temporary) / "state.json", client,
            ).run_once(BetPlan(1, 2, "2", "猴"), "115055011", "115055011")
        self.assertEqual(outcome.message, "投注成功")
        self.assertEqual(
            opener.requests[-2].full_url, opener.requests[-1].full_url
        )
        self.assertEqual(opener.requests[-2].data, opener.requests[-1].data)
        self.assertEqual(opener.requests[-1].get_header("Authorization"), "Bearer NEW")
        session.renew.assert_called_once()


if __name__ == "__main__":
    unittest.main()
