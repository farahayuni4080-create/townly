"""Pure unit tests for solar OCR interpretation and claim validation.

The atomic duplicate/ledger guarantees are enforced by the Supabase RPC in
supabase_solar_claims_migration.sql and require the configured database to test.
"""

import unittest
from datetime import date
from decimal import Decimal

from solar_claims import (
    calculate_solar_points,
    has_successful_claim,
    is_suspicious,
    parse_solar_reading,
    validate_claim,
)


class SolarClaimRulesTests(unittest.TestCase):
    def test_solar_rate_is_half_a_point_per_kwh_with_whole_point_rounding(self):
        self.assertEqual(calculate_solar_points(413), 207)
        self.assertEqual(calculate_solar_points(500), 250)

    def test_500_kwh_monthly_report_is_250_points(self):
        result = parse_solar_reading(
            "April 2026 Monthly Solar Generation: 500 kWh"
        )
        self.assertEqual(result["kwh"], Decimal("500"))
        amount, points, issue = validate_claim(
            result["kwh"], result["month"], result["year"], today=date(2026, 5, 1)
        )
        self.assertEqual((amount, points, issue), (Decimal("500"), 250, None))

    def test_inverter_month_view_selects_pv_production_not_consumption(self):
        # OCR reading order varies, so include the total and both PV subtotals.
        result = parse_solar_reading(
            "Day Week Month Year Total\n10.2026\n"
            "PV production (DC)\n413.00\nkWh\n44%\n"
            "Self-consum ption\n185.70 kWh\n56%\n"
            "Grid feed-in\n227.30 kWh\n"
            "Consumption\n714.00 kWh\nSelf-sufficiency\n185.70 kWh\n"
            "Grid supplied\n528.30 kWh"
        )
        self.assertEqual(result["kwh"], Decimal("413.00"))
        self.assertEqual((result["month"], result["year"]), (10, 2026))

    def test_lifetime_reading_is_not_used_as_monthly_generation(self):
        result = parse_solar_reading("Lifetime generation total: 12500 kWh")
        self.assertIn("error", result)

    def test_unreadable_image_text_does_not_produce_a_claim_value(self):
        result = parse_solar_reading("SOLAR ENERGY REPORT")
        self.assertIn("error", result)
        amount, points, issue = validate_claim(None, 4, 2026, today=date(2026, 5, 1))
        self.assertIsNone(amount)
        self.assertIsNone(points)
        self.assertIsNotNone(issue)

    def test_zero_or_invalid_readings_are_rejected(self):
        for reading in ("0", "not-a-number", "NaN", "Infinity"):
            amount, points, issue = validate_claim(
                reading, 4, 2026, today=date(2026, 5, 1)
            )
            self.assertIsNone(amount)
            self.assertIsNone(points)
            self.assertIsNotNone(issue)

    def test_claim_period_validation_rejects_future_and_invalid_month(self):
        self.assertIsNotNone(
            validate_claim(500, 13, 2026, today=date(2026, 5, 1))[2]
        )
        self.assertIsNotNone(
            validate_claim(500, 6, 2026, today=date(2026, 5, 1))[2]
        )

    def test_duplicate_check_only_counts_successful_claims(self):
        history = [
            {"claim_month": 4, "claim_year": 2026, "claim_status": "flagged_review"},
            {"claim_month": 3, "claim_year": 2026, "claim_status": "awarded"},
        ]
        self.assertFalse(has_successful_claim(history, 4, 2026))
        self.assertTrue(has_successful_claim(history, 3, 2026))
        self.assertFalse(has_successful_claim(history, 5, 2026))

    def test_unusually_large_reading_is_flagged_not_rejected(self):
        amount, points, issue = validate_claim(
            50001, 4, 2026, today=date(2026, 5, 1)
        )
        self.assertEqual(amount, Decimal("50001"))
        self.assertEqual(points, 25001)
        self.assertIsNone(issue)
        self.assertTrue(is_suspicious(amount))

    def test_new_month_can_be_claimed_after_an_earlier_award(self):
        history = [
            {"claim_month": 4, "claim_year": 2026, "claim_status": "awarded"}
        ]
        self.assertFalse(has_successful_claim(history, 5, 2026))
        self.assertEqual(
            validate_claim(500, 5, 2026, today=date(2026, 5, 1))[1], 250
        )


if __name__ == "__main__":
    unittest.main()
