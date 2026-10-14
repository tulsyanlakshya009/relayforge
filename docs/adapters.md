# Agent setup and report contract

Default CLI forms were checked against primary documentation on 2026-10-14:

- [Codex non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode): `exec`, explicit workspace sandbox. Legacy `--full-auto` is no longer supported.
- [Claude Code programmatic execution](https://code.claude.com/docs/en/headless): print mode, JSON output and tool allowlists.
- [Grok Build getting started](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/01-getting-started.md): `grok -p`, JSON output and repository instructions.
- [Kimi Code command reference](https://www.kimi.com/code/docs/en/kimi-code-cli/reference/kimi-command.html): current `kimi -p` print mode. Older kimi-cli versions may use different flags; use a custom command array.
- [Hermes CLI](https://hermes-agent.nousresearch.com/docs/user-guide/cli): `hermes chat -q` single-query mode.
- [OpenClaw agent CLI](https://docs.openclaw.ai/cli/agent): local execution and agent identity. Match the selected agent workspace to the managed repository; setting a process cwd alone does not change its configured workspace.

Agent installation, account authentication, subscription entitlements, models and tool
permissions remain owned by each CLI. No CLI is bundled. The runner passes its report
contract in the prompt; it does not depend on a vendor-specific conversation ID or event
schema. Report paths include a random attempt nonce and reports are never reused.

If using a custom bridge instead of a supported CLI, it must read the `{prompt}` argument,
perform the work in the supplied workspace, and write the specified JSON report before
exiting. Exit nonzero for transport/provider failures and emit recognizable limit/reset
signals so the runner can wait. Prompt text may contain quotes and newlines and arrives
as a single argv argument. Never construct a shell command with it.

## Included command templates

| Adapter | Argument form | Important setup |
|---|---|---|
| `codex` | `codex exec --sandbox workspace-write PROMPT` | Authenticate; use a trusted Git workspace and workspace permissions |
| `claude` | `claude -p PROMPT --output-format json --permission-mode acceptEdits` | Authenticate; allow required commands through native scoped permissions |
| `grok` | `grok -p PROMPT --output-format json` | Install Grok Build; configure login and tool permissions |
| `kimi` | `kimi -p PROMPT` | Install the appropriate Kimi Code CLI version; configure login and permissions |
| `hermes` | `hermes chat -q PROMPT` | Configure a provider and terminal/code tools |
| `openclaw` | `openclaw agent --local --agent main --message PROMPT --json` | Configure `main` with the managed application's workspace |

These are configurable adapter templates, not a certification that every installed CLI
version or subscription supports unattended execution. The automated suite checks argument
construction and orchestration with a fake agent. Live paid runs across all six tools have
not been verified. Inspect each installed CLI's help and native permission settings.

The child process runs with the managed project as cwd, stdin closed, and combined output
captured in a log. Approvals requiring terminal interaction can fail or time out. RelayForge
does not globally disable native approvals. Configure a scoped allowlist or isolated runtime
appropriate to your agent.

## Completion report contract

The prompt provides an absolute report path and a fresh attempt ID. Write a JSON object
there before exiting. The report file is separate from any JSON the provider prints to stdout.

```json
{
  "task_id": "1.2",
  "attempt": "COPY_THE_EXACT_ID_FROM_THE_PROMPT",
  "status": "done",
  "summary": "Tasks now persist across restart. Use the save/load interface; malformed records return a validation error. No migration from older schemas is included.",
  "tests": [
    "python3 -m unittest discover -s tests -v: passed persistence and invalid-record cases"
  ],
  "bugs": []
}
```

| Field | Contract |
|---|---|
| `task_id` | Must match the selected work item exactly |
| `attempt` | Must match the current prompt's random attempt ID exactly |
| `status` | `done` or `blocked`; other values do not complete the item |
| `summary` | For `done`, a nonempty string describing behavior, usage, verification and limitations |
| `tests` | For `done`, a nonempty array of nonempty evidence strings |
| `bugs` | Optional array, default empty; each object has numeric `target` and one-line `title` |

Reports larger than 1,000,000 bytes are rejected. Unknown fields are not used. A `blocked`
report should provide a useful `summary`; it does not require test evidence, although the
item and attempt IDs still must match. Report validation cannot prove that agent-authored
claims are true. Independent application test commands provide an additional check.

Planning reports must also include a nonempty `requirements` array:

```json
{
  "requirements": [
    {"id": "1.1", "title": "Define storage interfaces and document persistence decisions"},
    {"id": "1.2", "title": "Save and reload tasks; preserve titles across restart"}
  ]
}
```

This array is additional to the normal report fields, not a complete report by itself. IDs
must be unique positive numeric leaves without parent/child overlap; titles must be nonempty
single lines. The runner renders `PLANNED_REQUIREMENTS.md` for human review. Its presence
alone does not prove planning completed: a draft can be written before later checks fail.
Confirm the planning task is `done` before reviewing it as a completed proposal.

## Provider errors and limits

A custom bridge should return nonzero for execution failures. Include the provider's real
error and usable reset signal in its output, avoiding credentials. The runner recognizes
common usage/rate/credit/quota/token/spending/budget limit phrases and uses the reset rules
in [Configuration](configuration.md). A valid report plus a successful process exit is not
classified as limited merely because its log discusses quotas.

Limits only count as recovered when a later execution succeeds; the wait itself does not
confirm restored credits. A provider JSON error is recognized when the inspected log text
is one JSON object containing `is_error: true` or a truthy `error` field. Mixed logs and
streaming JSON can prevent that structured check, so exit status remains important.
