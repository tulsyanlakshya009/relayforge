import argparse
import json
from pathlib import Path
import shlex
import shutil
import sys
import time
from .adapters import COMMANDS, ALIASES, command
from .core import Project, atomic, MASTER


def init(root, agent):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    meta = root / '.relayforge'
    if (meta / 'config.json').exists():
        raise ValueError('Project already initialized')
    meta.mkdir(exist_ok=True)
    config = dict(agent=ALIASES.get(agent, agent), test_commands=[], max_attempts=3,
                  timeout_seconds=1800, cooldown_seconds=18000, poll_seconds=60, context_chars=8000)
    atomic(meta / 'config.json', json.dumps(config, indent=2) + '\n')
    templates = {
        'MASTER_PROMPT.md': MASTER,
        'REQUIREMENTS.md': '# Approved requirements\n\n## 1. First feature\n\n- [ ] 1.1 Replace this example with a precise feature and acceptance criteria\n',
        'REQUIREMENT_CHANGES.md': '# Human requirement changes\n\nAppend entries after reviewing implemented work. Import explicitly with `relayforge changes`.\n\n<!-- - [ ] CHG-001 | 1.1 | Describe the approved change and acceptance criteria -->\n',
        'SYSTEM_DESIGN.md': '# System design\n\nRecord architecture, interfaces, data model, constraints and decisions here.\n',
    }
    for name, text in templates.items():
        if not (root / name).exists():
            atomic(root / name, text)
    with (root / '.gitignore').open('a') as stream:
        stream.write('\n# RelayForge local state and private transcripts\n.relayforge/\n')
    project = Project(root)
    project.render()
    project.close()
    print(f'Initialized {root}. Edit REQUIREMENTS.md, configure test_commands, then import.')


def validate_config(config):
    agent = config.get('agent')
    if agent not in COMMANDS and not config.get('command'):
        raise ValueError('Unknown adapter; use a custom command array')
    command(agent, 'validation', config.get('command'))
    for key in ['timeout_seconds', 'cooldown_seconds', 'poll_seconds', 'context_chars', 'max_attempts']:
        if not isinstance(config.get(key), (int, float)) or isinstance(config.get(key), bool) or config[key] <= 0:
            raise ValueError(key + ' must be positive')
    if not isinstance(config['max_attempts'], int) or not isinstance(config['context_chars'], int):
        raise ValueError('max_attempts and context_chars must be integers')
    if not isinstance(config.get('test_commands'), list):
        raise ValueError('test_commands must be an array of argv arrays')
    for check in config['test_commands']:
        if not isinstance(check, list) or not check or not all(isinstance(x, str) for x in check):
            raise ValueError('test_commands must be an array of argv arrays')
    if config.get('reset_at'):
        from datetime import datetime
        value = datetime.fromisoformat(config['reset_at'].replace('Z', '+00:00'))
        if value.tzinfo is None:
            raise ValueError('reset_at must include a timezone')


def main(argv=None):
    parser = argparse.ArgumentParser(description='RelayForge — resume development when your budget does')
    parser.add_argument('--project', default='.', help='Target code repository')
    commands = parser.add_subparsers(dest='action', required=True)
    p = commands.add_parser('init'); p.add_argument('--agent', choices=list(COMMANDS) + list(ALIASES), default='codex')
    p = commands.add_parser('plan'); p.add_argument('brief', help='Markdown project brief to decompose into a proposed checklist')
    p = commands.add_parser('import'); p.add_argument('file', nargs='?', default='REQUIREMENTS.md')
    commands.add_parser('changes', help='Import human-approved requirement changes')
    p = commands.add_parser('bug'); p.add_argument('target'); p.add_argument('title'); p.add_argument('--priority', type=int, default=10)
    for name in ['status', 'tick', 'pause', 'resume', 'doctor', 'schedule']:
        commands.add_parser(name)
    p = commands.add_parser('run'); p.add_argument('--max-ticks', type=int, default=0, help='0 runs until idle/blocked; waits for limits to reset')
    p = commands.add_parser('retry'); p.add_argument('id')
    p = commands.add_parser('configure'); p.add_argument('--agent', choices=list(COMMANDS)); p.add_argument('--command', help='JSON argv array containing {prompt}'); p.add_argument('--tests', help='JSON array of test argv arrays'); p.add_argument('--cooldown', type=int); p.add_argument('--reset-at', help='ISO 8601 datetime including timezone')
    args = parser.parse_args(argv)
    project = None
    try:
        if args.action == 'init':
            init(args.project, args.agent)
            return
        project = Project(args.project)
        validate_config(project.config)
        if args.action in ['plan', 'import', 'changes', 'bug', 'pause', 'resume', 'retry', 'configure']:
            with project.lock():
                if args.action == 'plan':
                    path = Path(args.brief)
                    text = (path if path.is_absolute() else project.root / path).read_text()
                    title = 'PLANNING ONLY: Decompose the following brief into numbered leaf requirements with acceptance criteria, starting with requirements analysis and system design, then bounded implementation increments. Do not implement features yet. In the completion report add requirements: [{id: positive dotted numeric ID, title: single-line acceptance criteria}]. Report actual feasibility and checklist validation checks in tests. Brief:\n' + text
                    # Task titles are single-line; JSON preserves brief line breaks as text.
                    title = title.replace('\n', ' ')
                    import hashlib
                    id_ = 'PLAN-' + hashlib.sha256(text.encode()).hexdigest()[:12]
                    with project.db:
                        if not any(x['id'] == id_ for x in project.tasks()):
                            project.add(id_, title, 'plan', '1', priority=0)
                    project.render()
                    print('Planning queued. Run the worker, then review PLANNED_REQUIREMENTS.md before importing.')
                elif args.action == 'import':
                    path = Path(args.file)
                    project.import_requirements(path if path.is_absolute() else project.root / path)
                elif args.action == 'changes':
                    project.import_changes()
                elif args.action == 'configure':
                    config = dict(project.config)
                    if args.agent: config['agent'] = args.agent; config.pop('command', None)
                    if args.command: config['command'] = json.loads(args.command)
                    if args.tests: config['test_commands'] = json.loads(args.tests)
                    if args.cooldown is not None: config['cooldown_seconds'] = args.cooldown
                    if args.reset_at == 'auto': config.pop('reset_at', None)
                    elif args.reset_at: config['reset_at'] = args.reset_at
                    validate_config(config)
                    atomic(project.meta / 'config.json', json.dumps(config, indent=2) + '\n')
                else:
                    with project.db:
                        if args.action == 'bug':
                            print(project.bug(args.target, args.title, args.priority))
                        elif args.action in ['pause', 'resume']:
                            project.set('paused', '1' if args.action == 'pause' else '0')
                        else:
                            count = project.db.execute("UPDATE tasks SET status='pending', attempts=0 WHERE id=? AND status!='done'", (args.id,)).rowcount
                            if not count: raise ValueError('No unfinished task with this ID')
                            project.event(args.id, 'retry', 'Human requested another attempt')
                    project.render()
        elif args.action == 'status':
            with project.lock():
                with project.db: project.sync_gates()
                rows = project.tasks()
                print(json.dumps(dict(paused=project.get('paused') == '1', resume_at=float(project.get('resume_at', '0')), tasks=rows), indent=2))
        elif args.action == 'doctor':
            cmd = command(project.config['agent'], 'test', project.config.get('command'))
            found = shutil.which(cmd[0])
            print(f'Agent executable: {found or "MISSING: " + cmd[0]}')
            print(f'Test commands: {len(project.config["test_commands"])}')
            print('Authentication and tool permissions must be configured in the agent itself.')
            if not found or not project.config['test_commands']: sys.exit(1)
        elif args.action == 'schedule':
            executable = shutil.which('relayforge')
            cmd = [executable, '--project', str(project.root), 'tick'] if executable else [sys.executable, '-m', 'relayforge', '--project', str(project.root), 'tick']
            print('# Run one bounded task every minute; cooldown and lock prevent duplicate runs.')
            print('* * * * * ' + shlex.join(cmd) + ' >> ' + shlex.quote(str(project.meta / 'scheduler.log')) + ' 2>&1')
            print('# Set PATH in crontab to include your agent CLI. Prefer an installed relayforge executable.')
        elif args.action == 'tick':
            print(project.tick())
        elif args.action == 'run':
            if args.max_ticks < 0: raise ValueError('--max-ticks must be nonnegative')
            count = 0
            while not args.max_ticks or count < args.max_ticks:
                # Reload configuration between work items, including human adapter switches.
                project.config = json.loads((project.meta / 'config.json').read_text())
                validate_config(project.config)
                outcome = project.tick()
                print(outcome, flush=True)
                count += 1
                if outcome in ['idle', 'blocked', 'paused']: break
                if outcome in ['waiting', 'limited', 'failed']:
                    time.sleep(min(60, project.config['poll_seconds']))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'relayforge: {exc}\n')
    except KeyboardInterrupt:
        print('Stopped; progress saved.', file=sys.stderr)
    finally:
        if project: project.close()
