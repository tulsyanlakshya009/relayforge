import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import time
import uuid
from .adapters import command, LIMIT, provider_error, reset_delay

ID = re.compile(r"^[1-9]\d*(?:\.[1-9]\d*)*$")
LINE = re.compile(r"^- \[([ xX])\] (\d+(?:\.\d+)*)\s+(.+)$")

MASTER = """You are executing one bounded RelayForge work item.
Use the project's existing conventions. Inspect relevant code before editing.
Follow the approved requirement and acceptance criteria, design before implementation,
make the smallest coherent change, and add meaningful regression and edge-case tests.
Inspect the workspace for partial work from interrupted attempts; reuse it when correct.
Never change REQUIREMENT_CHANGES.md, REQUIREMENTS.md, config.json, state.sqlite3,
CHECKLIST.md, CURRENT.md or HISTORY.md. Never publish, deploy, or push.
Update SYSTEM_DESIGN.md when architecture changes. Record discovered bugs in your report.
For a test gate, exercise every implemented feature in that top-level requirement,
including unit, integration, boundary, invalid-input and regression cases as applicable.
Do not claim completion if blocked, tools fail, or tests fail. State limitations honestly.
Write the report to the exact absolute JSON path below. Required object:
{"task_id":"exact id", "attempt":"exact nonce", "status":"done|blocked",
 "summary":"implemented behavior, usage, tests and limitations",
 "tests":["actual test commands and outcomes"],
 "bugs":[{"target":"numeric requirement id", "title":"specific defect"}]}
A successful process exit alone does not complete the task. Do only this work item.
"""


def atomic(path, content):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with tmp.open("w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def numeric(value):
    return tuple(int(x) for x in value.split("."))


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.meta = self.root / ".relayforge"
        if not (self.meta / "config.json").exists():
            raise ValueError("Run relayforge init first")
        self.config = json.loads((self.meta / "config.json").read_text())
        self.db = sqlite3.connect(self.meta / "state.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, target TEXT NOT NULL, kind TEXT NOT NULL,
          title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          priority INTEGER NOT NULL DEFAULT 100, attempts INTEGER NOT NULL DEFAULT 0,
          summary TEXT NOT NULL DEFAULT '', deps TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, at REAL, task TEXT, action TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
        ''')

    def close(self):
        self.db.close()

    @contextlib.contextmanager
    def lock(self):
        with (self.meta / "runner.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Another runner is active for this project")
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def event(self, task, action, detail=""):
        self.db.execute("INSERT INTO events(at,task,action,detail) VALUES(?,?,?,?)", (time.time(), task, action, detail))

    def get(self, key, default=""):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, str(value)))

    def tasks(self):
        return [dict(x) for x in self.db.execute("SELECT * FROM tasks")]

    def add(self, id_, title, kind="feature", target=None, priority=100, deps=None):
        target = target or id_
        if not ID.fullmatch(target) or not title.strip() or len(title) > 16000 or '\n' in title:
            raise ValueError("Use a positive dotted numeric target and a one-line title")
        if kind == "feature" and not ID.fullmatch(id_):
            raise ValueError("Invalid requirement ID")
        self.db.execute("INSERT INTO tasks(id,target,kind,title,priority,deps) VALUES(?,?,?,?,?,?)", (id_, target, kind, title, priority, json.dumps(deps or [])))
        self.event(id_, "added", title)

    def import_requirements(self, path):
        text = Path(path).read_text()
        parsed = []
        for line in text.splitlines():
            match = LINE.match(line)
            if match:
                if match[1] != ' ':
                    raise ValueError("Imports must be unchecked; only verified runs mark completion")
                parsed.append((match[2], match[3]))
            elif re.match(r"^- \[", line):
                raise ValueError("Malformed requirement checkbox: " + line)
        if not parsed:
            raise ValueError("No requirements found; use - [ ] 1.1 Title")
        ids = [x[0] for x in parsed]
        if len(set(ids)) != len(ids) or any(not ID.fullmatch(x) for x in ids):
            raise ValueError("Duplicate or invalid requirement IDs")
        if any(any(other.startswith(x + '.') for other in ids) for x in ids):
            raise ValueError("Use leaf checkbox IDs; top-level groups are Markdown headings")
        with self.db:
            for id_, title in parsed:
                existing = self.db.execute("SELECT * FROM tasks WHERE id=?", (id_,)).fetchone()
                if existing:
                    if existing['title'] != title:
                        raise ValueError("Existing requirement changed; use a human change entry")
                else:
                    if any(t['kind'] == 'feature' and (t['id'].startswith(id_ + '.') or id_.startswith(t['id'] + '.')) for t in self.tasks()):
                        raise ValueError("Requirement IDs cannot overlap an existing parent/child")
                    self.add(id_, title)
                    self.invalidate(id_)
            self.set("requirements_hash", hashlib.sha256(text.encode()).hexdigest())
        self.render()

    def import_changes(self):
        """Explicit human action; runner never auto-ingests this file."""
        path = self.root / "REQUIREMENT_CHANGES.md"
        text = path.read_text()
        entries = []
        for line in text.splitlines():
            if line.startswith("- ["):
                match = re.fullmatch(r"- \[ \] (CHG-[A-Za-z0-9_-]+) \| (\d+(?:\.\d+)*) \| (.+)", line)
                if not match or not ID.fullmatch(match[2]):
                    raise ValueError("Change syntax: - [ ] CHG-001 | 1.5 | Acceptance criteria")
                entries.append(match.groups())
        if len({x[0] for x in entries}) != len(entries):
            raise ValueError("Duplicate change IDs")
        with self.db:
            for id_, target, title in entries:
                old = self.db.execute("SELECT * FROM tasks WHERE id=?", (id_,)).fetchone()
                if old:
                    if old['title'] != title or old['target'] != target:
                        raise ValueError("Imported changes are immutable; append a new change ID")
                    continue
                if not any(t['kind'] == 'feature' and t['target'] == target for t in self.tasks()):
                    raise ValueError("Change target must be an existing feature ID")
                self.add(id_, title, "change", target, priority=50)
                self.invalidate(target)
        self.render()

    def invalidate(self, target):
        self.db.execute("UPDATE tasks SET attempts=CASE WHEN status IN ('done','blocked') THEN 0 ELSE attempts END,status='pending' WHERE kind='gate' AND target=?", (target.split('.')[0],))

    def bug(self, target, title, priority=10):
        if not any(t['kind'] == 'feature' and (t['target'] == target or t['target'].split('.')[0] == target) for t in self.tasks()):
            raise ValueError("Bug target must refer to an existing requirement")
        digest = hashlib.sha256((target + '\0' + title).encode()).hexdigest()[:12]
        id_ = "BUG-" + digest
        old = self.db.execute("SELECT * FROM tasks WHERE id=?", (id_,)).fetchone()
        if not old:
            self.add(id_, title, "bug", target, priority)
        elif old['status'] == 'done':
            self.db.execute("UPDATE tasks SET status='pending',attempts=0 WHERE id=?", (id_,))
            self.event(id_, "reopened", title)
        self.invalidate(target)
        return id_

    def sync_gates(self):
        rows = self.tasks()
        for group in {x['target'].split('.')[0] for x in rows if x['kind'] == 'feature'}:
            related = [x for x in rows if x['target'].split('.')[0] == group and x['kind'] not in ('gate', 'plan')]
            if related and all(x['status'] == 'done' for x in related):
                id_ = 'TEST-' + group
                if not any(x['id'] == id_ for x in rows):
                    self.add(id_, 'Test all features, edge cases and regressions for requirement ' + group, 'gate', group, 20)

    def next_task(self):
        self.sync_gates()
        rows = self.tasks()
        done = {x['id'] for x in rows if x['status'] == 'done'}
        groups = sorted({x['target'].split('.')[0] for x in rows if x['kind'] == 'feature'}, key=numeric)
        active = next((g for g in groups if 'TEST-' + g not in done), None)
        ready = [x for x in rows if x['status'] == 'pending' and set(json.loads(x['deps'])) <= done
                 and (x['kind'] in ('bug', 'plan') or x['target'].split('.')[0] == active)
                 and (x['kind'] != 'gate' or all(t['status'] == 'done' for t in rows if t['kind'] not in ('gate', 'plan') and t['target'].split('.')[0] == x['target']))]
        # Repairs always precede new work; numeric tuples order 1.2 before 1.10.
        return min(ready, key=lambda x: (0 if x['kind'] == 'bug' else 1, x['priority'], numeric(x['target']), x['id'])) if ready else None

    def render(self):
        rows = sorted(self.tasks(), key=lambda x: (numeric(x['target']), x['kind'], x['id']))
        atomic(self.root / 'CHECKLIST.md', '# Workflow checklist\n\nGenerated from verified state; edit requirements and changes instead.\n\n' + '\n'.join(
            f"- [{'x' if x['status'] == 'done' else ' '}] {x['id']} {x['title']} — {x['status']}" for x in rows) + '\n')
        atomic(self.root / 'BUGS.md', '# Bugs and regressions\n\n' + '\n'.join(
            f"- [{'x' if x['status'] == 'done' else ' '}] {x['id']} → {x['target']}: {x['title']} — {x['status']}" for x in rows if x['kind'] == 'bug') + '\n')
        atomic(self.root / 'CURRENT.md', '# Current implementation\n\n' + '\n\n'.join(
            f"## {x['id']} — {x['title']}\n\n{x['summary']}" for x in rows if x['status'] == 'done' and x['kind'] != 'gate') + '\n')
        history = self.db.execute("SELECT * FROM events WHERE action IN ('done','failed','limited','blocked','reopened') ORDER BY seq").fetchall()
        atomic(self.root / 'HISTORY.md', '# Version history\n\n' + '\n'.join(
            f"- v{x['seq']} · {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(x['at']))} · {x['task']} · {x['action']}: {x['detail']}" for x in history) + '\n')

    def prompt(self, task, attempt, report):
        completed = [dict(id=x['id'], title=x['title'], summary=x['summary'][:1200]) for x in self.tasks() if x['status'] == 'done' and x['target'].split('.')[0] == task['target'].split('.')[0]]
        context = {name: (self.root / name).read_text()[:self.config['context_chars']] for name in ['SYSTEM_DESIGN.md'] if (self.root / name).exists()}
        master_path = self.root / 'MASTER_PROMPT.md'
        master = master_path.read_text()[:16000] if master_path.exists() else MASTER
        return master + '\nWorkspace: ' + str(self.root) + '\nReport: ' + str(report) + '\nAttempt: ' + attempt + '\nTask: ' + json.dumps(task) + '\nImplemented in this requirement: ' + json.dumps(completed)[:self.config['context_chars']] + '\nDesign: ' + json.dumps(context) + '\nRead REQUIREMENTS.md and CURRENT.md for full acceptance criteria and implementation details when relevant; test gates must cover every approved feature in their group.'

    def process(self, argv, logfile, timeout):
        """Stream to disk; terminate the process group on timeout or interruption."""
        with logfile.open('wb') as log:
            child = subprocess.Popen(argv, cwd=self.root, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                return child.wait(timeout=timeout)
            except BaseException:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                raise

    def tick(self):
        with self.lock():
            if self.get('paused') == '1':
                return 'paused'
            if float(self.get('resume_at', '0')) > time.time():
                return 'waiting'
            # A prior runner died. Its filesystem edits survive, task is retried.
            with self.db:
                self.db.execute("UPDATE tasks SET status='pending' WHERE status='running'")
                task = self.next_task()
            if task is None:
                self.render()
                return 'blocked' if any(x['status'] != 'done' for x in self.tasks()) else 'idle'
            if task['attempts'] >= self.config['max_attempts']:
                with self.db:
                    self.db.execute("UPDATE tasks SET status='blocked' WHERE id=?", (task['id'],))
                    self.event(task['id'], 'blocked', 'Retry budget exhausted; inspect logs and retry explicitly')
                self.render()
                return 'blocked'
            attempt = uuid.uuid4().hex
            run = self.meta / 'runs' / attempt
            run.mkdir(parents=True)
            report = run / 'report.json'
            prompt = self.prompt(task, attempt, report)
            atomic(run / 'prompt.md', prompt)
            protected_paths = [self.root / n for n in ['REQUIREMENT_CHANGES.md', 'REQUIREMENTS.md', 'MASTER_PROMPT.md']] + [self.meta / 'config.json']
            protected = {p: p.read_bytes() if p.exists() else None for p in protected_paths}
            with self.db:
                self.db.execute("UPDATE tasks SET status='running',attempts=attempts+1 WHERE id=?", (task['id'],))
                self.event(task['id'], 'started', attempt)
            outcome, detail = 'failed', 'Agent did not return a valid completion report'
            try:
                code = self.process(command(self.config['agent'], prompt, self.config.get('command')), run / 'agent.log', self.config['timeout_seconds'])
                # Inspect only the bounded tail of the log, never load the entire transcript.
                with (run / 'agent.log').open('rb') as log:
                    log.seek(max(0, log.seek(0, 2) - 65536))
                    output = log.read().decode(errors='replace')
                if (code != 0 or provider_error(output) or not report.exists()) and LIMIT.search(output):
                    delay = reset_delay(output, self.config['cooldown_seconds'])
                    configured = self.config.get('reset_at')
                    if configured:
                        from datetime import datetime
                        until_reset = datetime.fromisoformat(configured.replace('Z', '+00:00')).timestamp() - time.time()
                        if until_reset > 0:
                            delay = until_reset
                    with self.db:
                        self.set('resume_at', time.time() + delay)
                        self.db.execute("UPDATE tasks SET attempts=attempts-1 WHERE id=?", (task['id'],))
                    outcome, detail = 'limited', f'Credits/limits unavailable; retry in {delay:.0f}s'
                elif code == 0 and not provider_error(output) and report.exists():
                    if report.stat().st_size > 1000000:
                        raise ValueError('Report exceeds 1 MB')
                    result = json.loads(report.read_text())
                    if not isinstance(result, dict):
                        raise ValueError('Report must be a JSON object')
                    if result.get('task_id') != task['id'] or result.get('attempt') != attempt:
                        raise ValueError('Report task/attempt mismatch')
                    if result.get('status') == 'blocked':
                        outcome, detail = 'blocked', str(result.get('summary', 'Agent blocked'))
                    elif result.get('status') == 'done':
                        if not isinstance(result.get('summary'), str) or not result['summary'].strip():
                            raise ValueError('Completion needs a nonempty summary')
                        if not isinstance(result.get('tests'), list) or not result['tests'] or not all(isinstance(x, str) and x.strip() for x in result['tests']):
                            raise ValueError('Completion needs test evidence')
                        bugs = result.get('bugs', [])
                        if not isinstance(bugs, list):
                            raise ValueError('bugs must be an array')
                        for bug in bugs:
                            if not isinstance(bug, dict) or not isinstance(bug.get('target'), str) or not isinstance(bug.get('title'), str):
                                raise ValueError('Malformed bug report')
                        if task['kind'] == 'plan':
                            requirements = result.get('requirements')
                            if not isinstance(requirements, list) or not requirements:
                                raise ValueError('Planning report must include nonempty requirements array')
                            ids = []
                            for requirement in requirements:
                                if not isinstance(requirement, dict) or not isinstance(requirement.get('id'), str) or not ID.fullmatch(requirement['id']) or not isinstance(requirement.get('title'), str) or not requirement['title'].strip() or '\n' in requirement['title']:
                                    raise ValueError('Invalid planned requirement')
                                ids.append(requirement['id'])
                            if len(set(ids)) != len(ids) or any(any(other.startswith(id_ + '.') for other in ids) for id_ in ids):
                                raise ValueError('Planned requirements must have distinct leaf IDs')
                            atomic(self.root / 'PLANNED_REQUIREMENTS.md', '# Proposed requirements — review before import\n\n' + '\n'.join('- [ ] ' + r['id'] + ' ' + r['title'] for r in requirements) + '\n')
                        checks = [] if task['kind'] == 'plan' else self.config['test_commands']
                        if task['kind'] == 'gate' and not checks:
                            raise ValueError('Configure test_commands before passing a top-level gate')
                        checks_ok = True
                        for i, check in enumerate(checks):
                            if not isinstance(check, list) or not check or not all(isinstance(x, str) for x in check):
                                raise ValueError('Tests must be argv arrays')
                            if self.process(check, run / f'test-{i}.log', self.config['timeout_seconds']) != 0:
                                checks_ok = False
                                detail = f'Host verification command {i} failed; see {run.name}/test-{i}.log'
                                if task['kind'] != 'bug':
                                    with self.db:
                                        self.bug(task['target'], f'Repair failing verification for {task["id"]}: {json.dumps(check)}')
                                break
                        if checks_ok:
                            with self.db:
                                for bug in bugs:
                                    self.bug(bug['target'], bug['title'])
                            if task['kind'] == 'gate' and bugs:
                                detail = 'Gate reported defects; repair before passing'
                            else:
                                outcome, detail = 'done', result['summary'] + '\nTests: ' + '; '.join(result['tests'])
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                detail = str(exc)
            except KeyboardInterrupt:
                detail = 'Interrupted; partial edits retained'
                raise
            finally:
                changed = [p for p, before in protected.items() if (p.read_bytes() if p.exists() else None) != before]
                for p in changed:
                    if protected[p] is None:
                        p.unlink(missing_ok=True)
                    else:
                        p.write_bytes(protected[p])
                if changed:
                    outcome, detail = 'blocked', 'Agent modified human-owned inputs; originals restored'
                with self.db:
                    status = outcome if outcome in ('done', 'blocked') else 'pending'
                    self.db.execute("UPDATE tasks SET status=?,summary=? WHERE id=?", (status, detail if outcome == 'done' else task['summary'], task['id']))
                    if outcome == 'done' and task['kind'] != 'gate':
                        self.invalidate(task['target'])
                    self.event(task['id'], outcome, detail)
                self.render()
            return outcome
