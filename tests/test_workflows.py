from fnmatch import fnmatchcase
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load((ROOT / '.github/workflows' / name).read_text(encoding='utf-8'), Loader=yaml.BaseLoader)


def test_inbox_only_push_does_not_trigger_report_publication_or_notification():
    publish = workflow('daily.yml')
    paths = ['data/inbox/2026-09-04/abcd/feed.xml', 'data/inbox/2026-09-04/abcd/manifest.json']
    assert publish['on']['push']['branches'] == ['main']
    assert not any(fnmatchcase(path, pattern) for path in paths for pattern in publish['on']['push']['paths'])
    assert publish['jobs']['deploy-notify']['if'] == "github.ref == 'refs/heads/main'"


def test_capture_schedule_scope_and_generated_file_staging():
    job = workflow('capture-rss.yml')
    assert set(job['on']) == {'schedule', 'workflow_dispatch'}
    assert job['on']['schedule'] == [{'cron': '15 11 * * 1-5', 'timezone': 'Europe/Warsaw'}]
    capture = job['jobs']['capture']
    assert capture['if'] == "github.ref == 'refs/heads/main'"
    assert capture['permissions'] == {'contents': 'write'}
    commands = '\n'.join(step.get('run', '') for step in capture['steps'])
    assert 'git add -- "$INPUT_DIR/feed.xml" "$INPUT_DIR/manifest.json"' in commands
    for prohibited in ['src.finalize_run', 'src.notify', 'data/state.json', 'git add .', 'git add -A', '--force']:
        assert prohibited not in commands


def test_branch_ci_has_no_publication_permissions_or_steps():
    ci = workflow('validate-offline.yml')
    assert 'fix/offline-arxiv-input' in ci['on']['push']['branches']
    assert ci['permissions'] == {'contents': 'read'}
    steps = ci['jobs']['validate']['steps']
    commands = '\n'.join(step.get('run', '') for step in steps)
    assert 'pytest -q' in commands
    assert '--inbox-dir tmp/ci-inbox' in commands
    assert "patch('requests.sessions.Session.request'" in commands
    for prohibited in ['src.notify', 'src.finalize_run', 'git commit', 'git push']:
        assert prohibited not in commands
    assert not any('pages' in step.get('uses', '') for step in steps)
    checkout = next(step for step in steps if step.get('uses', '').startswith('actions/checkout@'))
    assert checkout['with']['persist-credentials'] == 'false'
