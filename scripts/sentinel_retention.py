"""Select a small useful collection by observation, never by backfill run date."""
import json
from pathlib import Path
import re

from sentinel_products import observed_at

CONFIG = Path(__file__).resolve().parents[1] / 'data/sentinel-retention.json'


def policy(path=CONFIG):
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('version') != 1 or value.get('max_acquisitions') not in (8, 6, 4):
        raise ValueError('Retention must be 8, 6 or 4 acquisitions')
    if type(value.get('max_site_bytes')) is not int or not 0 < value['max_site_bytes'] <= 400_000_000:
        raise ValueError('Invalid site byte budget')
    return value


def rank(entry):
    record = entry['product']
    baseline = re.search(r'_N(\d{4})_', record['id'])
    # Processing time breaks ties only after observation, baseline, schema and ID.
    return (observed_at(record['datetime']), int(baseline[1]) if baseline else -1,
            entry['product_version'], record['id'], entry.get('processed_at', ''),
            record['fingerprint'])


def select(entries, limit):
    if limit not in (8, 6, 4):
        raise ValueError('Retention must be 8, 6 or 4 acquisitions')
    days = {}
    for entry in entries:
        day = observed_at(entry['product']['datetime']).date()
        if day not in days or rank(entry) > rank(days[day]):
            days[day] = entry
    return sorted(days.values(), key=rank, reverse=True)[:limit]
