# Chitter

Real-time coordination for Claude Code agents.

**The problem:** When Claude Code spawns parallel agents, they can't see each other. Agent A picks REST, Agent B picks GraphQL. You end up with incompatible systems.

**The solution:** Chitter forces agents to log their decisions. Main Claude reviews after parallel work completes, catches conflicts before they become problems.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rayhernandez/chitter/main/install.sh | bash
```

Or clone and run:

```bash
git clone https://github.com/rayhernandez/chitter.git
cd chitter
./install.sh
```

Restart Claude Code after installation.

## How It Works

```
1. Main Claude spawns parallel agents
2. Agents log decisions to Chitter (via MCP tools)
3. Main Claude reviews after completion
4. Conflicts caught and resolved before presenting results
```

### Chitter vs Goldfish

| | Goldfish | Chitter |
|---|----------|---------|
| Purpose | Memory | Coordination |
| Lifespan | Forever | Per workflow |
| Scope | Across sessions | Within parallel work |

They complement each other. Goldfish remembers. Chitter coordinates.

## Tools

| Tool | Called By | Purpose |
|------|-----------|---------|
| `chitter_status` | Main Claude | Check active workflows |
| `chitter_workflow_start` | Main Claude | Create coordination context |
| `chitter_workflow_review` | Main Claude | Review after agents complete |
| `chitter_workflow_close` | Main Claude | Clean up workflow |
| `chitter_agent_start` | Agents | Declare task and areas |
| `chitter_decision` | Agents | Log key decisions |
| `chitter_complete` | Agents | Mark task done |

## Workflow

```
# Before spawning agents
chitter_workflow_start(
  description="Build user auth",
  agents_planned=["Frontend", "Backend"]
)

# Inject returned context into each agent's task prompt
# Spawn agents in parallel...

# After all agents complete
chitter_workflow_review(workflow_id)
# -> Shows all decisions, detects conflicts

# Resolve any conflicts, then:
chitter_workflow_close(workflow_id)
```

## Uninstall

```bash
~/.chitter/install.sh --uninstall
```

Or if you have the repo:

```bash
./install.sh --uninstall
```

## Requirements

- Python 3.10+
- Claude Code
- MCP SDK (installed automatically)

## License

MIT
