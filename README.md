# Chitter

**Stop your Claude Code agents from building incompatible systems.**

## The Problem

You ask Claude Code to build a feature. It spawns three agents in parallel:
- Frontend agent builds a login form expecting `POST /api/auth/login`
- Backend agent creates endpoints at `POST /api/v1/authenticate`
- Database agent designs a schema with `users.email` as the primary key

Each agent does great work. But when they're done, nothing fits together.

**Why?** Parallel agents can't see each other. They're spawned into isolated processes. Agent A has no idea Agent B exists, let alone what decisions it's making.

## The Solution

Chitter automatically tracks parallel agents and surfaces coordination context.

**No action required from you or Claude.** Hooks intercept Task calls and:
1. Detect when multiple agents are running in parallel
2. Auto-create a coordination workflow
3. Show context to Claude before each agent spawns
4. Log completions and extract decisions
5. Surface potential conflicts when work finishes

```
Before: Agents work in isolation → conflicting decisions → you clean up

After:  Hooks track everything → context injected → conflicts visible
```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/raydawg88/chitter/main/install.sh | bash
```

Restart Claude Code after installation.

## How It Works

When Claude spawns a second parallel agent, you'll see in the log:

```
[12:34:56] PARALLEL DETECTED: backend-a1b2 joining 1 active agents
[12:34:56] AGENT REGISTERED: backend-a1b2 (backend-developer) - Build auth API
```

And Claude sees this context before the Task executes:

```
⚡ CHITTER: Parallel work detected
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Workflow: a1b2c3d4
Active agents:
  • frontend-x1y2 (frontend-developer): Building login UI
  • backend-a1b2 (backend-developer): [THIS AGENT]

💡 Consider including in this agent's prompt:
   "Other agents are working on this project. Coordinate on shared interfaces."
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

When all agents complete, decisions are extracted and surfaced:

```
📋 CHITTER: Parallel work complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Decisions detected:
[frontend-x1y2] Created login form using React Hook Form
[backend-a1b2] Implemented JWT auth with /api/v1/auth endpoints

💡 Review for conflicts with: chitter_workflow_review("a1b2c3d4")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Modes

Configure in `~/.chitter/config.json`:

```json
{
  "mode": "nudge"
}
```

| Mode | Behavior |
|------|----------|
| `track` | Silent logging only. No output to Claude. |
| `nudge` | Track + show context to Claude. **(default)** |
| `block` | Hard block Task calls without active workflow. |

## Watch the Log

```bash
tail -f ~/.chitter/chitter.log
```

## Works with Goldfish

[Goldfish](https://github.com/raydawg88/goldfish) gives Claude Code persistent memory across sessions—so it remembers what you built last week.

Chitter handles coordination within a session when multiple agents work in parallel.

| | Goldfish | Chitter |
|---|----------|---------|
| **Problem** | "Claude forgot everything" | "Parallel agents built incompatible code" |
| **Solution** | Persistent project memory | Automatic parallel tracking |
| **Lifespan** | Forever | Per workflow |

Use both. Goldfish remembers. Chitter coordinates.

## MCP Tools (Optional)

Chitter also provides MCP tools for explicit control:

| Tool | Purpose |
|------|---------|
| `chitter_status` | Check active workflows |
| `chitter_workflow_start` | Manually create coordination context |
| `chitter_workflow_review` | Review decisions, detect conflicts |
| `chitter_workflow_close` | Clean up workflow |

The hooks handle most cases automatically. Use MCP tools when you want explicit control.

## Requirements

- Claude Code
- Python 3.10+

## Uninstall

```bash
~/.chitter/install.sh --uninstall
```

## License

MIT
