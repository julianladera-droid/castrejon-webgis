from datetime import date, timedelta
from pathlib import Path
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

    def test_fifteen_day_intervals_across_months_and_new_year(self):
        for year in (2025, 2026, 2027, 2028):
            start, end = date(year, 10, 1), date(year + 1, 1, 31)
            days = [start + timedelta(days=i) for i in range((end-start).days+1)]
            due = [day for day in days if is_due(day)]
            expected = [(10, 1), (10, 16), (10, 31), (11, 15), (11, 30),
                        (12, 15), (12, 30), (1, 14), (1, 29)]
            self.assertEqual([(day.month, day.day) for day in due], expected)
            self.assertTrue(all((b-a).days == 15 for a, b in zip(due, due[1:])))
            self.assertTrue(is_due(date(year + 1, 2, 1)))

    def test_workflow_checks_every_day(self):
        workflow = Path(__file__).resolve().parents[1] / '.github/workflows/sentinel.yml'
        cron_lines = [line.strip() for line in workflow.read_text().splitlines()
                      if line.strip().startswith('- cron:')]
        self.assertEqual(cron_lines, ["- cron: '30 5 * * *'"])


if __name__ == '__main__':
    unittest.main()
