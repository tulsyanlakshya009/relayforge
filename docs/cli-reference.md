# CLI reference

All examples assume RelayForge is installed. Put the global project option **before** the
subcommand:

```text
relayforge [--project PATH] COMMAND [OPTIONS]
```

`PATH` defaults to the current directory. Relative requirement and brief paths are resolved
against the managed project. Use `relayforge COMMAND --help` for argparse's option help.

## Setup and inputs

| Command | Options / arguments | Behavior |
|---|---|---|
| `init` | `--agent NAME`, default `codex` | Initializes local config/state and project templates; rejects an already initialized project |
| `plan BRIEF` | Markdown brief path | Queues a planning item; does not immediately call an agent or import the resulting proposal |
| `import [FILE]` | Default `REQUIREMENTS.md` | Adds approved numbered requirements; existing IDs must have identical titles |
| `changes` | None | Explicitly imports entries in `REQUIREMENT_CHANGES.md` |
| `bug TARGET TITLE` | `--priority INTEGER`, default `10` | Adds/deduplicates a repair and prints its ID; lower priority numbers run earlier |

`init` accepts `codex`, `claude`, `grok`, `kimi`, `hermes` and `openclaw`. It also accepts
aliases `claude-code`, `grok-build` and `kimi-code`. `configure --agent` uses canonical names.

## Execution and control

| Command | Options / arguments | Behavior |
|---|---|---|
| `tick` | None | Makes one scheduling pass; launches at most one work item and prints an outcome |
| `run` | `--max-ticks INTEGER`, default `0` | Repeats ticks; `0` means no count limit; exits on idle, paused or blocked |
| `status` | None | Prints JSON with pause state, reset timestamp and task records |
| `pause` | None | Sets the project pause flag after acquiring its lock |
| `resume` | None | Clears pause; does not clear cooldown or retry counters |
| `retry ID` | An unfinished item ID | Sets that item pending and resets its ordinary attempt counter |
| `doctor` | None | Checks agent executable availability and nonempty verification configuration |
| `schedule` | None | Prints a cron entry and PATH guidance; installs nothing |

`run --max-ticks 5` counts scheduling passes, including waits; it does not mean five completed
tasks. Between failed, waiting or limited outcomes, `run` sleeps for the configured poll
interval, capped at 60 seconds. Other successful outcomes continue immediately.

Queue mutation and execution use a nonblocking project lock. `status` also needs that
lock and may create newly eligible test-gate rows. It is not a live read of an active attempt.
If another runner holds the lock, these commands fail rather than waiting.

## Configuration commands

```bash
relayforge --project /absolute/path/to/my-app configure --agent claude
relayforge --project /absolute/path/to/my-app configure --tests '[["npm","run","test:ci"]]'
relayforge --project /absolute/path/to/my-app configure --cooldown 18000
relayforge --project /absolute/path/to/my-app configure --reset-at 2026-10-15T09:00:00+08:00
relayforge --project /absolute/path/to/my-app configure --reset-at auto
```

| Option | Value | Effect |
|---|---|---|
| `--agent` | Canonical adapter name | Selects the adapter and removes any previous custom command |
| `--command` | JSON argument array containing `{prompt}` | Overrides the agent command; each argument is passed without shell expansion |
| `--tests` | JSON array of argument arrays | Replaces the entire verification-command list |
| `--cooldown` | Positive integer seconds | Sets the fallback limit wait |
| `--reset-at` | Timezone-aware ISO timestamp, or `auto` | Sets a next-reset override, or removes it |

See [Configuration](configuration.md) for defaults and settings that require editing the
local config file with the worker stopped.

## Interpreting output

| Tick outcome | Next action |
|---|---|
| `done` | Review completed work and evidence; continue to the next item |
| `failed` | Inspect agent/report/test logs; task remains pending until its attempt budget is exhausted |
| `limited` | A reset time was saved; keep the worker or scheduler running |
| `waiting` | Cooldown has not expired; no agent was launched |
| `blocked` | Inspect the blocker; fix it and retry, or pause for review |
| `paused` | Resume the project when ready |
| `idle` | No unfinished work remains; import approved work to continue |

These outcome strings do not map to nonzero process exit codes. A normal `tick` returning
`failed` or `blocked` still exits successfully. Supervisors should inspect output, state and
logs rather than relying only on exit status.

Successful CLI commands normally exit `0`. `doctor` exits `1` when the executable is
missing or no test commands are configured. Argument errors and handled configuration,
file or lock errors exit `2`. Unexpected failures can produce a traceback. Ctrl-C prints
`Stopped; progress saved.`; inspect the last attempt before restarting.

## Status example

```json
{
  "paused": false,
  "resume_at": 0.0,
  "tasks": [
    {
      "id": "1.1",
      "target": "1.1",
      "kind": "feature",
      "title": "Save and reload tasks; preserve titles across restart",
      "status": "pending",
      "priority": 100,
      "attempts": 0,
      "summary": "",
      "deps": "[]"
    }
  ]
}
```

`resume_at` is a Unix timestamp in seconds; zero means no reset has been saved. An expired
nonzero value may remain in output. `deps` is a serialized internal field; there is no public
CLI for managing dependency graphs in 0.1.0.
