# Approved requirements

## 1. Storage

- [ ] 1.1 Define task IDs, titles and completion state; document the storage format and interfaces
- [ ] 1.2 Save and reload task records; preserve all fields across application restart
- [ ] 1.3 Reject malformed storage without overwriting it; provide a clear recovery error

## 2. Commands

- [ ] 2.1 Create a task with a nonblank title; reject whitespace-only titles with a clear error
- [ ] 2.2 List tasks and mark an existing task complete; preserve completion across restart and reject unknown IDs
