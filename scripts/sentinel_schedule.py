"""Local calendar gate: never contacts Copernicus."""
from datetime import date, datetime
import os
from zoneinfo import ZoneInfo


def is_due(day: date) -> bool:
    if 2 <= day.month <= 9:
        return (day - date(day.year, 2, 1)).days % 3 == 0
    cycle_year = day.year - 1 if day.month == 1 else day.year
    return (day - date(cycle_year, 10, 1)).days % 15 == 0


if __name__ == '__main__':
    today = datetime.now(ZoneInfo('Europe/Madrid')).date()
    due = os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' or is_due(today)
    value = str(due).lower()
    print(f'{today}: run={value}')
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f'run={value}\n')
