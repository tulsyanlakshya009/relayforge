# Getting started

By the end of this guide, you will have an initialized application, an approved queue,
verification commands and a first work item ready for review.

## 1. Prepare your environment

You need macOS or Linux, Python 3.9+, an application working directory, and an installed
coding-agent CLI. Authenticate that agent through its native login flow. Check its native
permissions before running unattended. Some agents require a Git repository or a trusted
workspace. For OpenClaw, configure the selected agent's workspace to match the application.

Keep a clean commit or backup of your application before the first run. The worker and its
tests can modify application files with the permissions you give them.

Install from the RelayForge checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
relayforge --help
```

You can run the installed executable from any directory. The examples use absolute paths
so it is clear which repository will receive application changes.

## 2. Initialize the managed application

```bash
relayforge --project /absolute/path/to/my-app init --agent codex
```

`init` creates `.relayforge/config.json`, local queue state and generated record files.
It also creates requirement, change, master-prompt and design templates when those files
do not already exist. It appends `.relayforge/` to the application's `.gitignore`.
It does not create a Git repository or install an agent. A second initialization is rejected.

Use `claude`, `grok`, `kimi`, `hermes` or `openclaw` to select another adapter.

## 3. Define approved scope

Edit the application's `REQUIREMENTS.md`. Each executable item must use this syntax:

```markdown
# Approved requirements

## 1. Task storage
- [ ] 1.1 Define the task record and storage interface; document persistence decisions
- [ ] 1.2 Save and reload tasks; preserve titles and completion state across restart
- [ ] 1.3 Reject blank titles and corrupted input with useful errors

## 2. Task commands
- [ ] 2.1 Add create and list commands; verify output for empty and populated lists
```

Use headings for groups and checkboxes for leaf items. Put acceptance criteria on the
checkbox line. Additional prose is useful context but is not imported as a work item's title.
See [Workflow](workflow.md) for import rules and amendments.

### Optional: start from a brief

Save the idea in the application's `BRIEF.md`, then queue a planning item:

```bash
relayforge --project /absolute/path/to/my-app plan BRIEF.md
relayforge --project /absolute/path/to/my-app run
```

After planning completes, review `PLANNED_REQUIREMENTS.md`. Copy the approved checklist
into `REQUIREMENTS.md` before importing. Planning does not approve or import its output.
Identical brief content queues the same planning ID; it does not create a second plan.
To retry an unfinished plan, use its ID from `status`. To request a new plan, revise the brief.
Planning skips independent application test commands and reports its feasibility checks.

## 4. Configure meaningful verification

Use the application's actual test runner. For a Python application:

```bash
relayforge --project /absolute/path/to/my-app configure \
  --tests '[["python3","-m","unittest","discover","-s","tests","-v"]]'
```

For an application whose package.json defines a noninteractive test script:

```bash
relayforge --project /absolute/path/to/my-app configure \
  --tests '[["npm","run","test:ci"]]'
```

Commands are JSON arrays of arguments, executed in the application directory. They do
not go through a shell. Choose commands that fail on errors and, where supported, fail
when no tests are found. A command exiting successfully with zero tests does not establish
coverage. All configured commands must pass; execution stops at the first failure.

## 5. Import and check the queue

```bash
relayforge --project /absolute/path/to/my-app import
relayforge --project /absolute/path/to/my-app doctor
relayforge --project /absolute/path/to/my-app status
```

`doctor` checks executable availability and whether test commands are configured. It does
not make a provider request, validate your login or prove the agent has editing permissions.
`status` prints JSON task records. Requirements remain unchecked in the human input file;
completion checkmarks appear in generated `CHECKLIST.md`.

## 6. Run and review one increment

```bash
relayforge --project /absolute/path/to/my-app tick
```

Inspect the application's source diff, `CHECKLIST.md`, `CURRENT.md`, `SYSTEM_DESIGN.md`
and the attempt's logs under `.relayforge/runs/`. Confirm that the implementation matches
its criteria and that verification actually ran. A `done` result means the report was accepted
and configured checks succeeded; it does not substitute for your first-run review.

## 7. Continue or schedule

```bash
relayforge --project /absolute/path/to/my-app run
```

The foreground worker continues through successful items and waits through recognized
limits. It stops when idle, paused or blocked. Ctrl-C terminates the active process group
and preserves partial source edits for a later attempt.

For repeated scheduled checks, follow [Scheduling](scheduling.md). No scheduler is
installed by `init`, `run` or `schedule`.
