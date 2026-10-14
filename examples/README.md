# Example: a persistent task-list application

These files demonstrate input structure. They are not a live-agent transcript or a completed
application. Copy the brief or requirements into a disposable managed project to try them.

- [BRIEF.md](BRIEF.md) is a product idea suitable for `plan BRIEF.md`.
- [REQUIREMENTS.md](REQUIREMENTS.md) is a manually reviewed example checklist.
- [REQUIREMENT_CHANGES.md](REQUIREMENT_CHANGES.md) is a later human amendment.

A typical sequence is:

```bash
relayforge --project /absolute/path/to/task-app init --agent codex
# Copy the example requirements into task-app/REQUIREMENTS.md and review them.
# Configure a real test command for the application before implementation.
relayforge --project /absolute/path/to/task-app import
relayforge --project /absolute/path/to/task-app tick
```

Expected ordering after successful work is `1.1`, `1.2`, `1.3`, `TEST-1`, then `2.1`, `2.2`,
`TEST-2`. If a bug is found in `1.2` after group `1` passes, its repair takes precedence and
`TEST-1` is invalidated. Import the example human change only after its target `2.1` has
been registered and you have reviewed the new scope.

Tests should cover saved-state restart, corrupted storage, blank titles, unknown IDs,
completion persistence, empty list output and the later title-length boundary. The runner
asks the agent to create meaningful checks, but review the actual assertions and outputs.
