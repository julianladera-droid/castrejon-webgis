"""Select a small useful collection by observation, never by backfill run date."""
import json
from pathlib import Path
import re

from sentinel_products import observed_at

CONFIG = Path(__file__).resolve().parents[1] / 'data/sentinel-retention.json'


def policy(path=CONFIG):
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('version') not in (1, 2) or value.get('max_acquisitions') not in (8, 6, 4):
        raise ValueError('Retention must be 8, 6 or 4 acquisitions')
    if type(value.get('max_site_bytes')) is not int or not 0 < value['max_site_bytes'] <= 400_000_000:
        raise ValueError('Invalid site byte budget')
    pins = value.get('pinned_products', [])
    if (not isinstance(pins, list) or len(pins) > 4 or len(set(pins)) != len(pins)
            or any(not isinstance(p, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,150}', p) for p in pins)):
        raise ValueError('At most four explicit product IDs may be pinned')
    if value.get('version') == 2:
        for key in ('site_fixed_bytes', 'estimated_public_bytes', 'max_artifact_bytes',
                    'max_cache_bytes', 'max_release_bytes', 'max_transfer_bytes',
                    'min_free_disk_bytes', 'max_work_bytes', 'max_rss_bytes', 'max_step_seconds'):
            if type(value.get(key)) is not int or value[key] <= 0:
                raise ValueError('Invalid resource budget: ' + key)
        if not .5 <= value.get('target_fraction', 0) <= .9 or type(value.get('previous_generation')) is not bool:
            raise ValueError('Invalid resource margin / previous generation')
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


def retired(entry, ledger):
    p = entry['product']
    return any(t['product']['id'] == p['id'] and
               (t.get('scope') == 'product' or t['product']['fingerprint'] == p['fingerprint'])
               for t in ledger.get('tombstones', []))


def choose(entries, config, ledger=None):
    """Metadata-only admission, after duplicate removal; no package downloads here."""
    contents = {}
    for entry in entries:
        fp = entry['product']['fingerprint']
        old = contents.get(fp)
        # Re-upload/run IDs do not create a new revision or force another download.
        if old is None or (bool(entry.get('path')), rank(entry)) > (bool(old.get('path')), rank(old)):
            contents[fp] = entry
    valid = [e for e in contents.values() if e['product_version'] in (0, 2, 3) and not retired(e, ledger or {})]
    pins = config.get('pinned_products', [])
    pinned = [max((e for e in valid if e['product']['id'] == p), key=rank, default=None) for p in pins]
    if any(p is None for p in pinned):
        raise ValueError('Pinned product is missing, retired or incompatible')
    pin_days = {observed_at(e['product']['datetime']).date() for e in pinned}
    if len(pin_days) != len(pinned):
        raise ValueError('Pinned products must have distinct observation days')
    rest = [e for e in valid if observed_at(e['product']['datetime']).date() not in pin_days]
    levels = [n for n in (8, 6, 4) if n <= config['max_acquisitions']]
    for n in levels:
        result = sorted(pinned + select(rest, 8)[:n-len(pinned)], key=rank, reverse=True)
        public = config.get('site_fixed_bytes', 0) + sum(
            e.get('public_bytes', config.get('estimated_public_bytes', 0)) for e in result)
        transfer = sum(e.get('size_bytes', 100_000_000) for e in result)
        # Selected DN packages have priority over accelerators and optional history.
        fits = (public <= config.get('max_site_bytes', float('inf')) * config.get('target_fraction', 1)
                and public <= config.get('available_upload_bytes', float('inf'))
                and transfer <= config.get('max_transfer_bytes', float('inf')) * config.get('target_fraction', 1)
                and transfer * 4 <= config.get('max_work_bytes', float('inf')) * config.get('target_fraction', 1))
        if fits:
            return result, {'limit': n, 'estimated_site_bytes': public,
                            'estimated_transfer_bytes': transfer, 'experimental': bool(pins),
                            'latest_available_observation': max((e['product']['datetime'] for e in valid), default=None)}
    raise ValueError('Minimum four (or all available) exceed resource budget; preserve current deployment')
