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
LOG_FILE = CHITTER_DIR / "chitter.log"
CONFIG_FILE = CHITTER_DIR / "config.json"

# Ensure directories exist
WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)

# Default config
DEFAULT_CONFIG = {
    "mode": "nudge",  # track, nudge, or block
}


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


def get_active_workflow() -> dict | None:
    """Get the currently active workflow, if any."""
    for path in WORKFLOWS_DIR.glob("*.json"):
        try:
            workflow = json.loads(path.read_text())
            if workflow.get("status") == "active":
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


def create_workflow(description: str) -> dict:
    """Create a new workflow."""
    import uuid
    workflow_id = str(uuid.uuid4())[:8]
    workflow = {
        "workflow_id": workflow_id,
        "description": description,
        "status": "active",
        "agents": {},
        "created_at": datetime.now().isoformat(),
        "created_by": "hook"
    }
    path = WORKFLOWS_DIR / f"{workflow_id}.json"
    path.write_text(json.dumps(workflow, indent=2))
    log(f"WORKFLOW AUTO-CREATED: {workflow_id} - {description}")
    return workflow


def add_agent_to_workflow(workflow: dict, agent_id: str, task: str, subagent_type: str) -> None:
    """Add an agent to the workflow."""
    workflow["agents"][agent_id] = {
        "task": task,
        "subagent_type": subagent_type,
        "status": "working",
        "started_at": datetime.now().isoformat(),
        "decisions": []
    }
    path = WORKFLOWS_DIR / f"{workflow['workflow_id']}.json"
    path.write_text(json.dumps(workflow, indent=2))
    log(f"AGENT REGISTERED: {agent_id} ({subagent_type}) - {task}")


def complete_agent(workflow: dict, agent_id: str, output: str) -> None:
    """Mark agent as complete and extract any decisions from output."""
    if agent_id in workflow["agents"]:
        workflow["agents"][agent_id]["status"] = "complete"
        workflow["agents"][agent_id]["completed_at"] = datetime.now().isoformat()
        workflow["agents"][agent_id]["output_summary"] = output[:2000] if output else ""

        # Simple heuristic: look for decision-like phrases
        decisions = extract_decisions(output)
        workflow["agents"][agent_id]["decisions"] = decisions

        path = WORKFLOWS_DIR / f"{workflow['workflow_id']}.json"
        path.write_text(json.dumps(workflow, indent=2))
        log(f"AGENT COMPLETE: {agent_id} - {len(decisions)} decisions extracted")


def extract_decisions(output: str) -> list[str]:
    """Extract decision-like statements from agent output."""
    if not output:
        return []

    decisions = []
    indicators = [
        "decided to", "chose ", "using ", "created ", "implemented ",
        "will use", "went with", "selected ", "picked "
    ]

    lines = output.split('\n')
    for line in lines:
        line_lower = line.lower()
        for indicator in indicators:
            if indicator in line_lower and len(line) < 200:
                decisions.append(line.strip())
                break

    return decisions[:10]  # Cap at 10


def handle_pre(tool_input: dict) -> None:
    """Handle PreToolUse for Task tool."""
    config = get_config()
    mode = config.get("mode", "nudge")

    # Extract task info
    prompt = tool_input.get("prompt", "")
    subagent_type = tool_input.get("subagent_type", "unknown")
    description = tool_input.get("description", "")

    # Generate agent ID
    import uuid
    agent_id = f"{subagent_type}-{str(uuid.uuid4())[:4]}"

    # Check for active workflow
    workflow = get_active_workflow()
    active_agents = get_active_agents(workflow) if workflow else []

    # Is this parallel work?
    is_parallel = len(active_agents) > 0

    if is_parallel:
        # Multiple agents running - this is where coordination matters
        log(f"PARALLEL DETECTED: {agent_id} joining {len(active_agents)} active agents")

        if mode == "block" and not workflow:
            # Block mode: require explicit workflow
            print("BLOCK: Parallel agents detected but no Chitter workflow active. Call chitter_workflow_start first, or set CHITTER_MODE=nudge")
            return

        if not workflow:
            # Auto-create workflow for parallel work
            workflow = create_workflow(f"Auto-coordinated: {description}")

        # Add this agent
        add_agent_to_workflow(workflow, agent_id, description or prompt[:200], subagent_type)

        if mode in ["nudge", "block"]:
            # Output context for Claude to see
            other_agents = "\n".join([
                f"  • {a['id']} ({a.get('subagent_type', '?')}): {a.get('task', '?')[:60]}"
                for a in active_agents
            ])

            print(f"""
⚡ CHITTER: Parallel work detected
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Workflow: {workflow['workflow_id']}
Active agents:
{other_agents}
  • {agent_id} ({subagent_type}): [THIS AGENT]

💡 Consider including in this agent's prompt:
   "Other agents are working on this project. Coordinate on shared interfaces, APIs, and data formats."
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
    else:
        # First agent or no active workflow
        if workflow:
            # Workflow exists, add this agent
            add_agent_to_workflow(workflow, agent_id, description or prompt[:200], subagent_type)
            log(f"AGENT START: {agent_id} - first in workflow {workflow['workflow_id']}")
        else:
            # No workflow, first agent - just track silently
            # Create workflow but don't output anything (single agent work)
            workflow = create_workflow(f"Single agent: {description}")
            add_agent_to_workflow(workflow, agent_id, description or prompt[:200], subagent_type)
            log(f"SINGLE AGENT: {agent_id} - workflow {workflow['workflow_id']}")

    # Store agent_id for PostToolUse to pick up
    state_file = CHITTER_DIR / "current_agent.txt"
    state_file.write_text(agent_id)


def handle_post(tool_input: dict, tool_output: str) -> None:
    """Handle PostToolUse for Task tool."""
    # Get the agent ID we stored
    state_file = CHITTER_DIR / "current_agent.txt"
    if not state_file.exists():
        return

    agent_id = state_file.read_text().strip()
    state_file.unlink()  # Clean up

    # Find the workflow with this agent
    workflow = get_active_workflow()
    if workflow and agent_id in workflow.get("agents", {}):
        complete_agent(workflow, agent_id, tool_output)

        # Check if all agents are complete
        agents = workflow.get("agents", {})
        all_complete = all(a.get("status") == "complete" for a in agents.values())

        if all_complete and len(agents) > 1:
            # Parallel work finished - surface summary
            log(f"WORKFLOW COMPLETE: {workflow['workflow_id']} - {len(agents)} agents")

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
            log(f"PRE: tool={data.get('tool_name')} type={tool_input.get('subagent_type')} desc={tool_input.get('description', '')}")
        except Exception as e:
            log(f"PRE PARSE ERROR: {e}")
            tool_input = {}
        handle_pre(tool_input)

    elif command == "post":
        raw_input = sys.stdin.read()
        try:
            data = json.loads(raw_input)
            tool_input = data.get("tool_input", {})
            tool_response = data.get("tool_response", "")
            # Log a meaningful summary of what the agent did
            agent_type = tool_input.get('subagent_type', 'unknown')
            desc = tool_input.get('description', '')
            # Get first 300 chars of response as summary
            summary = tool_response[:300].replace('\n', ' ').strip() if tool_response else 'no output'
            log(f"POST: {agent_type} ({desc}) → {summary}...")
        except Exception as e:
            log(f"POST PARSE ERROR: {e}")
            tool_input = {}
            tool_response = ""
        handle_post(tool_input, tool_response)


if __name__ == "__main__":
    main()
