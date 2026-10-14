import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from relayforge.adapters import COMMANDS, command, reset_delay, provider_error
from relayforge.cli import init, validate_config
from relayforge.core import Project

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        with contextlib.redirect_stdout(io.StringIO()): init(self.root, 'codex')
        self.p = Project(self.root)
        self.p.config['test_commands'] = [[sys.executable, '-c', 'pass']]
        self.script = self.root / 'fake_agent.py'
        self.script.write_text('''import json,sys,pathlib
prompt=sys.argv[1]
task=json.loads(prompt.split("\\nTask: ")[1].split("\\nImplemented")[0])
report=pathlib.Path(prompt.split("\\nReport: ")[1].split("\\n")[0])
attempt=prompt.split("\\nAttempt: ")[1].split("\\n")[0]
report.write_text(json.dumps(dict(task_id=task['id'],attempt=attempt,status='done',summary='Implemented behavior and verified edge cases',tests=['unit tests passed'],bugs=[])))
''')
        self.p.config['command'] = [sys.executable, str(self.script), '{prompt}']
    def tearDown(self):
        self.p.close(); self.tmp.cleanup()
    def requirements(self, text='- [ ] 1.1 First feature\n- [ ] 2.1 Second feature\n'):
        (self.root / 'REQUIREMENTS.md').write_text(text)
        self.p.import_requirements(self.root / 'REQUIREMENTS.md')
    def append(self, code):
        with self.script.open('a') as stream: stream.write('\n' + code + '\n')
    def test_numeric_order(self):
        self.requirements('- [ ] 1.10 Ten\n- [ ] 1.2 Two\n')
        self.assertEqual(self.p.next_task()['id'], '1.2')
    def test_gate_before_next_group(self):
        self.requirements(); self.assertEqual(self.p.tick(), 'done')
        self.assertEqual(self.p.next_task()['id'], 'TEST-1'); self.p.tick()
        self.assertEqual(self.p.next_task()['id'], '2.1')
    def test_bug_preempts_and_retests(self):
        self.requirements(); self.p.tick(); self.p.tick()
        with self.p.db: id_ = self.p.bug('1.1', 'Regression')
        self.assertEqual(self.p.next_task()['id'], id_); self.p.tick()
        self.assertEqual(self.p.next_task()['id'], 'TEST-1')
    def test_completed_bug_reopens(self):
        self.requirements()
        with self.p.db: id_ = self.p.bug('1.1', 'Regression')
        self.p.tick()
        with self.p.db: self.p.bug('1.1', 'Regression')
        self.assertEqual(self.p.next_task()['id'], id_)
    def test_changes_explicit_immutable_idempotent(self):
        self.requirements(); path = self.root / 'REQUIREMENT_CHANGES.md'
        path.write_text('- [ ] CHG-001 | 1.1 | Approved extension\n')
        self.assertFalse(any(x['kind'] == 'change' for x in self.p.tasks()))
        self.p.import_changes(); self.p.import_changes()
        self.assertEqual(len([x for x in self.p.tasks() if x['kind'] == 'change']), 1)
        path.write_text('- [ ] CHG-001 | 1.1 | Mutated\n')
        with self.assertRaises(ValueError): self.p.import_changes()
    def test_changes_rollback(self):
        self.requirements()
        (self.root / 'REQUIREMENT_CHANGES.md').write_text('- [ ] CHG-001 | 1.1 | Good\n- [ ] CHG-002 | 9.1 | Invalid\n')
        with self.assertRaises(ValueError): self.p.import_changes()
        self.assertFalse(any(x['kind'] == 'change' for x in self.p.tasks()))
    def test_import_idempotence(self):
        self.requirements(); self.p.import_requirements(self.root / 'REQUIREMENTS.md')
        self.assertEqual(len(self.p.tasks()), 2)
    def test_invalid_imports(self):
        for text in ['- [ ] 1.1 A\n- [ ] 1.1 B', '- [x] 1.1 Done', '- [ ] 01.1 Invalid', '- [ ] 1 Parent\n- [ ] 1.1 Child', '- [ ] nope Bad']:
            with self.subTest(text=text):
                with self.assertRaises(ValueError): self.requirements(text)
                self.assertEqual(self.p.tasks(), [])
    def test_existing_requirement_immutable(self):
        self.requirements()
        with self.assertRaises(ValueError): self.requirements('- [ ] 1.1 Changed\n')
    def test_cross_import_parent_overlap(self):
        self.requirements('- [ ] 1.1 First\n')
        with self.assertRaises(ValueError): self.requirements('- [ ] 1.1.1 Overlap\n')
    def test_docs_history(self):
        self.requirements(); self.p.tick()
        self.assertIn('[x] 1.1', (self.root / 'CHECKLIST.md').read_text())
        self.assertIn('Implemented behavior', (self.root / 'CURRENT.md').read_text())
        self.assertIn('done:', (self.root / 'HISTORY.md').read_text())
    def test_restart(self):
        self.requirements(); self.p.tick(); self.p.close(); self.p = Project(self.root)
        self.assertEqual(self.p.next_task()['id'], 'TEST-1')
    def test_interrupted_recovery(self):
        self.requirements()
        with self.p.db: self.p.db.execute("UPDATE tasks SET status='running' WHERE id='1.1'")
        self.assertEqual(self.p.tick(), 'done')
    def test_limit_wait_resume(self):
        self.requirements(); self.script.write_text("import sys; print('usage limit reached; retry-after: 120'); sys.exit(1)")
        self.assertEqual(self.p.tick(), 'limited'); self.assertEqual(self.p.tick(), 'waiting')
        self.assertEqual(self.p.tasks()[0]['attempts'], 0)
        with self.p.db: self.p.set('resume_at', 0)
        self.assertEqual(self.p.tick(), 'limited')
    def test_success_quota_discussion(self):
        self.requirements(); self.append("print('Discuss usage limit behavior')")
        self.assertEqual(self.p.tick(), 'done')
    def test_retry_budget(self):
        self.requirements(); self.p.config['max_attempts'] = 2; self.script.write_text('import sys; sys.exit(1)')
        self.assertEqual(self.p.tick(), 'failed'); self.assertEqual(self.p.tick(), 'failed')
        self.assertEqual(self.p.tick(), 'blocked')
    def test_no_report(self):
        self.requirements(); self.script.write_text('pass'); self.assertEqual(self.p.tick(), 'failed')
    def test_stale_report(self):
        self.requirements(); self.append("v=json.loads(report.read_text()); v['attempt']='stale'; report.write_text(json.dumps(v))")
        self.assertEqual(self.p.tick(), 'failed')
    def test_missing_tests(self):
        self.requirements(); self.append("v=json.loads(report.read_text()); v['tests']=[]; report.write_text(json.dumps(v))")
        self.assertEqual(self.p.tick(), 'failed')
    def test_host_failure_bug(self):
        self.requirements(); self.p.config['test_commands'] = [[sys.executable, '-c', 'raise SystemExit(1)']]
        self.assertEqual(self.p.tick(), 'failed'); self.assertEqual(self.p.next_task()['kind'], 'bug')
    def test_gate_requires_host_tests(self):
        self.requirements(); self.p.tick(); self.p.config['test_commands'] = []
        self.assertEqual(self.p.tick(), 'failed')
    def test_restore_human_file(self):
        self.requirements(); original = (self.root / 'REQUIREMENT_CHANGES.md').read_text()
        self.append("pathlib.Path('REQUIREMENT_CHANGES.md').write_text('malicious')")
        self.assertEqual(self.p.tick(), 'blocked')
        self.assertEqual((self.root / 'REQUIREMENT_CHANGES.md').read_text(), original)
    def test_pause(self):
        self.requirements()
        with self.p.db: self.p.set('paused', 1)
        self.assertEqual(self.p.tick(), 'paused'); self.assertEqual(self.p.tasks()[0]['attempts'], 0)
    def test_lock(self):
        other = Project(self.root)
        try:
            with self.p.lock():
                with self.assertRaises(ValueError): other.tick()
        finally: other.close()
    def test_timeout(self):
        self.requirements(); self.p.config['timeout_seconds'] = 0.1
        self.script.write_text('import time; time.sleep(30)')
        self.assertEqual(self.p.tick(), 'failed'); self.assertEqual(self.p.tasks()[0]['status'], 'pending')
    def test_failed_bug_does_not_spawn_infinite_repairs(self):
        self.requirements(); self.p.config['test_commands'] = [[sys.executable, '-c', 'raise SystemExit(1)']]
        self.p.tick(); self.p.tick(); self.p.tick()
        self.assertEqual(len([x for x in self.p.tasks() if x['kind'] == 'bug']), 1)
    def test_gate_waits_for_blocked_bug(self):
        self.requirements(); self.p.tick(); self.p.tick()
        with self.p.db:
            id_ = self.p.bug('1.1', 'Regression')
            self.p.db.execute("UPDATE tasks SET status='blocked' WHERE id=?", (id_,))
        self.assertIsNone(self.p.next_task())
    def test_invalid_report_object(self):
        self.requirements(); self.append("report.write_text('[]')")
        self.assertEqual(self.p.tick(), 'failed')
    def test_zero_exit_limit_without_report(self):
        self.requirements(); self.script.write_text("print('usage limit reached; retry-after: 60')")
        self.assertEqual(self.p.tick(), 'limited')
    def test_planning_drafts_requirements_without_import(self):
        with self.p.db: self.p.add('PLAN-test', 'Plan a small project', 'plan', '1', priority=0)
        self.append("v=json.loads(report.read_text()); v['requirements']=[{'id':'1.1','title':'Design interfaces'},{'id':'1.2','title':'Implement with acceptance checks'}]; report.write_text(json.dumps(v))")
        self.assertEqual(self.p.tick(), 'done')
        self.assertIn('- [ ] 1.1', (self.root / 'PLANNED_REQUIREMENTS.md').read_text())
        self.assertFalse(any(x['kind'] == 'feature' for x in self.p.tasks()))
    def test_planning_requires_valid_checklist(self):
        with self.p.db: self.p.add('PLAN-test', 'Plan project', 'plan', '1', priority=0)
        self.assertEqual(self.p.tick(), 'failed')
    def test_cli_end_to_end(self):
        (self.root / 'REQUIREMENTS.md').write_text('- [ ] 1.1 Feature\n')
        (self.p.meta / 'config.json').write_text(json.dumps(self.p.config))
        prefix = [sys.executable, '-m', 'relayforge', '--project', str(self.root)]
        for args in [['import'], ['run'], ['status']]:
            result = subprocess.run(prefix + args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(all(t['status'] == 'done' for t in data['tasks']))
        self.assertEqual({t['id'] for t in data['tasks']}, {'1.1', 'TEST-1'})
    def test_structured_reset(self):
        now = datetime(2026, 10, 14, tzinfo=timezone.utc)
        self.assertEqual(reset_delay('{"error":{"reset_at":"2026-10-14T01:00:00Z"}}', 300, now), 3600)
        self.assertEqual(reset_delay('{"error":{"retry_after":42}}', 300, now), 42)
    def test_unknown_bug(self):
        self.requirements()
        with self.assertRaises(ValueError): self.p.bug('9.9', 'Unknown')
    def test_adapters_preserve_prompt(self):
        prompt = 'quotes " $(touch /tmp/no) `echo no`\nnew line'
        for name in COMMANDS: self.assertIn(prompt, command(name, prompt))
    def test_adapter_validation(self):
        for override in ['shell string', [], ['echo', 'no placeholder']]:
            with self.assertRaises((ValueError, KeyError)): command('codex', 'hi', override)
    def test_config_validation(self):
        for key, value in [('timeout_seconds', -1), ('test_commands', ['echo pass']), ('reset_at', '2026-10-15T12:00:00')]:
            config = dict(self.p.config); config[key] = value
            with self.assertRaises(ValueError): validate_config(config)
    def test_provider_error(self):
        self.assertTrue(provider_error('{"is_error":true}')); self.assertFalse(provider_error('{"is_error":false}'))
    def test_reset_signals(self):
        self.assertEqual(reset_delay('retry-after: 10 minutes', 300), 600)
        self.assertEqual(reset_delay('try again in 2 hours', 300), 7200)
        self.assertEqual(reset_delay('unknown', 300), 300)
        self.assertEqual(reset_delay('reset_at: 2026-10-14T01:00:00Z', 300, datetime(2026, 10, 14, tzinfo=timezone.utc)), 3600)

if __name__ == '__main__': unittest.main()
