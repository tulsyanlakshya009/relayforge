# Running unattended

## Cron

Install RelayForge into a virtualenv, run `relayforge --project /absolute/path schedule`,
and paste its entry into `crontab -e`. Set an explicit PATH that includes your installed
agent binaries. Cron invokes `tick`, so a machine restart resumes from SQLite and a
quota cooldown causes a cheap no-op rather than another model call. An existing
foreground worker and cron share the same project lock.

Use one worker per managed repository. Keep the machine awake. Authentication must be
completed before installing a job. Native agent tool policies must allow the intended
commands without unexpected interactive prompts. Schedule output is a template; no
system service is installed automatically.

## macOS launchd template

Save as an operator-owned LaunchAgent after replacing every path. Use the virtualenv's
installed executable, not a relative source checkout.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.relayforge.my-app</string>
  <key>ProgramArguments</key><array>
    <string>/absolute/path/relayforge/.venv/bin/relayforge</string>
    <string>--project</string><string>/absolute/path/my-app</string><string>tick</string>
  </array>
  <key>StartInterval</key><integer>60</integer>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/absolute/path/agent/bin</string>
  </dict>
  <key>StandardOutPath</key><string>/absolute/path/my-app/.relayforge/scheduler.log</string>
  <key>StandardErrorPath</key><string>/absolute/path/my-app/.relayforge/scheduler.log</string>
</dict></plist>
```

## Linux systemd

Create a user service with an absolute `ExecStart=/path/to/relayforge --project /path/to/app tick`
and an explicit agent PATH. Trigger it with a user timer using `OnCalendar=*-*-* *:*:00`.
A single tick can run for up to the configured agent/test timeout. Use a timer rather than
`Restart=always` so idle or blocked work does not busy-loop. Use trusted local execution;
public CI runners should not hold subscription credentials.

## Operations

- `status` reports task states and Unix `resume_at` timestamp.
- Logs are under `.relayforge/runs`; inspect agent and test logs for blockers.
- `retry ID` clears an unfinished item's ordinary retry counter after a fix.
- `pause`/`resume` apply between work items because they acquire the runner lock.
- Back up the target code and `.relayforge` together. State is not synchronized via Git.
- Review local logs before sharing; native agent output can contain sensitive project data.
- Logs currently have no automatic retention policy; periodically archive older attempt directories.
