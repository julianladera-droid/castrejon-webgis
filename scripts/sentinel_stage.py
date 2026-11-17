"""Final local references/integrity gate and removal of owned staging temporaries."""
import hashlib
import json
from pathlib import Path
import shutil

from sentinel_resources import disk_guard, tree_bytes
from sentinel_retention import policy


def verify(site, config=None):
    config = config or policy()
    catalog = json.loads((site / 'sentinel/catalog.json').read_text())
    identities = {a['id'] for a in catalog['acquisitions']}
    refs = []
    for a in catalog['acquisitions']:
        for spec in a['indices'].values():
            for name in ('image', 'download'):
                path = (site / spec[name]).resolve()
                if not path.is_relative_to(site.resolve()) or not path.is_file():
                    raise ValueError('Missing index output')
            if hashlib.sha256((site / spec['download']).read_bytes()).hexdigest() != spec['sha256']:
                raise ValueError('Corrupt published index')
        refs.extend([a['parcel_indices'], a['water']['table'], a['water']['zones']])
    for c in catalog['comparisons']:
        if c['a'] not in identities or c['b'] not in identities or c['a'] == c['b']:
            raise ValueError('Comparison references unselected product')
        refs.append(c)
    if len(catalog['comparisons']) > max(0, len(identities)-1):
        raise ValueError('Comparison count exceeds adjacent-pair budget')
    for ref in refs:
        target = (site / ref['path']).resolve()
        if not target.is_relative_to(site.resolve()) or hashlib.sha256(target.read_bytes()).hexdigest() != ref['sha256']:
            raise ValueError('Broken public reference')
    total = tree_bytes(site)
    if total > config['max_site_bytes']:
        raise ValueError('Site exceeds budget; preserve current deployment')
    disk_guard(site, total * 2, config)
    return total


if __name__ == '__main__':
    print('Verified prepared site bytes:', verify(Path('_site')))
    # Only these new workflow staging directories, never user data or remote objects.
    root = Path.cwd().resolve()
    for name in ('sentinel-products', 'sentinel-products-v3'):
        target = (root / name).resolve()
        if target.parent != root or target.is_symlink():
            raise ValueError('Unsafe staging path')
        if target.exists():
            shutil.rmtree(target)
