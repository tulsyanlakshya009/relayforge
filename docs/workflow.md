# Workflow rules

RelayForge stores the executable queue in SQLite. Markdown requirements and changes are
inputs to explicit imports; generated checklists are views of the queue.

## Requirement imports

An item such as `- [ ] 1.5 Save account settings; reject invalid fields` creates a feature
work item with ID and target `1.5`. Its entire single-line title contains its acceptance criteria.
IDs contain positive numeric components without leading zeroes. `1.2` precedes `1.10`.
Blank titles, duplicate IDs, checked input items and malformed checkbox lines are rejected.
Titles are limited to 16,000 characters.

A checkbox parent and its checkbox child cannot coexist. Use `## 1. Accounts` as a heading
and `1.1`, `1.2` as leaves. Deeper leaves such as `1.2.1` are supported, but their top-level
group is still `1`. Headings and other prose are not executable tasks.

Reimporting identical IDs and titles is idempotent. New IDs add work and invalidate a
previously passed gate for their group. Changing an existing title requires a change entry.
Removing an item from the Markdown file **does not remove it from the queue**. There is
no supported task deletion, cancellation or ID-renumbering command in this release.

## Queue selection

The worker selects a pending eligible item using these rules:

1. Bugs come before all other kinds of work, across requirement groups.
2. Within bugs, lower numeric priority wins; ties use the numeric target, then item ID.
3. Otherwise, planning items are eligible globally, while features, changes and gates
   stay in the earliest group without a completed `TEST-<group>` item.
4. Non-bug priorities are planning `0`, gates `20`, human changes `50`, and features `100`.
   Gates become eligible only when every feature, change and bug in their group is done.
5. Remaining ties use numeric target, then item ID.

The CLI does not expose arbitrary dependencies or feature-priority editing. Top-level
groups provide the supported ordering boundary. A new change in completed group `1`
invalidates `TEST-1`, making group `1` the active group again before ordinary later work.

### Example: a defect after completion

Suppose `1.1` through `1.7` and `TEST-1` are done, and `2.1` is pending. Reporting a bug
against `1.5` adds a repair and returns `TEST-1` to pending. The next selection is the bug,
then `TEST-1` once group `1` has no unfinished items, then `2.1`.

Scheduling happens between attempts. A new item cannot preempt an agent already running.
Commands that modify the queue also need the project lock.

## Human requirement changes

Append a new entry to `REQUIREMENT_CHANGES.md` after reviewing implemented work:

```markdown
- [ ] CHG-001 | 1.5 | Add timezone selection; validate unknown zones and preserve saved settings
```

Then import it explicitly:

```bash
relayforge --project /absolute/path/to/my-app changes
```

The target must match an existing feature's exact ID, not just its group heading. Change
IDs start with `CHG-` and contain letters, digits, underscores or hyphens. Each entry uses
an unchecked checkbox and the spaced ` | ` separators shown above.

Imported ID, target and title are immutable. Reimporting identical entries has no effect;
append a new ID for the next amendment. The worker neither imports this file automatically
nor marks its entries checked. Use `CHECKLIST.md` to track execution. If any entry in an
import is invalid, that import's database changes roll back.

## Bugs and repairs

```bash
relayforge --project /absolute/path/to/my-app bug 1.5 "Settings are lost after restarting"
relayforge --project /absolute/path/to/my-app bug 1.5 "Settings are lost after restarting" --priority 1
```

A bug target can be an existing feature ID or an existing top-level group. The command
returns `BUG-<hash>`. Exact target/title pairs deduplicate. Reporting the same resolved bug
reopens it and resets its attempts. Reporting a pending or blocked duplicate does not
change its existing priority or unblock it; use `retry ID` for an unfinished blocked item.
To set a priority, supply it when first reporting the bug.

Accepted completion reports may also contain discovered bugs. A normal feature can
complete while follow-up defects are queued. A gate that reports defects does not pass.
A failing independent check creates a repair unless the current item is already a repair,
in which case the same repair is retried within its attempt budget.

## Completion and test gates

For a non-planning item to complete, the agent must exit successfully, provide a fresh
report matching the item and attempt, and include a nonempty summary and test-evidence
list. Every configured independent verification command must then exit successfully.
These commands run after features, human changes, bugs and gates.

After all non-planning work in a group completes, the worker creates `TEST-1`, `TEST-2`,
and so on. The gate asks the agent to cover all approved features, including relevant unit,
integration, boundary, invalid-input and regression cases. At least one independent test
command is required for a gate to pass. The runner does not calculate coverage or check
that every acceptance criterion has a corresponding assertion.

An empty verification configuration can allow feature completion based on the agent's
report, but it cannot pass the group's gate. Configure meaningful tests before implementation.

## Task states and tick outcomes

| Persisted task state | Meaning |
|---|---|
| `pending` | Eligible later, including work returned after a failed or limited attempt |
| `running` | An attempt has started |
| `done` | Completion was accepted; a gate or bug can later reopen |
| `blocked` | Agent reported a blocker, protected input changed, or retry budget was exhausted |

`failed`, `limited`, `waiting`, `paused` and `idle` are tick outcomes, not task states.
An ordinary failed attempt returns its task to pending. A recognized limit also returns it
to pending, saves `resume_at`, and does not consume its ordinary retry budget.

The foreground `run` command stops on a `blocked` outcome. It is not a global prohibition
on all future work: later scheduled ticks may execute other eligible pending items. A group
gate remains ineligible while that group has unfinished items, including blocked bugs.
Use `pause` if you want to stop future execution across the entire project.
