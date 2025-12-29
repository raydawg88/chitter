<h1 align="center">
  <br>
  🐦 Chitter
  <br>
</h1>

<h3 align="center">The Telephone Game for AI Agents</h3>

<p align="center">
  <strong>Stop your Claude Code agents from building incompatible systems.</strong>
</p>

<p align="center">
  <a href="#the-problem">The Problem</a> •
  <a href="#the-solution">The Solution</a> •
  <a href="#results">Results</a> •
  <a href="#install">Install</a> •
  <a href="#how-it-works">How It Works</a>
</p>

---

## The Problem

You ask Claude to build a feature. It spawns three agents:

```
Frontend Agent: "I'll use POST /api/auth/login"
Backend Agent:  "I'll create POST /api/v1/authenticate"
Database Agent: "I'll make users.email the primary key"
```

Each agent does great work. **But nothing fits together.**

Why? Because parallel agents can't see each other. They're isolated processes. Agent A has no idea Agent B exists, let alone what decisions it's making.

The result: you spend hours reconciling incompatible code, mismatched APIs, and conflicting architectural decisions.

## The Solution

**Chitter implements the telephone game pattern.**

Instead of parallel chaos, agents run sequentially. Each one reads what came before and builds on it:

```
Agent 1 runs → writes decisions
    ↓
Agent 2 runs → reads Agent 1's decisions → makes compatible choices
    ↓
Agent 3 runs → reads Agent 1+2's decisions → builds on both
    ↓
... knowledge accumulates through the team
```

It's not magic. It's just making sure agents know what other agents decided.

## Results

We ran A/B tests with real agent teams:

| Metric | Without Chitter | With Chitter |
|--------|-----------------|--------------|
| **Major Conflicts** | 7 | 0 |
| **API Mismatches** | 3 | 0 |
| **Schema Conflicts** | 2 | 0 |
| **Overall Alignment** | ~30% | ~70% |

**Zero major conflicts.** Agents naturally align because each one knows what came before.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/raydawg88/chitter/main/install.sh | bash
```

Restart Claude Code. That's it.

## How It Works

### 1. Sequential Execution

When Claude tries to spawn agents in parallel, Chitter blocks it:

```
⛔ CHITTER: Sequential mode - one agent at a time

Agent 'backend-dev' blocked. Another agent is currently running.

✅ Wait for the current agent to complete, then spawn this one.
```

This forces the telephone game pattern. No parallel chaos.

### 2. Context Injection

After each agent completes, their decisions are captured. The next agent gets them **injected directly into their prompt**:

```
Task: Spawn backend-developer with prompt:
"Build the auth API.

PREVIOUS DECISIONS:
- Frontend expects POST /api/auth/login
- Response format: { token, user: { id, email, name } }
- Error format: { error: string, code: number }

Build an API that matches these expectations."
```

No hoping agents read a file. The context is forced in.

### 3. Compression Between Phases

10 agents outputting 300 words each = token bomb.

Chitter tells the orchestrator to compress each phase into a 300-500 word summary before passing to the next phase. Later agents get the signal, not the noise.

### 4. Structured Output Templates

Every agent outputs structured decisions:

```markdown
### Decision
Use JWT tokens stored in httpOnly cookies

### Why This Choice
- httpOnly prevents XSS token theft
- Cookies auto-attach to requests (no client-side token handling)
- Refresh token rotation built into cookie expiry

### Trade-off
Can't access token from JavaScript (intentional)
```

The **WHY** is mandatory. Decisions without rationale are useless to the next agent.

## The Telephone Game in Action

Here's a real UX team execution:

```
PHASE 1: RESEARCH
├── don-norman      → "The real problem is cognitive load, not missing features"
├── jakob-nielsen   → "Heuristic evaluation shows 3 violations"
├── steve-krug      → "Users shouldn't have to think about navigation"
└── ... (7 more researchers)

    ↓ [Orchestrator compresses to 400 words]

PHASE 2: DESIGN PHILOSOPHY
├── dieter-rams     → "Less but better - remove the settings panel entirely"
├── jony-ive        → "The primary action should be unmissable"
└── ... (4 more philosophers)

    ↓ [Compressed summary injected]

PHASE 3: VISUAL LANGUAGE
├── paul-rand       → "Logo: geometric, single color, 48px minimum"
├── massimo-vignelli → "12-column grid, 8px baseline"
└── ... (4 more designers)

    ↓ [Compressed summary injected]

PHASE 4: UI SPECIFICATION
├── rauno-freiberg  → "Hero: fade-in 400ms ease-out, stagger children 50ms"
├── dann-petty      → "CTA: #2563EB, 16px padding, 200ms hover transition"
└── ... (7 more UI designers)
```

Each phase builds on the last. By Phase 4, the UI designers know:
- What problem they're solving (Phase 1)
- What principles to follow (Phase 2)
- What visual language to use (Phase 3)

No conflicts. No mismatches. Just aligned execution.

## Configuration

Default mode is `sequential` (recommended). Other modes:

```json
// ~/.chitter/config.json
{
  "mode": "sequential",  // One agent at a time (recommended)
  "max_concurrent": 1
}
```

| Mode | Behavior |
|------|----------|
| `sequential` | Block parallel spawns. Telephone game enforced. |
| `queue` | Track order, warn about parallelism, but allow it. |
| `track` | Silent logging only. No enforcement. |

## Watch It Work

```bash
tail -f ~/.chitter/logs/chitter.log
```

You'll see:
```
[12:34:56] SESSION abc123: Agent don-norman registered at position 0
[12:34:57] SESSION abc123: Agent don-norman complete, 4 decisions captured
[12:34:58] SESSION abc123: Agent jakob-nielsen registered at position 1
[12:34:58] SESSION abc123: jakob-nielsen reading don-norman's decisions
...
```

## Works With Goldfish

[Goldfish](https://github.com/raydawg88/goldfish) gives Claude persistent memory across sessions.

Chitter handles coordination within a session.

| | Goldfish | Chitter |
|---|----------|---------|
| **Problem** | "Claude forgot our decisions from yesterday" | "Parallel agents made conflicting decisions today" |
| **Solution** | Persistent project memory | Sequential execution + context injection |
| **Lifespan** | Forever | Per session |

Use both. **Goldfish remembers. Chitter coordinates.**

## Requirements

- Claude Code
- Python 3.10+

## Uninstall

```bash
~/.chitter/install.sh --uninstall
```

## Why "Chitter"?

Birds coordinate through calls. Each one hears what came before and adds to it. That's the telephone game.

Your AI agents should work the same way.

---

<p align="center">
  <strong>Stop debugging agent conflicts. Start shipping.</strong>
</p>

<p align="center">
  <a href="https://github.com/raydawg88/chitter">GitHub</a> •
  <a href="https://github.com/raydawg88/goldfish">Goldfish (Memory)</a>
</p>
