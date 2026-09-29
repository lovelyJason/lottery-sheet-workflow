import unittest
from datetime import date

from balls import ball_color, is_hot, number_zodiac, parse_numbers


class BallTests(unittest.TestCase):
    def test_wave_colors(self):
        self.assertEqual(ball_color(45), "red")
        self.assertEqual(ball_color(41), "blue")
        self.assertEqual(ball_color(43), "green")
        self.assertEqual(ball_color(3), "blue")

    def test_double_and_big_are_hot(self):
        self.assertTrue(is_hot("双"))
        self.assertTrue(is_hot("大"))
        self.assertFalse(is_hot("单"))
        self.assertFalse(is_hot("小"))

    def test_2026_horse_year_matches_the_results_board(self):
        day = date(2026, 9, 28)
        expected = {45: "狗", 7: "鼠", 13: "马", 9: "狗", 37: "马", 23: "猴", 6: "牛"}
        for number, animal in expected.items():
            self.assertEqual(number_zodiac(number, day), animal)

    def test_parse_numbers(self):
        self.assertEqual(parse_numbers("41,40,32,39,10,35"), [41, 40, 32, 39, 10, 35])
        self.assertEqual(parse_numbers("1,50,x"), [1])
