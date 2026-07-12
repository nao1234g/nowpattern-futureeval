from __future__ import annotations

import unittest

from forecast_parsing import extract_last_probability


class ForecastParsingTests(unittest.TestCase):
    def test_extracts_last_explicit_probability(self) -> None:
        text = "Base rate Probability: 30%\nFinal answer Probability: 64.5%"
        self.assertEqual(extract_last_probability(text), 0.645)

    def test_clamps_platform_boundaries(self) -> None:
        self.assertEqual(extract_last_probability("Probability: 0%"), 0.01)
        self.assertEqual(extract_last_probability("Probability: 100%"), 0.99)

    def test_rejects_missing_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "was not found"):
            extract_last_probability("The chance is probably moderate.")

    def test_rejects_out_of_range_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            extract_last_probability("Probability: 101%")


if __name__ == "__main__":
    unittest.main()
