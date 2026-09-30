import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from resource_status import DANGER, SAFE, WARN, traffic_color


class TrafficColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_usage_turns_red_when_it_fills_up(self):
        self.assertEqual(traffic_color(10, healthy_when_high=False), SAFE)
        self.assertEqual(traffic_color(60, healthy_when_high=False), WARN)
        self.assertEqual(traffic_color(90, healthy_when_high=False), DANGER)

    def test_remaining_turns_red_when_it_runs_out(self):
        self.assertEqual(traffic_color(90, healthy_when_high=True), SAFE)
        self.assertEqual(traffic_color(40, healthy_when_high=True), WARN)
        self.assertEqual(traffic_color(10, healthy_when_high=True), DANGER)


if __name__ == "__main__":
    unittest.main()
