import tempfile
import unittest
import io
import json
from pathlib import Path
from unittest.mock import Mock

from bet_client import (
    AutoBetRunner, BetClient, BetError, BetPlan, issue_distance, selected_numbers,
    zodiac_numbers,
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
        outcome = runner.run_once(self.plan, "115055011")
        self.assertEqual(outcome.total_points, 120)
        self.assertEqual(outcome.completed, 1)
        self.assertIsNone(runner.run_once(self.plan))
        self.client.submit.assert_called_once()

    def test_issue_is_reserved_even_when_submit_fails(self):
        self.client.submit.side_effect = BetError("积分不足,投注失败")
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        with self.assertRaisesRegex(BetError, "积分不足"):
            runner.run_once(self.plan, "115055011")
        self.client.submit.reset_mock()
        self.client.submit.side_effect = None
        self.assertIsNone(runner.run_once(self.plan))
        self.client.submit.assert_not_called()

    def test_no_zero_trigger_means_no_bet(self):
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        self.assertIsNone(runner.run_once(self.plan))
        self.client.game_id.assert_not_called()

    def test_exactly_n_consecutive_slots_then_waits_for_next_zero(self):
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        for index, issue in enumerate(("115055012", "115055013"), 1):
            self.client.next_issue.return_value = (issue, 1790610600 + index * 300)
            outcome = runner.run_once(self.plan, "115055011" if index == 1 else None)
            self.assertEqual(outcome.completed, index)
        self.client.next_issue.return_value = ("115055014", 1790611500)
        self.assertIsNone(runner.run_once(self.plan, "115055011"))
        self.assertEqual(self.client.submit.call_count, 2)

    def test_rejected_period_still_consumes_one_of_n_slots(self):
        self.client.submit.side_effect = BetError("积分不足,投注失败")
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        with self.assertRaises(BetError):
            runner.run_once(self.plan, "115055011")
        self.client.submit.side_effect = None
        self.client.next_issue.return_value = ("115055013", 1790610900)
        outcome = runner.run_once(self.plan)
        self.assertEqual(outcome.completed, 2)
        self.client.next_issue.return_value = ("115055014", 1790611200)
        self.assertIsNone(runner.run_once(self.plan))

    def test_start_offset_selects_the_requested_issue_window(self):
        plan = BetPlan(3, 3, "2", "猴", start_offset=2)
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        self.client.next_issue.return_value = ("115055012", 1790610600)
        self.assertIsNone(runner.run_once(plan, "115055011"))
        self.client.submit.assert_not_called()
        for expected, issue in enumerate(("115055013", "115055014", "115055015"), 1):
            self.client.next_issue.return_value = (issue, 1790610600 + expected * 300)
            outcome = runner.run_once(plan)
            self.assertEqual(outcome.completed, expected)
        self.client.next_issue.return_value = ("115055016", 1790611800)
        self.assertIsNone(runner.run_once(plan))
        self.assertEqual(self.client.submit.call_count, 3)

    def test_issue_distance_handles_999_to_001_boundary(self):
        self.assertEqual(issue_distance("115054999", "115055001"), 1)
        self.assertEqual(issue_distance("115054998", "115055002"), 3)

    def test_new_zero_restarts_an_active_campaign_and_discards_old_remainder(self):
        plan = BetPlan(6, 3, "2", "猴", start_offset=2)  # delay one issue
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        self.client.next_issue.return_value = ("115055120", 1790610600)
        self.assertIsNone(runner.run_once(plan, "115055119"))
        for issue in ("115055121", "115055122", "115055123"):
            self.client.next_issue.return_value = (issue, 1790610600)
            self.assertIsNotNone(runner.run_once(plan))
        # Result 123 is another zero: old planned 124 is cancelled, and the
        # new delay skips 124 before the new campaign starts at 125.
        self.client.next_issue.return_value = ("115055124", 1790610600)
        self.assertIsNone(runner.run_once(plan, "115055123"))
        self.client.next_issue.return_value = ("115055125", 1790610600)
        outcome = runner.run_once(plan)
        self.assertEqual(outcome.completed, 1)
        submitted_issues = [
            call.args[0] for call in self.client.submit.call_args_list
        ]
        self.assertEqual(len(submitted_issues), 4)

    def test_each_period_uses_its_own_points_schedule(self):
        plan = BetPlan(3, 1, "2", "猴", 1, (1, 2, 5))
        runner = AutoBetRunner("https://web.example.test", {}, self.state, self.client)
        observed = []
        for index, issue in enumerate(("115055120", "115055121", "115055122"), 1):
            self.client.next_issue.return_value = (issue, 1790610600)
            outcome = runner.run_once(plan, "115055119" if index == 1 else None)
            used_plan = self.client.build_payload.call_args.args[1]
            observed.append((used_plan.points, outcome.points, outcome.total_points))
        self.assertEqual(observed, [(1, 1, 40), (2, 2, 80), (5, 5, 200)])


class ClientContractTests(unittest.TestCase):
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
                                        BetPlan(1, 2, "2", "猴"), "115055011")
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


if __name__ == "__main__":
    unittest.main()
