"""Regression checks for running screenshot OCR safety limits."""

import unittest

from rewards import MAX_RUNNING_DISTANCE_KM, is_valid_running_distance
from walking_ocr import make_recognition_script, parse_running_stats


class RunningOcrSafetyTests(unittest.TestCase):
    def test_extreme_decimal_point_ocr_result_is_not_rewardable(self):
        # A small distance can be misread when the decimal point is missed.
        result = parse_running_stats(
            "Time 50m 55s Distance 416.40 km",
            distance_text="416.40",
            time_text="50m 55s",
        )
        self.assertEqual(result["distance_km"], 416.4)
        self.assertFalse(is_valid_running_distance(result["distance_km"]))

    def test_normal_run_and_safety_boundary_are_accepted(self):
        self.assertTrue(is_valid_running_distance(4.16))
        self.assertTrue(is_valid_running_distance(MAX_RUNNING_DISTANCE_KM))

    def test_values_over_safety_boundary_are_rejected(self):
        self.assertFalse(is_valid_running_distance(MAX_RUNNING_DISTANCE_KM + 0.001))
        self.assertFalse(is_valid_running_distance(float("inf")))
        self.assertFalse(is_valid_running_distance(float("nan")))

    def test_android_ocr_script_keeps_workflow_mode_separate(self):
        solar_script = make_recognition_script("abc", "image/png", "solar")
        running_script = make_recognition_script("abc", "image/png", "running", request_id=7)
        self.assertIn('"solar"', solar_script)
        self.assertIn('"running"', running_script)
        self.assertIn(", 7);", running_script)
        with self.assertRaises(ValueError):
            make_recognition_script("abc", "image/png", "unknown")


if __name__ == "__main__":
    unittest.main()
