# Adapter interface references

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
