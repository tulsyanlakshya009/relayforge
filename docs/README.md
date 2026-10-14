# RelayForge documentation

This documentation describes **RelayForge 0.1.0**, last reviewed against the implementation
on **2026-10-14**. It covers the shipped command-line product. Features described as
limitations or future possibilities are not promises of current behavior.

## Product overview

RelayForge addresses a practical problem: a coding agent can stop before a project is
finished, leaving the developer to reconstruct the next step. RelayForge keeps the approved
work, its status and verification evidence outside the agent's conversation. On the next
run, it builds a new bounded prompt from that state and the existing workspace.

It is intended for individual developers who already have an agent CLI and want a local,
reviewable development process. The approach combines upfront requirements and design
with small implementation increments, prioritized repairs and repeated verification.
It does not implement Scrum roles, sprint planning or a full project-management platform.

The developer supplies and approves scope, configures meaningful tests, reviews results,
and resolves blockers that require human judgment. The agent performs bounded work and
reports evidence. RelayForge schedules, records and verifies the work according to the
configured workflow.

## Choose a reading path

- **First-time user:** [Getting started](getting-started.md) → [Workflow](workflow.md) → [Operations](operations.md).
- **Setting up an agent:** [Agent setup](adapters.md) → [Configuration](configuration.md) → [Getting started](getting-started.md).
- **Running unattended:** [Operations](operations.md) → [Scheduling](scheduling.md).
- **Building an adapter or contributing:** [Architecture](architecture.md) → [CLI reference](cli-reference.md) → [Agent setup](adapters.md).

## Terminology

| Term | Meaning |
|---|---|
| Managed project | The application repository RelayForge is asked to develop |
| RelayForge repository | The source checkout from which the orchestrator is installed |
| Requirement | An approved, numbered leaf item such as `1.5` |
| Requirement group | Items sharing the first numeric component, such as group `1` |
| Work item | A queued feature, human change, bug, plan or test gate |
| Tick | One scheduling pass that executes at most one work item |
| Attempt | One agent execution with a fresh report path and random identifier |
| Test gate | Group-level verification item such as `TEST-1` |
| Cooldown | A persisted timestamp before which the worker does not launch another item |
| Verified completion | Accepted agent report plus success of any configured independent checks |

## Supported scope

macOS and Linux with Python 3.9 or later are supported by the local runner. No agent CLI
is bundled. Six adapter command templates are included; actual provider behavior depends
on CLI versions and account setup. Windows is not supported because the runner uses POSIX
locking and process groups.

Runtime data stays in the managed project's `.relayforge` directory. There is no hosted
RelayForge account, server or analytics integration. The selected agent may transmit code
and prompts to its provider under its own configuration.

## Documents versus generated project records

The files in this documentation directory explain the **RelayForge product**. A managed
project receives separate records including `CURRENT.md`, `SYSTEM_DESIGN.md` and `HISTORY.md`.
Those records describe the application being developed. `CURRENT.md` is assembled from
completed task summaries; its completeness depends on report quality. It is not an
independent documentation-generation service.
