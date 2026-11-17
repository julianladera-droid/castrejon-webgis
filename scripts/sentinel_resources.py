"""Local admission checks and measured, bounded Linux workflow steps (stdlib only)."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from sentinel_retention import policy


def disk_guard(path, required=0, config=None):
    config = config or policy()
    path = Path(path).resolve()
    while not path.exists():
        path = path.parent
    free = shutil.disk_usage(path).free
    if free < required + config.get('min_free_disk_bytes', 0):
        raise ValueError(f'Insufficient disk: {free} free, {required} required plus reserve; preserve current deployment')
    return free


def tree_bytes(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file())


def run_step(label, command, config=None):
    """Linux /proc counts the whole process group; sample peaks are lower bounds.

    RLIMIT_AS is deliberately not used: GDAL mmap reservations are not RSS.
    A failed child or resource limit always blocks subsequent upload/deployment.
    """
    config = config or policy()
    disk_guard('.', config['max_work_bytes'], config)
    start = time.monotonic()
    peak_rss = peak_disk = 0
    proc = subprocess.Popen(command, start_new_session=True)
    reason = None
    try:
        while proc.poll() is None:
            rss = 0
            for stat in Path('/proc').glob('[0-9]*/stat'):
                try:
                    # comm may contain spaces; fields after the closing ')' begin at #3.
                    parts = stat.read_text().rsplit(')', 1)[1].split()
                    if int(parts[2]) == proc.pid:
                        rss += int(parts[21]) * os.sysconf('SC_PAGE_SIZE')
                except (OSError, ValueError, IndexError):
                    continue
            used = sum(tree_bytes(p) for p in ('sentinel-output', 'sentinel-products', 'sentinel-products-v3', '_site'))
            peak_rss, peak_disk = max(rss, peak_rss), max(used, peak_disk)
            if rss > config['max_rss_bytes'] or used > config['max_work_bytes'] or time.monotonic()-start > config['max_step_seconds']:
                reason = 'memory, work disk or time budget exceeded'
                break
            disk_guard('.', config=config)
            time.sleep(.5)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        result = proc.wait()
        report = {'label': label, 'seconds': round(time.monotonic()-start, 3),
                  'sampled_peak_rss_bytes': peak_rss, 'sampled_peak_work_bytes': peak_disk,
                  'exit_code': result, 'stopped': reason}
        with Path('sentinel-metrics.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(report) + '\n')
        print(json.dumps(report))
    if result or reason:
        raise ValueError('Resource/process failure; preserve current deployment')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command:
        run_step(args.label, args.command)
    else:
        disk_guard('.', policy()['max_work_bytes'])
