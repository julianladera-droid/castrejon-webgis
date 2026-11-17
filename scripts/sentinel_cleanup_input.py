"""Reject untrusted/stale plan runs before downloading the small plan artifact."""
import json
import os
import re
from collect_sentinel_products import github_get


def validate(run, repository, sha):
    if not (run.get('head_repository', {}).get('full_name') == repository and run.get('head_branch') == 'main'
            and run.get('path') == '.github/workflows/sentinel-cleanup.yml' and run.get('event') == 'workflow_dispatch'
            and run.get('conclusion') == 'success' and run.get('head_sha') == sha):
        raise ValueError('Plan must be a successful main cleanup run at the same code SHA')


if __name__ == '__main__':
    number, digest = os.environ['PLAN_RUN'], os.environ['PLAN_SHA256']
    if not re.fullmatch(r'\d+', number) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Explicit plan run ID and SHA256 required')
    validate(json.loads(github_get('/actions/runs/' + number)), os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA'])
