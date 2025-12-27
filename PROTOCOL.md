## CHITTER PROTOCOL (Real-Time Agent Coordination)

Chitter enables parallel agents to coordinate without conflicts. Use it whenever spawning multiple agents to work simultaneously.

**Goldfish = memory (persistent, across sessions)**
**Chitter = coordination (ephemeral, within workflows)**

### When Spawning Parallel Agents

**1. Before spawning, create a workflow:**
```
Call chitter_workflow_start with:
- description: Overall goal of this parallel work
- agents_planned: List of agent roles/tasks you'll spawn
```

**2. Inject the returned context into each agent's task prompt.**

The workflow_start response includes ready-to-use text. Copy it into each agent's task description so they know they're part of a coordinated workflow.

**3. After all agents complete, review:**
```
Call chitter_workflow_review(workflow_id)
```

This returns:
- Summary of all agent work
- All decisions made
- All files modified
- Any detected conflicts (file overlaps, area conflicts)

**4. Resolve conflicts before presenting results to user.**

If conflicts detected:
- Analyze which approach better serves the overall goal
- Make adjustments yourself if trivial
- Spawn a follow-up agent to reconcile if complex
- Ask user for direction if it's a significant architectural choice

**5. Close the workflow:**
```
Call chitter_workflow_close(workflow_id)
```

### What Agents Log

Agents in a Chitter workflow will call:
- `chitter_agent_start` - declares their task and areas of concern
- `chitter_decision` - logs key decisions (architecture, API, data model, interface, dependency choices)
- `chitter_complete` - marks done with summary and files modified

### Conflict Detection

Chitter auto-detects:
- **File conflicts** (high severity): Multiple agents modified same file
- **Area overlaps** (medium severity): Multiple agents made decisions in same area

Semantic conflicts (REST vs GraphQL, different architectural approaches) require your analysis.

### Example Workflow

```
You: "Build user authentication with frontend and backend"

1. chitter_workflow_start(
     description="User authentication system",
     agents_planned=["Frontend auth UI", "Backend auth API"]
   )

2. Spawn Agent A: "Build frontend login/signup forms. [INJECT CHITTER CONTEXT]"
   Spawn Agent B: "Build backend auth endpoints. [INJECT CHITTER CONTEXT]"

3. [Agents work, logging decisions to Chitter]

4. chitter_workflow_review(workflow_id)
   -> Shows: Agent A expects POST /api/auth/login
   -> Shows: Agent B created POST /api/v1/auth/login
   -> CONFLICT: endpoint path mismatch

5. Resolve: Update frontend to use /api/v1/auth/login

6. chitter_workflow_close(workflow_id)
```

### When NOT to Use Chitter

- Single agent tasks (no coordination needed)
- Sequential agent work (context passes naturally)
- Research/exploration tasks (no decisions to conflict)

Use Chitter when parallel agents might make incompatible decisions.
