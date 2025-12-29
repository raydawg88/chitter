# Chitter

**Real-time coordination for Claude Code agents.**

When Claude spawns multiple agents, they can't see each other. Agent A picks REST, Agent B picks GraphQL, you end up with incompatible systems. Chitter solves this with the **telephone game pattern**: agents run sequentially, each building on the previous agent's decisions.

## The Problem

You ask Claude to build a feature. It spawns three agents in parallel:
- Frontend agent expects `POST /api/auth/login`
- Backend agent creates `POST /api/v1/authenticate`
- Database agent designs `users.email` as primary key

Each agent does great work. But nothing fits together.

**Why?** Parallel agents are isolated processes. Agent A has no idea Agent B exists.

## The Solution: Telephone Game

Chitter enforces **sequential execution** where each agent reads what came before:

```
Agent 1 runs → writes decisions to coordination file
    ↓
Agent 2 runs → reads Agent 1's decisions → makes compatible choices
    ↓
Agent 3 runs → reads Agent 1 + 2's decisions → builds on both
    ↓
... continues through the team
```

**Result:** Agents naturally align because each one knows what the previous agents decided.

## Test Results

A/B testing with real agent teams:

| Metric | Without Chitter | With Chitter |
|--------|-----------------|--------------|
| Major conflicts | 7 | 0 |
| Minor differences | 0 | 5 |
| Alignment | ~30% | ~70% |

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/raydawg88/chitter/main/install.sh | bash
```

Restart Claude Code after installation.

## How It Works

### 1. Hooks Intercept Agent Spawns

When Claude uses the Task tool to spawn an agent, Chitter's PreToolUse hook fires:

```
[12:34:56] SESSION 7a8b9c: First agent spawn, creating workflow
[12:34:56] QUEUE: frontend-x1y2 registered at position 0
```

### 2. Sequential Mode Blocks Parallel Spawns

If Claude tries to spawn a second agent while one is running:

```
⛔ CHITTER: Sequential mode - one agent at a time

Agent 'backend-a1b2' blocked. Another agent is currently running.

✅ What to do:
1. Wait for the current agent to complete
2. Then spawn this agent

This ensures each agent can read previous agents' decisions.
```

### 3. Coordination File Passes Context

After each agent completes, their decisions are written to `~/.chitter/active/{session}.md`:

```markdown
## Agent: frontend-developer (frontend-x1y2)
**Task:** Build login UI
**Completed:** 2024-01-15 12:35:00

### Decisions Made:
- Using React Hook Form for validation
- Login endpoint: POST /api/auth/login
- Token storage: httpOnly cookies
- Error display: inline under form fields
```

The next agent reads this file before starting, so they know:
- What endpoints to expect
- What data formats were chosen
- What patterns are already established

### 4. Main Claude Orchestrates

Main Claude (the one you talk to) coordinates everything:
1. Reads team definition to know spawn order
2. Spawns agents one at a time
3. Waits for each to complete
4. Compiles outputs into unified deliverable

## Modes

Configure in `~/.chitter/config.json`:

```json
{
  "mode": "sequential",
  "max_concurrent": 1
}
```

| Mode | Behavior |
|------|----------|
| `sequential` | Block parallel spawns. One agent at a time. **(recommended)** |
| `queue` | Track spawn order, warn about parallelism, but allow it. |
| `block` | Hard block without coordination marker in prompt. |
| `track` | Silent logging only. No enforcement. |

## Team Definitions

For best results, define explicit spawn orders in your team agents. Example from `ux-team.md`:

```markdown
## Sequential Spawn Order

**Phase 1: Research Foundation (5 agents)**
1. don-norman      → Human-centered design foundation
2. jakob-nielsen   → Reads Norman, adds usability heuristics
3. steve-krug      → Reads both, adds simplicity lens
4. erika-hall      → Reads all, refines research questions
5. jared-spool     → Reads all, adds strategic alignment
```

The team orchestrator spawns agents in this order. Each agent's decisions pass to the next via the coordination file.

## Architecture

```
Main Claude spawns Agent #1
  ↓
[PreToolUse hook] → Create workflow, register agent
  ↓
Agent #1 runs → completes
  ↓
[PostToolUse hook] → Extract decisions, write to coordination file
  ↓
Main Claude spawns Agent #2
  ↓
[PreToolUse hook] → Check mode, allow if sequential slot free
  ↓
Agent #2 reads coordination file → sees Agent #1's decisions
  ↓
Agent #2 runs → completes
  ↓
... continues through team
```

## Files

```
~/.chitter/
├── hook.py            # Core logic (PreToolUse, PostToolUse)
├── config.json        # Mode configuration
├── active/            # Coordination files per session
│   └── {session}.md   # Decisions from completed agents
├── workflows/         # Workflow state (JSON)
├── queue/             # Agent queue state (JSON)
└── logs/              # Debug logs

~/.claude/
├── settings.local.json  # Hook configuration
└── CLAUDE.md            # Protocol injection
```

## Watch the Log

```bash
tail -f ~/.chitter/logs/chitter.log
```

## Works with Goldfish

[Goldfish](https://github.com/raydawg88/goldfish) gives Claude persistent memory across sessions.

Chitter handles coordination within a session.

| | Goldfish | Chitter |
|---|----------|---------|
| **Problem** | "Claude forgot everything" | "Agents built incompatible code" |
| **Solution** | Persistent project memory | Sequential execution + coordination |
| **Lifespan** | Forever | Per workflow |

Use both. Goldfish remembers. Chitter coordinates.

## MCP Tools (Optional)

Chitter also provides MCP tools for explicit control:

| Tool | Purpose |
|------|---------|
| `chitter_status` | Check active workflows |
| `chitter_workflow_start` | Manually create workflow |
| `chitter_workflow_review` | Review decisions, detect conflicts |
| `chitter_workflow_close` | Clean up workflow |

The hooks handle most cases automatically. MCP tools are for when you want explicit control.

## Known Limitations

- **Race condition on simultaneous spawn:** If two agents spawn at the exact same millisecond, both may start (solved with file locking, but edge case exists)
- **Nested agents:** Agent-to-agent Task calls don't trigger hooks (only Main Claude → Agent)
- **Not true peer communication:** Agents don't talk to each other directly. They read/write to coordination file, Main Claude orchestrates.

## Requirements

- Claude Code
- Python 3.10+

## Uninstall

```bash
~/.chitter/install.sh --uninstall
```

## License

MIT
