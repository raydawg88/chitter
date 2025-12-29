#!/usr/bin/env python3
"""
Chitter Hook Helper
Handles PreToolUse and PostToolUse logic for Task tool coordination.

Usage:
  python3 hook.py pre <tool_input_json>
  python3 hook.py post <tool_input_json> <tool_output>
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

CHITTER_DIR = Path.home() / ".chitter"
WORKFLOWS_DIR = CHITTER_DIR / "workflows"
ACTIVE_DIR = CHITTER_DIR / "active"  # Coordination files for active sessions
LOG_FILE = CHITTER_DIR / "chitter.log"
CONFIG_FILE = CHITTER_DIR / "config.json"

# Ensure directories exist
WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
ACTIVE_DIR.mkdir(parents=True, exist_ok=True)

# The magic string agents must read
COORDINATION_INSTRUCTION = "CHITTER_COORDINATION"

# Default config
DEFAULT_CONFIG = {
    "mode": "nudge",  # track, nudge, or block
}

# Known project roots to look for
PROJECT_ROOTS = [
    "/Goldfish/personal/",
    "/Goldfish/work/",
    "/Projects/",
]


def extract_project_from_prompt(prompt: str) -> tuple[str, str]:
    """Try to extract project name and path from file paths mentioned in the prompt.
    Returns (project_name, first_path_found)."""
    import re

    # Find actual file paths - must start with /Users/ or contain Goldfish
    # and have a file extension or end with a directory-like structure
    real_path_patterns = [
        r"(/Users/[^\s\"']+)",  # macOS user paths
        r"(/home/[^\s\"']+)",   # Linux user paths
        r"([^\s\"']*Goldfish[^\s\"']+)",  # Goldfish paths
        r"([^\s\"']*Projects/[^\s\"']+)",  # Projects paths
    ]

    first_path = ""
    for pattern in real_path_patterns:
        match = re.search(pattern, prompt)
        if match:
            first_path = match.group(1)
            break

    # Look for paths that include known project roots
    for root in PROJECT_ROOTS:
        # Find paths like /Goldfish/personal/project-name/...
        pattern = re.escape(root) + r"([^/\s\"']+)"
        match = re.search(pattern, prompt)
        if match:
            return match.group(1), first_path

    # Fallback: look for any absolute path and extract a reasonable folder name
    # Match paths like /Users/.../something/file.ext
    folder_match = re.search(r"/Users/[^/]+/[^/]+/([^/\s\"']+)", prompt)
    if folder_match:
        folder = folder_match.group(1)
        # Skip common non-project folders
        if folder not in ["Library", "Documents", "Desktop", "Downloads", ".claude", ".chitter"]:
            return folder, first_path

    return "unknown", first_path


def log(message: str) -> None:
    """Append to log file."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def get_coordination_file(session_id: str) -> Path:
    """Get the path to the coordination file for a session."""
    return ACTIVE_DIR / f"{session_id}.md"


def write_coordination_state(session_id: str, workflow: dict, new_agent_type: str, new_agent_task: str) -> None:
    """Write current coordination state to the session's coordination file."""
    coord_file = get_coordination_file(session_id)

    agents = workflow.get("agents", {})
    active_agents = [(aid, a) for aid, a in agents.items() if a.get("status") == "working"]
    completed_agents = [(aid, a) for aid, a in agents.items() if a.get("status") == "complete"]

    # Build the coordination markdown
    lines = [
        f"# CHITTER_COORDINATION - Session {session_id}",
        "",
        f"**Read this before starting your work.**",
        "",
        f"You are part of a parallel agent workflow. Other agents are working on related tasks.",
        f"Coordinate with them to avoid conflicts.",
        "",
        "## Your Task",
        f"You are: **{new_agent_type}**",
        f"Task: {new_agent_task}",
        "",
    ]

    # Active agents (others currently working)
    other_active = [(aid, a) for aid, a in active_agents if a.get("subagent_type") != new_agent_type or a.get("task") != new_agent_task]
    if other_active:
        lines.append("## Currently Active Agents (working in parallel with you)")
        lines.append("")
        for aid, agent in other_active:
            lines.append(f"- **{agent.get('subagent_type', 'unknown')}**: {agent.get('task', 'no description')}")
        lines.append("")

    # Completed agents and their decisions
    if completed_agents:
        lines.append("## Completed Agents (coordinate with their decisions)")
        lines.append("")
        for aid, agent in completed_agents:
            lines.append(f"### {agent.get('subagent_type', 'unknown')}")
            lines.append(f"Task: {agent.get('task', 'no description')}")
            decisions = agent.get("decisions", [])
            if decisions:
                lines.append("**Decisions made:**")
                for d in decisions[:10]:
                    lines.append(f"- {d}")
            lines.append("")

    # Coordination instructions
    lines.extend([
        "## IMPORTANT: Coordination Rules",
        "",
        "1. **Check decisions above** - If another agent defined an API, endpoint, or interface, USE THE SAME FORMAT",
        "2. **Be explicit** - State your decisions clearly so future agents can coordinate with you",
        "3. **No conflicts** - If you see a decision that conflicts with your plan, MATCH their decision",
        "",
        "---",
        f"*Generated by Chitter at {datetime.now().isoformat()}*",
    ])

    coord_file.write_text("\n".join(lines))
    log(f"[{session_id}] COORDINATION FILE WRITTEN: {coord_file}")


def prompt_has_coordination(prompt: str) -> bool:
    """Check if the prompt includes coordination instruction."""
    return COORDINATION_INSTRUCTION in prompt or "~/.chitter/active/" in prompt or ".chitter/active/" in prompt


def get_config() -> dict:
    """Load config or return defaults."""
    if CONFIG_FILE.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text())}
        except:
            pass
    return DEFAULT_CONFIG


def get_active_workflow(session_id: str = None) -> dict | None:
    """Get the currently active workflow for this session, if any."""
    for path in WORKFLOWS_DIR.glob("*.json"):
        try:
            workflow = json.loads(path.read_text())
            if workflow.get("status") == "active":
                # If session_id provided, only match workflows for this session
                if session_id and workflow.get("session_id") != session_id:
                    continue
                return workflow
        except:
            pass
    return None


def get_active_agents(workflow: dict) -> list[dict]:
    """Get agents that are still working (not complete)."""
    agents = []
    for agent_id, agent in workflow.get("agents", {}).items():
        if agent.get("status") == "working":
            agents.append({"id": agent_id, **agent})
    return agents


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
    log(f"[{session_id}] WORKFLOW AUTO-CREATED: {workflow_id} - {description}")
    return workflow


def add_agent_to_workflow(workflow: dict, agent_id: str, task: str, subagent_type: str) -> None:
    """Add an agent to the workflow."""
    path = WORKFLOWS_DIR / f"{workflow['workflow_id']}.json"
    session_id = workflow.get("session_id", "unknown")

    # Re-read to avoid race conditions with parallel agents
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
    log(f"[{session_id}] AGENT REGISTERED: {agent_id} ({subagent_type}) - {task[:100]}")


def complete_agent(workflow: dict, agent_id: str, output) -> None:
    """Mark agent as complete and extract any decisions from output."""
    path = WORKFLOWS_DIR / f"{workflow['workflow_id']}.json"
    session_id = workflow.get("session_id", "unknown")

    # Re-read to avoid race conditions
    try:
        current = json.loads(path.read_text())
    except:
        current = workflow

    if agent_id not in current["agents"]:
        log(f"[{session_id}] COMPLETE FAILED: {agent_id} not in workflow")
        return

    current["agents"][agent_id]["status"] = "complete"
    current["agents"][agent_id]["completed_at"] = datetime.now().isoformat()

    # Handle different output types
    if isinstance(output, str):
        output_str = output
    elif isinstance(output, dict):
        output_str = json.dumps(output)
    else:
        output_str = str(output) if output else ""

    current["agents"][agent_id]["output_summary"] = output_str[:2000] if output_str else ""

    # Extract actual content and find decisions
    decisions = extract_decisions(output_str)
    current["agents"][agent_id]["decisions"] = decisions

    path.write_text(json.dumps(current, indent=2))
    log(f"[{session_id}] AGENT COMPLETE: {agent_id} - {len(decisions)} decisions")


def extract_actual_content(output: str) -> str:
    """Extract actual text content from Claude's response format."""
    if not output:
        return ""

    # Try to parse as JSON and extract nested content
    try:
        data = json.loads(output)
        # Check for content array (Claude's format)
        if isinstance(data, dict) and "content" in data:
            content = data["content"]
            if isinstance(content, list):
                texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                return "\n".join(texts)
        # Maybe it's just a simple response
        if isinstance(data, dict) and "text" in data:
            return data["text"]
    except:
        pass

    # Not JSON or couldn't parse - return as-is
    return output


def extract_decisions(output: str) -> list[str]:
    """Extract decision-like statements from agent output."""
    # First extract actual text content
    text = extract_actual_content(output)
    if not text:
        return []

    decisions = []
    indicators = [
        "decided", "chose", "chosen", "using", "created", "implemented",
        "will use", "went with", "selected", "picked", "recommend",
        "should use", "best approach", "opted for", "settled on",
        "design direction", "final design", "winning concept"
    ]

    lines = text.split('\n')
    for line in lines:
        line_lower = line.lower()
        for indicator in indicators:
            if indicator in line_lower and 20 < len(line) < 300:
                decisions.append(line.strip())
                break

    return decisions[:15]  # Cap at 15


def handle_pre(tool_input: dict, tool_use_id: str = "", session_id: str = "unknown") -> bool:
    """Handle PreToolUse for Task tool. Returns False to block, True to allow."""
    config = get_config()
    mode = config.get("mode", "nudge")

    # Extract task info
    prompt = tool_input.get("prompt", "")
    subagent_type = tool_input.get("subagent_type", "unknown")
    description = tool_input.get("description", "")

    # Use tool_use_id as agent_id (unique per Task call)
    agent_id = tool_use_id[:12] if tool_use_id else f"{subagent_type}-{str(__import__('uuid').uuid4())[:4]}"

    # Check for active workflow FOR THIS SESSION
    workflow = get_active_workflow(session_id)
    active_agents = get_active_agents(workflow) if workflow else []

    # Is this parallel work?
    is_parallel = len(active_agents) > 0
    task_summary = description if description else prompt[:500]

    if is_parallel:
        # Multiple agents running - this is where coordination matters
        log(f"[{session_id}] PARALLEL DETECTED: {agent_id} joining {len(active_agents)} active agents")

        if not workflow:
            # Auto-create workflow for parallel work
            workflow = create_workflow(f"Auto-coordinated: {description}", session_id)

        # Write coordination state BEFORE checking - agents need to read this
        write_coordination_state(session_id, workflow, subagent_type, task_summary)

        # Check if prompt includes coordination instruction
        has_coordination = prompt_has_coordination(prompt)
        coord_file = get_coordination_file(session_id)

        if not has_coordination:
            # BLOCK - prompt doesn't include coordination context
            log(f"[{session_id}] BLOCKED: {agent_id} - no coordination instruction in prompt")

            agent_details = []
            for a in active_agents:
                agent_type = a.get('subagent_type', 'unknown')
                task = a.get('task', 'no description')
                agent_details.append(f"  - {agent_type}: {task}")

            other_agents = "\n".join(agent_details)

            print(f"""
🚫 CHITTER: BLOCKED - Coordination Required
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Parallel agents detected. To prevent conflicts, this agent must read
the coordination file before starting.

Other agents currently working:
{other_agents}

REQUIRED: Add this to the START of your agent's prompt:

   "FIRST: Read the coordination file at {coord_file}
    and follow any decisions made by other agents.
    CHITTER_COORDINATION"

Then retry the Task call.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
            # Exit with error to block the tool
            sys.exit(1)

        # Has coordination - allow and register
        add_agent_to_workflow(workflow, agent_id, task_summary, subagent_type)
        log(f"[{session_id}] COORDINATED AGENT: {agent_id} - has coordination context")

        print(f"""
✅ CHITTER: Coordination verified
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent {subagent_type} will read {coord_file}
Active agents in workflow: {len(active_agents) + 1}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

    else:
        # First agent or no active workflow - no coordination needed yet
        if workflow:
            # Workflow exists, add this agent
            add_agent_to_workflow(workflow, agent_id, task_summary, subagent_type)
            log(f"[{session_id}] AGENT START: {agent_id} - first in workflow {workflow['workflow_id']}")
        else:
            # No workflow, first agent - create workflow
            workflow = create_workflow(f"Single agent: {description}", session_id)
            add_agent_to_workflow(workflow, agent_id, task_summary, subagent_type)
            # Write initial coordination state for future agents
            write_coordination_state(session_id, workflow, subagent_type, task_summary)
            log(f"[{session_id}] FIRST AGENT: {agent_id} - workflow {workflow['workflow_id']}")

    return True


def handle_post(tool_input: dict, tool_output, tool_use_id: str = "", session_id: str = "unknown") -> None:
    """Handle PostToolUse for Task tool."""
    subagent_type = tool_input.get("subagent_type", "unknown")

    # Use tool_use_id to find the matching agent (same ID used in PRE)
    agent_id = tool_use_id[:12] if tool_use_id else None

    # Try to find matching agent in active workflow FOR THIS SESSION
    workflow = get_active_workflow(session_id)
    if not workflow:
        return

    # If agent_id from tool_use_id not in workflow, try matching by type
    if agent_id not in workflow.get("agents", {}):
        # Fallback: find by type and working status
        for aid, agent in workflow.get("agents", {}).items():
            if agent.get("status") == "working" and agent.get("subagent_type") == subagent_type:
                agent_id = aid
                break

    if not agent_id or agent_id not in workflow.get("agents", {}):
        log(f"[{session_id}] POST: Could not find agent {agent_id} for {subagent_type}")
        return

    if agent_id in workflow.get("agents", {}):
        complete_agent(workflow, agent_id, tool_output)

        # Re-read workflow to get updated state with decisions
        workflow = get_active_workflow(session_id)

        # Update coordination file so next agents see this agent's decisions
        if workflow:
            # Find any still-working agents to update coord file for
            active = get_active_agents(workflow)
            if active:
                first_active = active[0]
                write_coordination_state(session_id, workflow, first_active.get('subagent_type', ''), first_active.get('task', ''))
                log(f"[{session_id}] COORDINATION UPDATED: added decisions from {agent_id}")

        # Check if all agents are complete
        agents = workflow.get("agents", {}) if workflow else {}
        all_complete = all(a.get("status") == "complete" for a in agents.values())

        if all_complete and len(agents) > 1:
            # Parallel work finished - surface summary
            log(f"[{session_id}] WORKFLOW COMPLETE: {workflow['workflow_id']} - {len(agents)} agents")

            decisions = []
            for aid, a in agents.items():
                for d in a.get("decisions", []):
                    decisions.append(f"[{aid}] {d}")

            if decisions:
                print(f"""
📋 CHITTER: Parallel work complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Workflow: {workflow['workflow_id']}
Agents: {len(agents)}
Decisions detected:
{chr(10).join(decisions[:10])}

💡 Review for conflicts with: chitter_workflow_review("{workflow['workflow_id']}")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


def main():
    if len(sys.argv) < 2:
        print("Usage: hook.py pre|post <args>", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    # Claude Code passes JSON with structure:
    # {
    #   "session_id": "...",
    #   "hook_event_name": "PreToolUse" or "PostToolUse",
    #   "tool_name": "Task",
    #   "tool_input": { "description": "...", "prompt": "...", "subagent_type": "..." },
    #   "tool_response": "..." (only for PostToolUse)
    # }

    if command == "pre":
        raw_input = sys.stdin.read()
        try:
            data = json.loads(raw_input)
            tool_input = data.get("tool_input", {})
            tool_use_id = data.get("tool_use_id", "")
            session_id = data.get("session_id", "unknown")[:8]  # First 8 chars for readability

            # Try to extract project from file paths in the prompt
            prompt = tool_input.get("prompt", "")
            project, file_path = extract_project_from_prompt(prompt)

            log(f"[{session_id}] PRE: {tool_input.get('subagent_type')} ({tool_input.get('description', '')}) project={project} path={file_path[:80] if file_path else 'none'}")
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

            # Try to extract project from file paths in the prompt
            prompt = tool_input.get("prompt", "")
            project, file_path = extract_project_from_prompt(prompt)

            # Convert response to string if needed
            if isinstance(tool_response, dict):
                tool_response_str = json.dumps(tool_response)
            else:
                tool_response_str = str(tool_response) if tool_response else ""

            # Log a meaningful summary of what the agent did
            agent_type = tool_input.get('subagent_type', 'unknown')
            desc = tool_input.get('description', '')
            log(f"[{session_id}] POST: {agent_type} ({desc}) project={project} path={file_path[:80] if file_path else 'none'}")

            handle_post(tool_input, tool_response_str, tool_use_id, session_id)
        except Exception as e:
            log(f"POST PARSE ERROR: {e}")
            import traceback
            log(f"POST TRACEBACK: {traceback.format_exc()}")


if __name__ == "__main__":
    main()
