"""Exercise the real audit CLI with local API fixtures and committed evidence."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]


class ReceiptEnforcement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'scripts').mkdir()
        shutil.copyfile(ROOT / 'scripts/merge-hygiene-audit.py', self.root / 'scripts/audit.py')
        self.now = datetime.now(timezone.utc) - timedelta(minutes=5)
        self.merged = self.now - timedelta(days=3)
        self.fixture = json.loads((ROOT / 'tests/fixtures/merge-hygiene/approved.json').read_text())
        # Initial and refetched PR responses must include stable head/base refs.
        self.fixture['pr']['base'] = {'sha': 'c'*40}
        self.fixture['files'] = [{'filename': 'scripts/x.py', 'status': 'modified'}]
        self.fixture['pr'].update(merged_at=self.merged.isoformat(), updated_at=self.merged.isoformat())
        for row in self.fixture['reviews']:
            row['submitted_at'] = (self.merged - timedelta(minutes=3)).isoformat()
        for row in self.fixture['checks']:
            row['started_at'] = (self.merged - timedelta(minutes=2)).isoformat()
            row['completed_at'] = (self.merged - timedelta(minutes=1)).isoformat()
        for row in self.fixture['statuses']:
            row['created_at'] = (self.merged - timedelta(minutes=1)).isoformat()
        self.anchor = dict(number=71, state='closed', merged_at=(self.merged - timedelta(seconds=1)).isoformat(),
                           base={'repo': {'full_name': 'onesyue/yueto-ci'}})
        self.exceptions = {'schema': 1, 'exceptions': []}
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        gh = self.bin / 'gh'
        gh.write_text(f'''#!{sys.executable}
import json,sys
from pathlib import Path
x=json.loads((Path(__file__).parent.parent/'api.json').read_text())
e=sys.argv[2]
if x.get('unavailable'): raise SystemExit(1)
if e=='repos/onesyue/yueto-ci/pulls/71': result=x['anchor']
elif '/pulls?' in e: result=[x['pr']]
elif '/reviews?' in e: result=x['reviews']
elif '/compare/' in e: result={{'files':x['files'], 'total_commits':1}}
elif '/check-runs?' in e: result={{'check_runs':x['checks']}}
elif '/statuses?' in e: result=x['statuses']
elif e.endswith('/pulls/203'): result=x['pr']
else: raise SystemExit(1)
if x.get('new_rerun') and '/check-runs?' in e:
 from datetime import datetime,timezone
 old=x['checks'][0]
 result['check_runs'].append(old | {{'id': 2, 'created_at': datetime.now(timezone.utc).isoformat(),
                                    'status': 'queued', 'completed_at': None}})
if x.get('new_status') and '/statuses?' in e:
 from datetime import datetime,timezone
 result.append(x['statuses'][0] | {{'id': 2, 'created_at': datetime.now(timezone.utc).isoformat(),
                                  'state': 'failure'}})
print(json.dumps(result))
''')
        gh.chmod(0o755)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Policy fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')

    def git(self, *args):
        subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)

    def run_cli(self, expected, *args):
        (self.root / 'api.json').write_text(json.dumps(self.fixture | {'anchor': self.anchor}))
        (self.root / 'merge-hygiene-exceptions.json').write_text(json.dumps(self.exceptions))
        env = os.environ | {'PATH': str(self.bin) + os.pathsep + os.environ['PATH']}
        result = subprocess.run([sys.executable, str(self.root / 'scripts/audit.py'),
                                 '--repos', 'yueops', '--hours', '1', '--format', 'json', *args],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def add_receipt(self, backfilled=True):
        sha = self.fixture['pr']['head']['sha']
        when = (self.merged - timedelta(minutes=1)).isoformat()
        value = dict(schema=1, repo='yueops', pr=203, head=sha, backfilled=backfilled,
                     review=dict(tool='codex', verdict='approve', reviewed_head=sha, artifact='review.md',
                                 reviewer='codex', reviewed_at=when),
                     parity=dict(result='pass', head=sha, command='make test', log_sha256='a'*64,
                                 ran_at=when, runner='box'))
        self.receipt = self.root / 'merge-receipts/yueops/203.json'
        self.receipt.parent.mkdir(parents=True, exist_ok=True)
        self.receipt.write_text(json.dumps(value))
        (self.root / 'review.md').write_text('Independent Codex fixture review: approve')
        self.git('add', 'merge-receipts/yueops/203.json', 'review.md')
        self.git('commit', '-qm', 'Fixture evidence')

    def register_exception(self):
        self.exceptions['exceptions'] = [dict(repo='yueops', pr=203, reason='Historical evidence absent',
                                               approver='owner')]

    def test_green_hosted_checks_still_require_receipt_and_do_not_age_out(self):
        data = self.run_cli(1)
        self.assertEqual(data['findings'][0]['findings'], ['required_merge_receipt_missing'])
        self.register_exception()
        self.assertIsNone(self.run_cli(1)['findings'][0]['exception'])
        self.add_receipt()
        self.run_cli(0)
        self.receipt.unlink()  # Real missing-object mutation must turn green into red.
        self.run_cli(1)

    def test_valid_receipt_never_suppresses_red_pending_or_unknown(self):
        self.add_receipt()
        self.register_exception()
        original = self.fixture['checks'][0].copy()
        for change in ({'conclusion': 'failure'}, {'status': 'queued', 'completed_at': None},
                       {'started_at': None, 'completed_at': None}):
            with self.subTest(change=change):
                self.fixture['checks'][0] = original | change
                row = self.run_cli(1)['findings'][0]
                self.assertIsNone(row['exception'])
                self.assertTrue(any(r.startswith('check_') for r in row['findings']))

    def test_boundary_and_historical_exception(self):
        # Include the historical PR via a wider lookback; activation itself is grandfathered.
        self.anchor['merged_at'] = self.merged.isoformat()
        self.fixture['reviews'] = []
        self.register_exception()
        self.assertIsNotNone(self.run_cli(0, '--hours', '100')['findings'][0]['exception'])
        self.anchor['merged_at'] = (self.merged - timedelta(microseconds=1)).isoformat()
        self.run_cli(1)

    def test_unmerged_activation_and_unavailable_anchor(self):
        self.anchor.update(state='open', merged_at=None)
        self.run_cli(0, '--hours', '100')
        self.anchor['state'] = 'closed'
        self.assertFalse(self.run_cli(2)['complete'])
        self.fixture['unavailable'] = True
        self.assertFalse(self.run_cli(2)['complete'])

    def test_wrong_head_or_uncommitted_review_is_incomplete(self):
        self.add_receipt()
        self.fixture['pr']['head']['sha'] = 'b'*40
        self.run_cli(2)
        self.fixture['pr']['head']['sha'] = 'a'*40
        (self.root / 'review.md').write_text('uncommitted approval')
        self.run_cli(2)

    def test_premerge_requires_evidence_even_before_activation(self):
        self.anchor.update(state='open', merged_at=None)
        self.fixture['pr'].update(state='open', merged_at=None)
        self.register_exception()
        self.run_cli(1, '--premerge', 'yueops', '203')
        self.add_receipt(backfilled=False)
        self.run_cli(0, '--premerge', 'yueops', '203')
        self.fixture['checks'][0]['status'] = 'queued'
        self.run_cli(1, '--premerge', 'yueops', '203')

    def test_premerge_rejects_backfill_and_changed_head(self):
        self.anchor.update(state='open', merged_at=None)
        self.fixture['pr'].update(state='open', merged_at=None)
        self.add_receipt()
        self.run_cli(2, '--premerge', 'yueops', '203')
        self.fixture['pr']['head']['sha'] = 'b'*40
        self.run_cli(2, '--premerge', 'yueops', '203')

    def test_premerge_observes_checks_created_after_audit_started(self):
        self.anchor.update(state='open', merged_at=None)
        self.fixture['pr'].update(state='open', merged_at=None)
        self.add_receipt(backfilled=False)
        for key in ('new_rerun', 'new_status'):
            with self.subTest(key=key):
                self.fixture[key] = True
                self.run_cli(1, '--premerge', 'yueops', '203')
                del self.fixture[key]
