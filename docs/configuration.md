# Configuration

Each managed project has its own `.relayforge/config.json`. Use `configure` for exposed
options. Stop the worker before manually editing other settings; preserve valid JSON and
all required keys. If a configuration is invalid, commands validate it before executing,
including `configure`, so you may need to repair the file manually.

## Defaults and validation

| Key | Default | Meaning |
|---|---|---|
| `agent` | `codex` | Canonical adapter name |
| `test_commands` | `[]` | Independent verification commands; each is a nonempty array of strings |
| `max_attempts` | `3` | Positive integer ordinary-attempt budget per item |
| `timeout_seconds` | `1800` | Positive number; timeout for the agent and separately for each verification command |
| `cooldown_seconds` | `18000` | Positive number; five-hour fallback when a limit has no usable reset hint |
| `poll_seconds` | `60` | Positive number; foreground polling sleep, capped at 60 seconds |
| `context_chars` | `8000` | Positive integer; excerpt limit for design and completed-group context |
| `command` | Absent | Optional nonempty custom argument array containing `{prompt}` |
| `reset_at` | Absent | Optional timezone-aware ISO timestamp for the next reset |

There is no fixed total-attempt duration: the agent and each check receive their own timeout.
Three 30-minute checks plus a 30-minute agent run can take roughly two hours. Scheduler
settings should account for that duration.

## Verification commands

```json
{
  "test_commands": [
    ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
    ["python3", "scripts/check_acceptance.py"]
  ]
}
```

The commands above are illustrative. Configure paths that actually exist in your application. Verification is sequential and stops at the first nonzero result.
Both agent output and test output go to attempt-specific files.

No command is interpreted as a shell expression. Operators, pipes, globbing and environment
assignments are not expanded. Instead of `"npm test && npm run lint"`, configure two arrays:

```bash
relayforge --project /absolute/path/to/my-app configure \
  --tests '[["npm","run","test:ci"],["npm","run","lint"]]'
```

If a wrapper script is needed, run it explicitly as an argument array and keep it in the
application repository. Executables inherit the runner's environment; install dependencies
and expose the correct PATH before starting the worker.

Planning does not run these independent application checks. Gates require a nonempty
list; ordinary implementation tasks can complete with an empty list if their reports pass
validation. Avoid treating that as equivalent to independent verification.

## Custom agent command

```bash
relayforge --project /absolute/path/to/my-app configure \
  --command '["/absolute/path/to/agent-wrapper","{prompt}"]'
```

`{prompt}` is replaced in each argument that contains it. The executable is launched in
the managed project, with stdin closed. Preserve the completion-report contract described
in [Agent setup](adapters.md). Selecting `--agent` removes a previous custom command;
supplying both options in one call selects the adapter then applies the new override.

## Reset timing

When a quota-like signal is recognized, timing is selected in this order:

1. A future operator-configured `reset_at` overrides automatic timing.
2. A usable provider retry/reset hint supplies the delay.
3. `cooldown_seconds` is used as the fallback.

Past `reset_at` overrides are ignored. `--reset-at auto` removes the override. Changing
these settings does not alter a `resume_at` cooldown already stored in the queue. `resume`
also respects that saved cooldown. There is no public command to force-clear a live cooldown.

Recognized hints include numeric JSON `retry_after`, JSON `reset_at`/`resets_at` as a Unix
timestamp or timezone-aware ISO string, plain `retry-after: 120`, and phrases such as
`try again in 2 hours`. Plain ISO reset phrases are also parsed. Detection requires a
quota-like signal, not just a reset hint. Only the last 64 KiB of the agent log is inspected;
structured JSON parsing requires that inspected text to be a valid JSON object.

This is heuristic recovery. A reported wait does not guarantee that credits will be available
when it expires; a second limit can schedule another wait. Authentication, subscription
changes and unfamiliar provider messages may require human intervention.

## Master prompt and context

`MASTER_PROMPT.md` is initialized with a bounded work-item process and a JSON completion
contract. You may customize workflow guidance, but retain the report instructions and
ownership rules. The runner reads up to 16,000 characters of this file and appends the
current task, report path, attempt ID, capped design excerpt and completed-group context.
If the file is absent, it uses its built-in prompt.

This limits injected orchestration context, not the agent's total token usage. The agent can
read additional files and make multiple model calls according to its own settings. There
is no enforced dollar budget, context-token budget or per-provider spending cap in 0.1.0.
