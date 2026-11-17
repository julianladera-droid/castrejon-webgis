"""Bound upcoming Actions storage independently of Pages; no remote mutation."""
import argparse
import os
from pathlib import Path
from collect_sentinel_products import github_items
from sentinel_resources import tree_bytes, disk_guard
from sentinel_retention import policy


def admit(current, addition, budget, service):
    if current + addition > budget:
        raise ValueError(f'{service}: {current} + {addition} exceeds {budget}; review explicit cleanup, preserve current deployment')


def check(folder, cache=False):
    config = policy()
    addition = tree_bytes(folder) + 1_000_000  # conservative ZIP/tar and metadata allowance
    disk_guard(folder, addition * 2, config)
    artifacts = list(github_items('/actions/artifacts?per_page=100', 'artifacts'))
    total = sum(a['size_in_bytes'] for a in artifacts if not a['expired'])
    admit(total, addition, config['max_artifact_bytes'], 'Actions artifacts (all repository contents)')
    if cache:
        caches = list(github_items('/actions/caches?per_page=100', 'actions_caches'))
        allowed = sum(c['size_in_bytes'] for c in caches) + addition <= config['max_cache_bytes']
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
                output.write(f'cache_allowed={str(allowed).lower()}\n')
        print('Cache save admitted:', allowed)
    print(f'Actions artifact bytes before upload: {total}; admission allowance: {addition}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--cache', action='store_true')
    args = parser.parse_args()
    check(args.folder, args.cache)
