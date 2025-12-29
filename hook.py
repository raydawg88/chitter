#!/usr/bin/env python3
"""
Chitter Hook Helper
Handles PreToolUse and PostToolUse logic for Task tool coordination.

v2.0 - Queue-based sequential execution ("telephone game" pattern)
Agents spawn together but execute one at a time, each building on previous.

Usage:
  python3 hook.py pre <tool_input_json>
  python3 hook.py post <tool_input_json> <tool_output>
"""

import json
import os
import sys
import fcntl
from datetime import datetime
from pathlib import Path

CHITTER_DIR = Path.home() / ".chitter"
WORKFLOWS_DIR = CHITTER_DIR / "workflows"
ACTIVE_DIR = CHITTER_DIR / "active"  # Coordination files for active sessions
QUEUE_DIR = CHITTER_DIR / "queues"   # Queue state per session
LOG_FILE = CHITTER_DIR / "chitter.log"
CONFIG_FILE = CHITTER_DIR / "config.json"

# Ensure directories exist
WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_DIR.mkdir(parents=True, exist_ok=True)

# The magic string agents must read
COORDINATION_INSTRUCTION = "CHITTER_COORDINATION"

# Default config
DEFAULT_CONFIG = {
    # Modes:
    #   "sequential" - Blocks parallel agents. Main Claude must spawn one at a time.
    #   "queue"      - Tracks order, warns on parallel, but doesn't block.
    #   "block"      - Original mode: blocks without coordination marker.
    #   "track"      - Just logs, no blocking.
    "mode": "sequential",
    "max_concurrent": 1,  # For sequential mode: how many agents can run at once
}

# Known project roots to look for
PROJECT_ROOTS = [
    "/Goldfish/personal/",
    "/Goldfish/work/",
    "/Projects/",
]


def extract_project_from_prompt(prompt: str) -> tuple[str, str]:
    """Try to extract project name and path from file paths mentioned in the prompt."""
    import re

    real_path_patterns = [
        r"(/Users/[^\s\"']+)",
        r"(/home/[^\s\"']+)",
        r"([^\s\"']*Goldfish[^\s\"']+)",
        r"([^\s\"']*Projects/[^\s\"']+)",
    ]

    first_path = ""
    for pattern in real_path_patterns:
        match = re.search(pattern, prompt)
        if match:
            first_path = match.group(1)
            break

    for root in PROJECT_ROOTS:
        pattern = re.escape(root) + r"([^/\s\"']+)"
        match = re.search(pattern, prompt)
        if match:
            return match.group(1), first_path

    folder_match = re.search(r"/Users/[^/]+/[^/]+/([^/\s\"']+)", prompt)
    if folder_match:
        folder = folder_match.group(1)
        if folder not in ["Library", "Documents", "Desktop", "Downloads", ".claude", ".chitter"]:
            return folder, first_path

    return "unknown", first_path


def log(message: str) -> None:
    """Append to log file."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def get_config() -> dict:
    """Load config or return defaults."""
    if CONFIG_FILE.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text())}
        except:
            pass
    return DEFAULT_CONFIG


# ============================================================================
# QUEUE MANAGEMENT
# ============================================================================

def get_queue_file(session_id: str) -> Path:
    """Get the queue state file for a session."""
    return QUEUE_DIR / f"{session_id}.json"


def get_lock_file(session_id: str) -> Path:
    """Get the lock file for a session's queue."""
    return QUEUE_DIR / f"{session_id}.lock"


class QueueLock:
    """File-based lock for queue operations."""
    def __init__(self, session_id: str):
        self.lock_file = get_lock_file(session_id)
        self.fd = None

    def __enter__(self):
        self.lock_file.touch(exist_ok=True)
        self.fd = open(self.lock_file, 'w')
        fcntl.flock(self.fd, fcntl.LOCK_EX)  # Exclusive lock, blocks until acquired
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.fd.close()
        return False


def get_queue(session_id: str) -> dict:
    """Get or create queue state for a session."""
    queue_file = get_queue_file(session_id)
    if queue_file.exists():
        try:
            return json.loads(queue_file.read_text())
        except:
            pass
    return {
        "session_id": session_id,
        "agents": [],  # List of {id, type, task, status, position, queued_at}
        "current_position": 0,  # Which position is currently allowed to run
        "created_at": datetime.now().isoformat()
    }


def save_queue(session_id: str, queue: dict) -> None:
    """Save queue state."""
    queue_file = get_queue_file(session_id)
    queue_file.write_text(json.dumps(queue, indent=2))


def add_to_queue(session_id: str, agent_id: str, agent_type: str, task: str) -> int:
    """Add an agent to the queue. Returns its position (0-indexed)."""
    with QueueLock(session_id):
        queue = get_queue(session_id)

        # Check if already in queue (retry case)
        for agent in queue["agents"]:
            if agent["id"] == agent_id:
                return agent["position"]

        position = len(queue["agents"])
        queue["agents"].append({
            "id": agent_id,
            "type": agent_type,
            "task": task,
            "status": "queued",
            "position": position,
            "queued_at": datetime.now().isoformat()
        })
        save_queue(session_id, queue)
        log(f"[{session_id}] QUEUE: Added {agent_type} at position {position}")
        return position


def get_queue_position(session_id: str, agent_id: str) -> int | None:
    """Get an agent's position in the queue."""
    queue = get_queue(session_id)
    for agent in queue["agents"]:
        if agent["id"] == agent_id:
            return agent["position"]
    return None


def is_turn(session_id: str, agent_id: str, max_concurrent: int = 1) -> bool:
    """Check if it's this agent's turn to run."""
    queue = get_queue(session_id)
    position = get_queue_position(session_id, agent_id)

    if position is None:
        return True  # Not in queue, allow

    # Count how many agents before this one are still not complete
    # "blocked" and "queued" both count as "not done yet"
    agents_ahead = 0
    for agent in queue["agents"]:
        if agent["position"] < position and agent["status"] not in ("complete",):
            agents_ahead += 1

    # It's our turn if fewer than max_concurrent agents are ahead
    return agents_ahead < max_concurrent


def mark_agent_running(session_id: str, agent_id: str) -> None:
    """Mark an agent as currently running."""
    with QueueLock(session_id):
        queue = get_queue(session_id)
        for agent in queue["agents"]:
            if agent["id"] == agent_id:
                agent["status"] = "running"
                agent["started_at"] = datetime.now().isoformat()
                break
        save_queue(session_id, queue)


def mark_agent_complete(session_id: str, agent_id: str) -> bool:
    """Mark an agent as complete. Returns False if agent wasn't running (was blocked)."""
    with QueueLock(session_id):
        queue = get_queue(session_id)
        for agent in queue["agents"]:
            if agent["id"] == agent_id:
                # Only mark complete if it was actually running (not blocked)
                if agent["status"] != "running":
                    log(f"[{session_id}] QUEUE: {agent_id} POST fired but status was '{agent['status']}' - not marking complete")
                    return False
                agent["status"] = "complete"
                agent["completed_at"] = datetime.now().isoformat()
                break
        save_queue(session_id, queue)
        log(f"[{session_id}] QUEUE: {agent_id} complete")
        return True


def mark_agent_blocked(session_id: str, agent_id: str) -> None:
    """Mark an agent as blocked (waiting in queue)."""
    with QueueLock(session_id):
        queue = get_queue(session_id)
        for agent in queue["agents"]:
            if agent["id"] == agent_id:
                agent["status"] = "blocked"
                break
        save_queue(session_id, queue)


def get_agents_ahead(session_id: str, agent_id: str) -> list[dict]:
    """Get list of agents ahead of this one that aren't complete."""
    queue = get_queue(session_id)
    position = get_queue_position(session_id, agent_id)

    if position is None:
        return []

    ahead = []
    for agent in queue["agents"]:
        if agent["position"] < position and agent["status"] not in ("complete",):
            ahead.append(agent)
    return ahead


def get_completed_agents(session_id: str) -> list[dict]:
    """Get list of completed agents in order."""
    queue = get_queue(session_id)
    completed = [a for a in queue["agents"] if a["status"] == "complete"]
    return sorted(completed, key=lambda x: x["position"])


# ============================================================================
# COORDINATION FILE
# ============================================================================

def get_coordination_file(session_id: str) -> Path:
    """Get the path to the coordination file for a session."""
    return ACTIVE_DIR / f"{session_id}.md"


def write_coordination_state(session_id: str, workflow: dict, new_agent_type: str, new_agent_task: str) -> None:
    """Write current coordination state to the session's coordination file."""
    coord_file = get_coordination_file(session_id)

    agents = workflow.get("agents", {})
    completed_agents = [(aid, a) for aid, a in agents.items() if a.get("status") == "complete"]

    # Get queue to show proper positions
    queue = get_queue(session_id)
    agent_positions = {a["id"]: a["position"] for a in queue.get("agents", [])}

    # Sort completed agents by position
    completed_agents_sorted = sorted(completed_agents, key=lambda x: agent_positions.get(x[0], 99))
    next_position = len(completed_agents_sorted) + 1

    lines = [
        f"# CHITTER COORDINATION - Session {session_id}",
        "",
        f"**Read this before starting your work.**",
        "",
        f"## Telephone Game Status",
        f"",
        f"| # | Agent | Status |",
        f"|---|-------|--------|",
    ]

    # Show completed agents in the status table
    for aid, agent in completed_agents_sorted:
        pos = agent_positions.get(aid, "?")
        agent_type = agent.get('subagent_type', 'unknown')
        lines.append(f"| {pos + 1} | {agent_type} | ✅ Complete |")

    lines.append(f"| {next_position} | **{new_agent_type}** | 🔄 Running (YOU) |")
    lines.append("")

    lines.extend([
        "## Your Task",
        f"You are: **{new_agent_type}** (Agent #{next_position})",
        f"Task: {new_agent_task}",
        "",
    ])

    # Completed agents and their decisions (the "telephone" context)
    if completed_agents_sorted:
        lines.append("## Previous Agents (build on their work)")
        lines.append("")
        for aid, agent in completed_agents_sorted:
            pos = agent_positions.get(aid, "?")
            agent_type = agent.get('subagent_type', 'unknown')
            lines.append(f"### Agent #{pos + 1}: {agent_type}")
            lines.append(f"Task: {agent.get('task', 'no description')}")
            decisions = agent.get("decisions", [])
            if decisions:
                lines.append("")
                lines.append("**Key decisions:**")
                for d in decisions[:10]:
                    lines.append(f"- {d}")
            lines.append("")

    lines.extend([
        "## IMPORTANT: Build On Previous Work",
        "",
        "1. **Read decisions above** - Previous agents made these choices. Use them.",
        "2. **Add your perspective** - What can you contribute that builds on their work?",
        "3. **Be explicit** - State your decisions clearly for agents after you.",
        "4. **No contradictions** - If you disagree with a previous decision, note it but don't change it.",
        "",
        "---",
        f"*Generated by Chitter at {datetime.now().isoformat()}*",
    ])

    coord_file.write_text("\n".join(lines))


def prompt_has_coordination(prompt: str) -> bool:
    """Check if the prompt includes coordination instruction."""
    return COORDINATION_INSTRUCTION in prompt or "~/.chitter/active/" in prompt or ".chitter/active/" in prompt


# ============================================================================
# WORKFLOW MANAGEMENT (kept for decision extraction)
# ============================================================================

def get_active_workflow(session_id: str = None) -> dict | None:
    """Get the currently active workflow for this session."""
    for path in WORKFLOWS_DIR.glob("*.json"):
        try:
            workflow = json.loads(path.read_text())
            if workflow.get("status") == "active":
                if session_id and workflow.get("session_id") != session_id:
                    continue
                return workflow
        except:
            pass
    return None


def create_workflow(description: str, session_id: str = "unknown") -> dict:
    """Create a new workflow scoped to a session."""
    import uuid
    workflow_id = str(uuid.uuid4())[:8]
    workflow = {
        "workflow_id": workflow_id,
        "session_id": session_id,
        "description": description,
        "status": "active",
        "agents": {},
        "created_at": datetime.now().isoformat(),
        "created_by": "hook"
    }
    path = WORKFLOWS_DIR / f"{workflow_id}.json"
    path.write_text(json.dumps(workflow, indent=2))
    log(f"[{session_id}] WORKFLOW CREATED: {workflow_id}")
    return workflow


def add_agent_to_workflow(workflow: dict, agent_id: str, task: str, subagent_type: str) -> None:
    """Add an agent to the workflow."""
    path = WORKFLOWS_DIR / f"{workflow['workflow_id']}.json"
    session_id = workflow.get("session_id", "unknown")

    try:
        current = json.loads(path.read_text())
    except:
        current = workflow

    current["agents"][agent_id] = {
        "task": task,
        "subagent_type": subagent_type,
        "status": "working",
        "started_at": datetime.now().isoformat(),
        "decisions": []
    }
    path.write_text(json.dumps(current, indent=2))


def complete_agent(workflow: dict, agent_id: str, output) -> None:
    """Mark agent as complete and extract decisions."""
    path = WORKFLOWS_DIR / f"{workflow['workflow_id']}.json"
    session_id = workflow.get("session_id", "unknown")

    try:
        current = json.loads(path.read_text())
    except:
        current = workflow

    if agent_id not in current["agents"]:
        return

    current["agents"][agent_id]["status"] = "complete"
    current["agents"][agent_id]["completed_at"] = datetime.now().isoformat()

    if isinstance(output, str):
        output_str = output
    elif isinstance(output, dict):
        output_str = json.dumps(output)
    else:
        output_str = str(output) if output else ""

    current["agents"][agent_id]["output_summary"] = output_str[:2000] if output_str else ""

    decisions = extract_decisions(output_str)
    current["agents"][agent_id]["decisions"] = decisions

    path.write_text(json.dumps(current, indent=2))
    log(f"[{session_id}] AGENT COMPLETE: {agent_id} - {len(decisions)} decisions extracted")


def extract_actual_content(output: str) -> str:
    """Extract actual text content from Claude's response format."""
    if not output:
        return ""

    try:
        data = json.loads(output)
        if isinstance(data, dict) and "content" in data:
            content = data["content"]
            if isinstance(content, list):
                texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                return "\n".join(texts)
        if isinstance(data, dict) and "text" in data:
            return data["text"]
    except:
        pass

    return output


def extract_decisions(output: str) -> list[str]:
    """Extract structured decisions from agent output.

    Looks for our phase output templates (### headers) and extracts
    the key decisions, specifications, and rationale.
    """
    text = extract_actual_content(output)
    if not text:
        return []

    decisions = []
    lines = text.split('\n')

    # Headers that indicate important content (from our templates)
    decision_headers = [
        "### decision", "### core principle", "### specification",
        "### visual specification", "### interaction specification",
        "### motion specification", "### responsive behavior",
        "### problem definition", "### key finding", "### recommendation",
        "### why this", "### trade-off", "### quality benchmark",
        "### architecture decision", "### code pattern", "### implementation"
    ]

    # Noise patterns to skip
    noise_patterns = [
        "│", "├", "└", "─", "┌", "┐", "┘", "┴", "┬", "┤", "┼",  # Table borders
        "---", "===", "***",  # Horizontal rules
        "```",  # Code blocks markers
        "| --- |", "| :-- |",  # Markdown table separators
    ]

    current_section = None
    section_content = []

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        line_lower = line_stripped.lower()

        # Skip noise
        if any(noise in line_stripped for noise in noise_patterns):
            continue

        # Skip empty lines and very short lines
        if len(line_stripped) < 5:
            continue

        # Skip lines that look like table rows (start with |)
        if line_stripped.startswith('|') and line_stripped.endswith('|'):
            continue

        # Check if this is a decision header
        is_header = line_stripped.startswith('###')
        is_decision_header = any(h in line_lower for h in decision_headers)

        if is_header and is_decision_header:
            # Save previous section if it had content
            if current_section and section_content:
                content = ' '.join(section_content[:3])  # First 3 lines
                if len(content) > 20:
                    decisions.append(f"**{current_section}**: {content[:200]}")

            # Start new section
            current_section = line_stripped.replace('###', '').strip()
            section_content = []
        elif current_section:
            # Add content to current section
            if len(line_stripped) > 10 and not line_stripped.startswith('#'):
                section_content.append(line_stripped)
        else:
            # Look for key statements outside sections
            key_phrases = [
                "we decided", "we chose", "final design:", "winning concept:",
                "using:", "architecture:", "stack:", "the approach is"
            ]
            if any(phrase in line_lower for phrase in key_phrases):
                if 20 < len(line_stripped) < 250:
                    decisions.append(line_stripped)

    # Don't forget the last section
    if current_section and section_content:
        content = ' '.join(section_content[:3])
        if len(content) > 20:
            decisions.append(f"**{current_section}**: {content[:200]}")

    return decisions[:20]


# ============================================================================
# HOOK HANDLERS
# ============================================================================

def handle_pre(tool_input: dict, tool_use_id: str = "", session_id: str = "unknown") -> bool:
    """Handle PreToolUse for Task tool. Returns False to block, True to allow."""
    config = get_config()
    mode = config.get("mode", "queue")
    max_concurrent = config.get("max_concurrent", 1)

    prompt = tool_input.get("prompt", "")
    subagent_type = tool_input.get("subagent_type", "unknown")
    description = tool_input.get("description", "")

    agent_id = tool_use_id[:12] if tool_use_id else f"{subagent_type}-{str(__import__('uuid').uuid4())[:4]}"
    task_summary = description if description else prompt[:100]

    # Get or create workflow
    workflow = get_active_workflow(session_id)
    if not workflow:
        workflow = create_workflow(f"Queue workflow: {description}", session_id)

    # SEQUENTIAL MODE: Enforce one-at-a-time execution
    # Blocks parallel agents - Main Claude must spawn sequentially
    if mode == "sequential":
        position = add_to_queue(session_id, agent_id, subagent_type, task_summary)
        coord_file = get_coordination_file(session_id)

        # Check if it's our turn
        if is_turn(session_id, agent_id, max_concurrent):
            # It's our turn - run!
            mark_agent_running(session_id, agent_id)
            add_agent_to_workflow(workflow, agent_id, task_summary, subagent_type)
            write_coordination_state(session_id, workflow, subagent_type, task_summary)

            completed = get_completed_agents(session_id)

            if position == 0:
                log(f"[{session_id}] START #1: {subagent_type} (first agent)")
                print(f"""
🚀 CHITTER: Agent #1 Starting
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent: {subagent_type}
Position: #1 (first in sequence)
Reading context from: (none - you're first!)

Task: {task_summary}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
            else:
                # Get names of completed agents
                completed_names = [a["type"] for a in completed]
                log(f"[{session_id}] START #{position + 1}: {subagent_type} (reading from: {', '.join(completed_names)})")
                print(f"""
🚀 CHITTER: Agent #{position + 1} Starting
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent: {subagent_type}
Position: #{position + 1}
Reading context from: {', '.join(completed_names)}

Task: {task_summary}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
            return True

        else:
            # Not our turn - BLOCK
            agents_ahead = get_agents_ahead(session_id, agent_id)
            first_ahead = agents_ahead[0] if agents_ahead else None
            mark_agent_blocked(session_id, agent_id)

            log(f"[{session_id}] SEQ: {agent_id} BLOCKED - waiting for {len(agents_ahead)} agents")

            print(f"""
🛑 CHITTER: Sequential Mode - Agent Queued
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent: {subagent_type}
Queue Position: #{position + 1}
Waiting for: {first_ahead['type'] if first_ahead else 'unknown'} to complete

╔════════════════════════════════════════════════════════════════════╗
║  MAIN CLAUDE: Spawn agents ONE AT A TIME for telephone game.      ║
║                                                                    ║
║  1. Wait for {first_ahead['type'] if first_ahead else 'the current agent':20} to complete           ║
║  2. Then spawn this agent again (same parameters)                  ║
║                                                                    ║
║  Or spawn all agents sequentially from the start.                  ║
╚════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
            sys.exit(1)

    # QUEUE MODE: Sequential execution with telephone game pattern
    # NOTE: This mode tracks order but does NOT block. Main Claude should spawn
    # agents sequentially (one at a time) for true telephone-game pattern.
    elif mode == "queue":
        # Add to queue (or get existing position if retry)
        position = add_to_queue(session_id, agent_id, subagent_type, task_summary)
        mark_agent_running(session_id, agent_id)
        add_agent_to_workflow(workflow, agent_id, task_summary, subagent_type)

        # Write coordination file with previous agents' decisions
        write_coordination_state(session_id, workflow, subagent_type, task_summary)
        coord_file = get_coordination_file(session_id)

        completed = get_completed_agents(session_id)
        agents_ahead = get_agents_ahead(session_id, agent_id)

        if position == 0:
            log(f"[{session_id}] QUEUE: {agent_id} is FIRST - running")
            print(f"""
✅ CHITTER: First agent running
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent: {subagent_type}
Position: #1 (first)

📄 Coordination file: {coord_file}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
        elif len(agents_ahead) == 0:
            log(f"[{session_id}] QUEUE: {agent_id} position {position} - running (predecessors complete)")
            print(f"""
✅ CHITTER: Running (predecessors complete)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent: {subagent_type}
Position: #{position + 1}
Completed before you: {len(completed)} agents

📄 Read previous decisions: {coord_file}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
        else:
            # Parallel detected - warn but don't block
            ahead_types = [a['type'] for a in agents_ahead]
            log(f"[{session_id}] QUEUE: {agent_id} position {position} - PARALLEL with {len(agents_ahead)} others")
            print(f"""
⚠️  CHITTER: Parallel execution detected
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent: {subagent_type}
Position: #{position + 1}
Still running ahead of you: {', '.join(ahead_types)}

⚠️  For true "telephone game", spawn agents ONE AT A TIME.
   This agent may miss decisions from agents still running.

📄 Coordination file (may be incomplete): {coord_file}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
        return True

    # BLOCK MODE: Original blocking behavior (require coordination marker)
    elif mode == "block":
        # Check if parallel
        active_agents = [a for a in workflow.get("agents", {}).values() if a.get("status") == "working"]

        if active_agents:
            if not prompt_has_coordination(prompt):
                log(f"[{session_id}] BLOCKED: {agent_id} - no coordination instruction")
                coord_file = get_coordination_file(session_id)
                print(f"""
🚫 CHITTER: BLOCKED - Coordination Required
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Add CHITTER_COORDINATION to your prompt and read: {coord_file}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
                sys.exit(1)

        add_agent_to_workflow(workflow, agent_id, task_summary, subagent_type)
        write_coordination_state(session_id, workflow, subagent_type, task_summary)

    # NUDGE/TRACK MODE: Just track, don't block
    else:
        add_agent_to_workflow(workflow, agent_id, task_summary, subagent_type)
        write_coordination_state(session_id, workflow, subagent_type, task_summary)
        log(f"[{session_id}] TRACKING: {agent_id} ({subagent_type})")

    return True


def handle_post(tool_input: dict, tool_output, tool_use_id: str = "", session_id: str = "unknown") -> None:
    """Handle PostToolUse for Task tool."""
    subagent_type = tool_input.get("subagent_type", "unknown")
    agent_id = tool_use_id[:12] if tool_use_id else None

    # Get position before marking complete
    queue = get_queue(session_id)
    position = None
    for a in queue.get("agents", []):
        if a["id"] == agent_id:
            position = a["position"]
            break

    # Mark complete in queue - but only if it was actually running
    if agent_id:
        was_running = mark_agent_complete(session_id, agent_id)
        if not was_running:
            # This agent was blocked in PRE, POST fired anyway - skip processing
            return

    # Update workflow
    workflow = get_active_workflow(session_id)
    if not workflow:
        return

    if agent_id not in workflow.get("agents", {}):
        for aid, agent in workflow.get("agents", {}).items():
            if agent.get("status") == "working" and agent.get("subagent_type") == subagent_type:
                agent_id = aid
                break

    decisions = []
    if agent_id and agent_id in workflow.get("agents", {}):
        complete_agent(workflow, agent_id, tool_output)

        # Get the decisions that were extracted
        workflow = get_active_workflow(session_id)
        if workflow and agent_id in workflow.get("agents", {}):
            decisions = workflow["agents"][agent_id].get("decisions", [])

        # Update coordination file for next agent
        if workflow:
            write_coordination_state(session_id, workflow, "next_agent", "pending")

    # Get previous agents for context
    completed_before = []
    queue = get_queue(session_id)
    for a in queue.get("agents", []):
        if position is not None and a["position"] < position and a["status"] == "complete":
            completed_before.append(a["type"])

    # Log completion with decisions
    pos_display = position + 1 if position is not None else "?"

    # Build the completion message
    decision_lines = []
    for d in decisions[:5]:  # Show top 5 decisions
        # Truncate long decisions
        d_display = d[:100] + "..." if len(d) > 100 else d
        decision_lines.append(f"   • {d_display}")

    if decisions:
        log(f"[{session_id}] COMPLETE #{pos_display}: {subagent_type}")
        for d in decisions[:3]:
            log(f"[{session_id}]   → {d[:80]}")

    # Print visible completion
    print(f"""
✅ CHITTER: Agent #{pos_display} Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent: {subagent_type}
Built on: {', '.join(completed_before) if completed_before else '(first agent)'}

Key decisions/learnings:""")

    if decision_lines:
        print("\n".join(decision_lines))
    else:
        print("   (no structured decisions extracted)")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # Check if all done
    all_complete = all(a["status"] == "complete" for a in queue["agents"]) if queue["agents"] else False

    if all_complete and len(queue["agents"]) > 1:
        log(f"[{session_id}] QUEUE COMPLETE: All {len(queue['agents'])} agents finished")

        # Build summary of all agents
        summary_lines = []
        for a in sorted(queue["agents"], key=lambda x: x["position"]):
            summary_lines.append(f"   #{a['position'] + 1}. {a['type']}")

        print(f"""
🎉 CHITTER: Telephone Game Complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agents completed in sequence:
""")
        print("\n".join(summary_lines))
        print(f"""
Each agent built on the previous one's work.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


def main():
    if len(sys.argv) < 2:
        print("Usage: hook.py pre|post <args>", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "pre":
        raw_input = sys.stdin.read()
        try:
            data = json.loads(raw_input)
            tool_input = data.get("tool_input", {})
            tool_use_id = data.get("tool_use_id", "")
            session_id = data.get("session_id", "unknown")[:8]

            prompt = tool_input.get("prompt", "")
            project, file_path = extract_project_from_prompt(prompt)

            log(f"[{session_id}] PRE: {tool_input.get('subagent_type')} ({tool_input.get('description', '')}) project={project}")
        except Exception as e:
            log(f"PRE PARSE ERROR: {e}")
            tool_input = {}
            tool_use_id = ""
            session_id = "unknown"
        handle_pre(tool_input, tool_use_id, session_id)

    elif command == "post":
        raw_input = sys.stdin.read()
        try:
            data = json.loads(raw_input)
            tool_input = data.get("tool_input", {})
            tool_response = data.get("tool_response", "")
            tool_use_id = data.get("tool_use_id", "")
            session_id = data.get("session_id", "unknown")[:8]

            prompt = tool_input.get("prompt", "")
            project, file_path = extract_project_from_prompt(prompt)

            if isinstance(tool_response, dict):
                tool_response_str = json.dumps(tool_response)
            else:
                tool_response_str = str(tool_response) if tool_response else ""

            agent_type = tool_input.get('subagent_type', 'unknown')
            desc = tool_input.get('description', '')
            log(f"[{session_id}] POST: {agent_type} ({desc}) project={project}")

            handle_post(tool_input, tool_response_str, tool_use_id, session_id)
        except Exception as e:
            log(f"POST PARSE ERROR: {e}")
            import traceback
            log(f"POST TRACEBACK: {traceback.format_exc()}")


if __name__ == "__main__":
    main()
