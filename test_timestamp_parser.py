import unittest
from datetime import datetime

from timestamp_parser import PatternError, compile_pattern


def parse(pattern, name):
    return compile_pattern(pattern).parse(name)


class ParseTest(unittest.TestCase):
    def test_full_timestamp(self):
        self.assertEqual(
            parse("yyyy-mm-dd_HH-mm-ss", "log_2023-01-15_09-30-05.txt"),
            datetime(2023, 1, 15, 9, 30, 5),
        )

    def test_compact_timestamp(self):
        self.assertEqual(
            parse("yyyymmddHHmmss", "IMG20230115093005.jpg"),
            datetime(2023, 1, 15, 9, 30, 5),
        )

    def test_date_only_defaults_to_midnight(self):
        self.assertEqual(parse("yyyy-mm-dd", "note 2024-12-31.md"), datetime(2024, 12, 31))

    def test_pattern_found_anywhere_in_the_name(self):
        self.assertEqual(parse("yyyymmdd", "backup_20200704_final.zip"), datetime(2020, 7, 4))

    def test_day_first_pattern(self):
        self.assertEqual(parse("dd.mm.yyyy", "scan 05.03.1999.pdf"), datetime(1999, 3, 5))

    def test_two_digit_year(self):
        self.assertEqual(parse("yymmdd", "990305_x.doc"), datetime(1999, 3, 5))
        self.assertEqual(parse("yymmdd", "200305_x.doc"), datetime(2020, 3, 5))

    def test_minute_wins_after_the_hour_even_when_time_comes_first(self):
        self.assertEqual(
            parse("HH-mm-ss yyyy-mm-dd", "10-30-00 2020-07-04.txt"),
            datetime(2020, 7, 4, 10, 30),
        )

    def test_impossible_date_is_rejected(self):
        with self.assertRaises(ValueError):
            parse("yyyymmdd", "20231301bad.txt")

    def test_longer_digit_run_does_not_match(self):
        with self.assertRaises(ValueError):
            parse("yyyymmdd", "202301151200.txt")

    def test_no_match(self):
        with self.assertRaises(ValueError):
            parse("yyyy-mm-dd", "holiday.jpg")


class PatternTest(unittest.TestCase):
    def test_year_is_required(self):
        with self.assertRaises(PatternError):
            compile_pattern("dd-mm")

    def test_empty_pattern(self):
        with self.assertRaises(PatternError):
            compile_pattern("   ")

    def test_duplicate_token(self):
        with self.assertRaises(PatternError):
            compile_pattern("yyyy-dd-dd")


if __name__ == "__main__":
    unittest.main()
