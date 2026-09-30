import unittest
import wave
from pathlib import Path


class AlertAudioTests(unittest.TestCase):
    def test_packaged_alarm_contains_three_repetitions(self):
        path = Path(__file__).resolve().parents[1] / "assets" / "alarm.wav"
        with wave.open(str(path), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
            self.assertEqual(audio.getnchannels(), 2)
            self.assertEqual(audio.getsampwidth(), 2)
        self.assertGreater(duration, 12.0)
        self.assertLess(duration, 13.0)


if __name__ == "__main__":
    unittest.main()
