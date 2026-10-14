"""CLI adapters. argv vectors only; no shell interpolation."""
import json
import re
from datetime import datetime, timezone

COMMANDS = {
    "codex": ["codex", "exec", "--sandbox", "workspace-write", "{prompt}"],
    "claude": ["claude", "-p", "{prompt}", "--output-format", "json", "--permission-mode", "acceptEdits"],
    "grok": ["grok", "-p", "{prompt}", "--output-format", "json"],
    "kimi": ["kimi", "-p", "{prompt}"],
    "hermes": ["hermes", "chat", "-q", "{prompt}"],
    "openclaw": ["openclaw", "agent", "--local", "--agent", "main", "--message", "{prompt}", "--json"],
}
ALIASES = {"claude-code": "claude", "grok-build": "grok", "kimi-code": "kimi"}
LIMIT = re.compile(r"(?:usage|rate|credit|quota|token|spending|budget)[ _-]*(?:limit|exhausted)|insufficient (?:credits|quota)|too many requests|hit your limit", re.I)


def command(agent, prompt, override=None):
    template = COMMANDS[ALIASES.get(agent, agent)] if override is None else override
    if not isinstance(template, list) or not template or not all(isinstance(x, str) for x in template):
        raise ValueError("Agent command must be a nonempty JSON array of strings")
    if not any("{prompt}" in x for x in template):
        raise ValueError("Agent command must contain {prompt}")
    return [x.replace("{prompt}", prompt) for x in template]


def provider_error(output):
    """Do not treat an agent's discussion of quota as a provider error."""
    try:
        value = json.loads(output)
    except ValueError:
        return False
    return isinstance(value, dict) and (value.get("is_error") is True or bool(value.get("error")))


def reset_delay(output, fallback, now=None):
    """Understand explicit relative or ISO signals, otherwise configured cooldown."""
    now = now or datetime.now(timezone.utc)
    try:
        data = json.loads(output)
        error = data.get('error', data) if isinstance(data, dict) else {}
        if isinstance(error, dict):
            retry = error.get('retry_after')
            reset = error.get('resets_at', error.get('reset_at'))
            if isinstance(retry, (int, float)):
                return max(1, float(retry))
            if isinstance(reset, (int, float)):
                return max(1, float(reset) - now.timestamp())
            if isinstance(reset, str):
                parsed = datetime.fromisoformat(reset.replace('Z', '+00:00'))
                if parsed.tzinfo:
                    return max(1, (parsed - now).total_seconds())
    except (ValueError, TypeError):
        pass
    match = re.search(r'(?:retry[-_ ]after|try again in)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)?\b', output, re.I)
    if match:
        unit = (match.group(2) or "s").lower()
        scale = 3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1
        return max(1, float(match.group(1)) * scale)
    match = re.search(r'(?:resets?[-_ ]at)\s*[:=]?\s*["\']?(\d{4}-\d\d-\d\dT[\d:.]+(?:Z|[+-]\d\d:\d\d))', output, re.I)
    if match:
        try:
            return max(1, (datetime.fromisoformat(match.group(1).replace("Z", "+00:00")) - now).total_seconds())
        except ValueError:
            pass
    return fallback
