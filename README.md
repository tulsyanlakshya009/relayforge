# RelayForge

<p align="center">
  <img src="assets/relayforge-logo-banner.png" alt="RelayForge logo" width="640">
</p>

**Small prompts. Durable progress. Development that resumes when your budget does.**

RelayForge is a local workflow orchestrator for Codex, Claude Code, Grok Build,
Kimi Code, Hermes and OpenClaw. It turns numbered requirements into a persistent
queue, sends one bounded work item to your installed agent, verifies its output,
records bugs, updates documentation and waits when a usage limit is reached.
Python 3.9+ on macOS or Linux; no runtime dependencies and no paid API of its own.

This is an initial working CLI release. Adapter command construction is tested;
paid live executions across all six providers have not been tested.

## Quick start

```bash
git clone git@github.com:tulsyanlakshya009/relayforge.git
cd relayforge
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Point it at the codebase you want your agent to develop.
relayforge --project /absolute/path/to/my-app init --agent codex
```

Optionally write a project idea in `BRIEF.md` inside the target project and let the
agent propose the decomposition:

```bash
relayforge --project /absolute/path/to/my-app plan BRIEF.md
relayforge --project /absolute/path/to/my-app run
# Review PLANNED_REQUIREMENTS.md, copy the approved checklist to REQUIREMENTS.md,
# then import it using the steps below. Planning never auto-approves its own scope.
```

The planning task asks for requirements analysis, system design and bounded implementation
increments with acceptance criteria. Edit the generated `MASTER_PROMPT.md` to customize
your development process. Edit the generated `REQUIREMENTS.md`, then configure real verification commands:

```markdown
# Approved requirements

## 1. Account creation
- [ ] 1.1 Design account storage and document the public interfaces
- [ ] 1.2 Implement signup; reject duplicate emails and invalid passwords
- [ ] 1.3 Implement login; reject invalid credentials without leaking account existence

## 2. Profile
- [ ] 2.1 Implement profile editing with field validation and authorization
```

Checkboxes are executable leaf tasks. Headings group them; avoid checking both
`1` and `1.1`. IDs sort numerically (`1.2` precedes `1.10`). Put acceptance criteria
on the task's line; link longer specifications in its text so the agent can read them.
Imported requirements are immutable. New scope for existing features belongs in the
human change file; new numbered features can be appended and imported.

```bash
relayforge --project /absolute/path/to/my-app configure \
  --tests '[["python3","-m","unittest","discover","-s","tests","-v"]]'
relayforge --project /absolute/path/to/my-app import
relayforge --project /absolute/path/to/my-app doctor
relayforge --project /absolute/path/to/my-app run
```

Use your application's actual test command, such as `npm test -- --run`, rather
than the example when its stack differs. Initialize Git in the target project if
your selected agent requires a trusted Git working directory. Authenticate the agent
once using its own login flow and configure its permitted tools before unattended runs.

## How it works

1. Select a repair first, otherwise the earliest unfinished requirement group.
2. Execute one subtask with its criteria, relevant design, and compact completion context.
3. Require a fresh, task-specific JSON report; run configured tests independently.
4. Tick the verified item, record its implementation and tests, and enqueue discovered bugs.
5. Once all items in group `1` pass, enqueue `TEST-1` covering every defined feature
   and its edge cases. Requirement `2` waits until this gate passes.
6. A bug targeting `1.5` preempts new feature work, including work in later groups.
   A successful repair invalidates `TEST-1` and schedules its regression gate again.
7. On a limit signal, save the same work item and its partial edits, wait, then retry.

No automatic commits, pushes, deployments or publishing happen in managed projects.
The agent is asked to perform requirements analysis, design, implementation, tests,
and documentation as one bounded development increment. Put explicit design spikes or
other activities into numbered tasks when they should have their own queue position.

## Human changes and bug reports

Only a human authors requirement changes. Append after reviewing completed work:

```markdown
- [ ] CHG-001 | 1.2 | Accept passphrases up to 128 characters and add boundary tests
```

Then approve them for execution with:

```bash
relayforge --project /absolute/path/to/my-app changes
relayforge --project /absolute/path/to/my-app bug 1.2 "Signup rejects valid long passphrases"
```

The runner never automatically imports `REQUIREMENT_CHANGES.md`, never ticks it,
and restores that file if an agent modifies it during a normal run. Imported change
IDs are immutable: append `CHG-002` for the next revision. Bug titles are deduplicated
per target and resolved bugs reopen when reported again. Repairs have highest priority;
changes precede ordinary features within their group. `bug --priority 1` raises a
repair's priority over other repairs (lower number means higher priority).

## Credits, resets and scheduling

RelayForge cannot query every subscription's balance. It detects common quota/rate
signals in failed executions, structured provider errors, or runs without a completion
report. It reads explicit relative retry signals or ISO reset times from log tails.
Otherwise the configurable cooldown is **five hours**. Detection is heuristic: inspect
logs if a provider emits an unfamiliar signal or a non-credit error is misclassified.
Limits do not consume the ordinary failure retry budget. No account rotation, billing
bypass or automatic purchase takes place.

```bash
relayforge --project /absolute/path/to/my-app configure --cooldown 18000
# Optional exact next reset including timezone; takes precedence over log/fallback timing.
relayforge --project /absolute/path/to/my-app configure --reset-at 2026-10-15T09:00:00+08:00
relayforge --project /absolute/path/to/my-app configure --reset-at auto  # restore automatic timing
relayforge --project /absolute/path/to/my-app status
relayforge --project /absolute/path/to/my-app schedule
```

`schedule` prints a crontab entry; review and install it with `crontab -e`. It does
not change your machine's scheduler. Each tick executes at most one work item;
file locks prevent overlapping executions and SQLite preserves queue state. Set
`PATH` in the crontab to include the agent's executable. The virtualenv's absolute
`relayforge` path is included in the generated command. The computer must be awake.
For machines without cron, run under launchd or systemd using [the service guide](docs/scheduling.md).

`run` waits through cooldowns and exits when idle, paused or blocked. Cron can continue
checking after idle, so subsequently imported human changes are picked up. Ordinary
failures stop after three attempts per item. Authentication/permission errors usually
need a human fix. A task reported blocked stops the continuous loop for review.

```bash
relayforge --project /absolute/path/to/my-app pause
relayforge --project /absolute/path/to/my-app resume
relayforge --project /absolute/path/to/my-app retry BUG-<id-from-status>
relayforge --project /absolute/path/to/my-app tick
relayforge --project /absolute/path/to/my-app run --max-ticks 5
```

Pause and config commands take the project lock, so wait for an active work item to
finish first, or stop the foreground runner with Ctrl-C. Ctrl-C terminates the child
process group and leaves work pending. `resume` clears pause; it respects credit cooldown.

## Agent compatibility

| Adapter | Default invocation | Setup |
|---|---|---|
| `codex` | `codex exec --sandbox workspace-write PROMPT` | CLI login; Git project; workspace sandbox |
| `claude` | `claude -p PROMPT --output-format json --permission-mode acceptEdits` | CLI login; explicitly allow required test/build tools |
| `grok` | `grok -p PROMPT --output-format json` | Grok Build login and native tool permissions |
| `kimi` | `kimi -p PROMPT` | Kimi Code login and native tool permissions |
| `hermes` | `hermes chat -q PROMPT` | Provider setup; terminal/code tools enabled |
| `openclaw` | `openclaw agent --local --agent main --message PROMPT --json` | Configure `main` agent's workspace to the target project |

Aliases accepted during init: `claude-code`, `grok-build`, `kimi-code`.
Native tool approval policies still apply. RelayForge does not disable them globally.
If an agent requires an interactive approval, configure a scoped allowlist or an
isolated runtime according to that agent's documentation. Merely launching a CLI
non-interactively does not guarantee it can perform every requested edit or command.

Switch tools without losing the queue:

```bash
relayforge --project /absolute/path/to/my-app configure --agent claude
# Customize CLI flags or use a different binary/profile; JSON argv, never a shell string.
relayforge --project /absolute/path/to/my-app configure \
  --command '["claude","-p","{prompt}","--output-format","json","--permission-mode","acceptEdits","--allowedTools","Read,Edit,Write,Bash(python3 -m unittest:*)"]'
```

All arguments are passed directly to a subprocess; prompt text is never shell-expanded.
The same report-file contract works with customized commands. See
[official interface references](docs/adapters.md) and [architecture](docs/architecture.md).

## Project files

| File | Owner / purpose |
|---|---|
| `REQUIREMENTS.md` | Human-approved numbered requirements |
| `REQUIREMENT_CHANGES.md` | Human-authored amendments; explicit import |
| `MASTER_PROMPT.md` | Editable bounded workflow and report instructions |
| `PLANNED_REQUIREMENTS.md` | Agent-proposed decomposition; review before import |
| `SYSTEM_DESIGN.md` | Agent-maintained architecture and decisions |
| `CHECKLIST.md` | Generated task and test-gate status |
| `BUGS.md` | Generated defect checklist tied to requirement IDs |
| `CURRENT.md` | All verified implementation summaries, usage and test evidence |
| `HISTORY.md` | Append-only database events rendered as version history |
| `.relayforge/config.json` | Agent, test argv arrays, timeouts, cooldown and prompt limits |
| `.relayforge/state.sqlite3` | Durable queue, attempts, events, pause and reset timestamp |
| `.relayforge/runs/<attempt>/` | Per-attempt prompt, report, agent log and independent test logs |

Generated documentation reflects verified work only. During partial attempts, source
files can be ahead of `CURRENT.md`; completion brings them back into alignment.
Version entries are local workflow events, not Git tags or semantic releases.
State and transcripts are Git-ignored. Keep a local backup of `.relayforge` to preserve
resume information. Code can contain partial edits on retries: inspect and reuse them.

## Development and scope

```bash
python3 -m unittest discover -s tests -v
```

Tests use a local fake agent and exercise ordering, repair priority, top-level gates,
quota wait/resume, restarts, timeouts, lock exclusion, retry bounds, protected inputs,
immutable human changes and report validation without spending model credits. GitHub
Actions runs the suite on Python 3.9, 3.12 and 3.13.

The report is agent-authored evidence, not a formal proof of correctness. Actual coverage
and acceptance depend on the tests you configure and the agent's implementation. File
protection is a workflow guard after normal runs, not a sandbox: abrupt machine failure
or an agent with broad filesystem access can still alter inputs. Use native agent
sandboxing and trusted repositories. Tests and agents execute code with your local
permissions. Windows support, a web dashboard, automatic subscription-balance APIs,
and native provider session resumption are outside this release. Resume uses persisted
work items, compact context and workspace edits rather than assuming identical session
APIs across vendors.

MIT licensed.
