# Chitter

**Stop your Claude Code agents from building incompatible systems.**

## The Problem

You ask Claude Code to build a feature. It spawns three agents in parallel:
- Frontend agent builds a login form expecting `POST /api/auth/login`
- Backend agent creates endpoints at `POST /api/v1/authenticate`
- Database agent designs a schema with `users.email` as the primary key

Each agent does great work. But when they're done, nothing fits together.

**Why?** Parallel agents can't see each other. They're spawned into isolated processes. Agent A has no idea Agent B exists, let alone what decisions it's making.

You end up playing merge conflict referee for code that was supposed to work together from the start.

## The Solution

Chitter gives your agents a shared decision log.

```
Before: Agents work in isolation → conflicting decisions → you clean up the mess

After:  Agents log decisions → Main Claude reviews → conflicts caught before code is written
```

It's not real-time chat between agents. It's simpler: **agents log, Main Claude coordinates.**

When you spawn parallel agents with Chitter:
1. Each agent declares what they're working on and logs key decisions
2. After all agents complete, you review the decision log
3. Conflicts surface immediately (same file modified, incompatible API designs, etc.)
4. You resolve conflicts before presenting results to the user

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/raydawg88/chitter/main/install.sh | bash
```

Restart Claude Code after installation.

## How It Works

**Before spawning agents:**
```
chitter_workflow_start(
  description="Build user authentication",
  agents_planned=["Frontend login UI", "Backend auth API", "Database schema"]
)
```

This returns context to inject into each agent's task. Agents then know they're part of a coordinated workflow and will log their decisions.

**After agents complete:**
```
chitter_workflow_review(workflow_id)
```

Returns:
```
## Decisions Made
- [Frontend] Expects POST /api/auth/login with {email, password}
- [Backend] Created POST /api/v1/authenticate with {username, password}
- [Database] Primary key is users.id, email is unique constraint

## CONFLICTS DETECTED
🔴 API mismatch: Frontend expects /api/auth/login, Backend created /api/v1/authenticate
🟡 Field mismatch: Frontend sends "email", Backend expects "username"
```

Now you fix the conflicts *before* the code is presented as "done."

## Works with Goldfish

[Goldfish](https://github.com/raydawg88/goldfish) gives Claude Code persistent memory across sessions—so it remembers what you built last week, what decisions you made, and where you left off.

Chitter handles the other half: **coordination within a session** when multiple agents work in parallel.

| | Goldfish | Chitter |
|---|----------|---------|
| **Problem** | "Claude forgot everything from yesterday" | "My parallel agents built incompatible code" |
| **Solution** | Persistent project memory | Shared decision log for parallel work |
| **Lifespan** | Forever | Cleared when workflow closes |

Use both. Goldfish remembers. Chitter coordinates.

## The Key Insight

The real problem isn't "agents can't talk to each other."

It's that **agents have no shared context.** They don't know what the overall goal is, who else is working, or what decisions matter.

Chitter doesn't try to make agents chat. It gives Main Claude (the coordinator) visibility into what each agent decided, so conflicts get caught at review time—not after you've already merged incompatible code.

## Tools

| Tool | Who Calls It | What It Does |
|------|--------------|--------------|
| `chitter_status` | Main Claude | Check for active workflows |
| `chitter_workflow_start` | Main Claude | Create coordination context |
| `chitter_workflow_review` | Main Claude | Review decisions, detect conflicts |
| `chitter_workflow_close` | Main Claude | Clean up when done |
| `chitter_agent_start` | Agents | Declare task and areas of concern |
| `chitter_decision` | Agents | Log a key decision |
| `chitter_complete` | Agents | Mark task complete |

## Requirements

- Claude Code
- Python 3.10+
- uv (installed automatically)

## Uninstall

```bash
~/.chitter/install.sh --uninstall
```

## License

MIT
