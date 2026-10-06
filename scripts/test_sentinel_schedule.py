from datetime import date, timedelta
import unittest
from sentinel_schedule import is_due


class ScheduleTests(unittest.TestCase):
    def test_three_day_intervals_across_months_and_leap_day(self):
        for year in (2026, 2028):
            start, end = date(year, 2, 1), date(year, 9, 30)
            days = [start + timedelta(days=i) for i in range((end-start).days+1)]
            due = [day for day in days if is_due(day)]
            self.assertEqual(due[0], start)
            self.assertTrue(all((b-a).days == 3 for a, b in zip(due, due[1:])))
            self.assertLessEqual((end-due[-1]).days, 2)

    def test_rest_of_year_only_fifteenth(self):
        for month in (1, 10, 11, 12):
            for day in range(1, 29):
                self.assertEqual(is_due(date(2026, month, day)), day == 15)


if __name__ == '__main__':
    unittest.main()
