#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp"]
# ///
"""
Chitter MCP Server
Real-time coordination for Claude Code agents

7 Tools:
- chitter_workflow_start: Main Claude creates coordination context
- chitter_workflow_review: Main Claude reviews after agents complete
- chitter_workflow_close: Main Claude closes workflow
- chitter_agent_start: Agent declares task and areas of concern
- chitter_decision: Agent logs key decision
- chitter_complete: Agent marks task complete
- chitter_status: Check active workflows before starting new ones
"""

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# State directory
CHITTER_DIR = Path.home() / ".chitter"
WORKFLOWS_DIR = CHITTER_DIR / "workflows"
LOG_FILE = CHITTER_DIR / "chitter.log"

# Ensure directories exist
WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    """Append timestamped message to log file."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")

server = Server("chitter")


def get_workflow_path(workflow_id: str) -> Path:
    """Get path to workflow state file."""
    return WORKFLOWS_DIR / f"{workflow_id}.json"


def load_workflow(workflow_id: str) -> dict | None:
    """Load workflow state from disk."""
    path = get_workflow_path(workflow_id)
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_workflow(workflow: dict) -> None:
    """Save workflow state to disk (atomic write)."""
    path = get_workflow_path(workflow["workflow_id"])
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(workflow, indent=2, default=str))
    temp_path.rename(path)


def delete_workflow(workflow_id: str) -> None:
    """Delete workflow state file."""
    path = get_workflow_path(workflow_id)
    if path.exists():
        path.unlink()


def cleanup_old_workflows(max_age_hours: int = 24) -> int:
    """Remove workflows older than max_age_hours. Returns count deleted."""
    deleted = 0
    cutoff = datetime.now() - timedelta(hours=max_age_hours)

    for path in WORKFLOWS_DIR.glob("*.json"):
        try:
            workflow = json.loads(path.read_text())
            created = datetime.fromisoformat(workflow.get("created_at", "2000-01-01"))
            if created < cutoff:
                path.unlink()
                deleted += 1
        except (json.JSONDecodeError, ValueError):
            # Corrupted file, delete it
            path.unlink()
            deleted += 1

    return deleted


def detect_conflicts(workflow: dict) -> list[dict]:
    """Detect potential conflicts between agents."""
    conflicts = []
    agents = workflow.get("agents", {})

    # Check for file conflicts
    files_by_agent = {}
    for agent_id, agent in agents.items():
        for f in agent.get("files_modified", []):
            if f not in files_by_agent:
                files_by_agent[f] = []
            files_by_agent[f].append(agent_id)

    for file, agent_ids in files_by_agent.items():
        if len(agent_ids) > 1:
            conflicts.append({
                "type": "file_conflict",
                "severity": "high",
                "file": file,
                "agents": agent_ids,
                "message": f"Multiple agents modified {file}: {', '.join(agent_ids)}"
            })

    # Check for area overlap with different decisions
    areas_decisions = {}  # area -> [(agent_id, decision)]
    for agent_id, agent in agents.items():
        areas = agent.get("areas_of_concern", [])
        decisions = agent.get("decisions", [])

        for area in areas:
            if area not in areas_decisions:
                areas_decisions[area] = []
            for decision in decisions:
                areas_decisions[area].append((agent_id, decision))

    for area, entries in areas_decisions.items():
        if len(entries) > 1:
            # Multiple agents made decisions in same area
            agent_ids = list(set(e[0] for e in entries))
            if len(agent_ids) > 1:
                conflicts.append({
                    "type": "area_overlap",
                    "severity": "medium",
                    "area": area,
                    "agents": agent_ids,
                    "decisions": [e[1] for e in entries],
                    "message": f"Multiple agents made decisions in '{area}': {', '.join(agent_ids)} - review for compatibility"
                })

    # Check for interface mismatches (expects vs created)
    interfaces_expected = {}  # interface_name -> [(agent_id, spec)]
    interfaces_created = {}

    for agent_id, agent in agents.items():
        for decision in agent.get("decisions", []):
            if decision.get("type") == "interface":
                desc = decision.get("decision", "").lower()
                if "expects" in desc or "expect" in desc:
                    key = decision.get("decision", "")[:50]
                    if key not in interfaces_expected:
                        interfaces_expected[key] = []
                    interfaces_expected[key].append((agent_id, decision))
                elif "created" in desc or "create" in desc or "provides" in desc:
                    key = decision.get("decision", "")[:50]
                    if key not in interfaces_created:
                        interfaces_created[key] = []
                    interfaces_created[key].append((agent_id, decision))

    return conflicts


def get_active_workflows() -> list[dict]:
    """Get all active workflows."""
    workflows = []
    for path in WORKFLOWS_DIR.glob("*.json"):
        try:
            workflow = json.loads(path.read_text())
            if workflow.get("status") == "active":
                workflows.append(workflow)
        except json.JSONDecodeError:
            pass
    return workflows


# Tool definitions
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="chitter_workflow_start",
            description="Start a new coordination workflow before spawning parallel agents. Returns workflow_id and context to inject into agent prompts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Overall goal of this parallel work (e.g., 'Building user authentication system')"
                    },
                    "agents_planned": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of agent roles/tasks planned (e.g., ['Frontend auth UI', 'Backend auth API', 'Database schema'])"
                    }
                },
                "required": ["description", "agents_planned"]
            }
        ),
        Tool(
            name="chitter_workflow_review",
            description="Review workflow state after all agents complete. Returns summary of all decisions, detected conflicts, and integration points.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "The workflow ID to review"
                    }
                },
                "required": ["workflow_id"]
            }
        ),
        Tool(
            name="chitter_workflow_close",
            description="Close a workflow after review and conflict resolution. Clears ephemeral state.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "The workflow ID to close"
                    },
                    "resolution_notes": {
                        "type": "string",
                        "description": "Optional notes on how conflicts were resolved"
                    }
                },
                "required": ["workflow_id"]
            }
        ),
        Tool(
            name="chitter_agent_start",
            description="Called by an agent when starting work. Declares task and areas of concern for conflict detection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "The workflow ID this agent belongs to"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Unique identifier for this agent (e.g., 'frontend-001')"
                    },
                    "task_summary": {
                        "type": "string",
                        "description": "Brief summary of what this agent will do"
                    },
                    "areas_of_concern": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Areas this agent will touch (e.g., ['auth flow', 'api endpoints', 'user model'])"
                    }
                },
                "required": ["workflow_id", "agent_id", "task_summary", "areas_of_concern"]
            }
        ),
        Tool(
            name="chitter_decision",
            description="Log a key decision. Call this for architecture, API, data model, dependency, or interface choices.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "The workflow ID"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "The agent making this decision"
                    },
                    "decision_type": {
                        "type": "string",
                        "enum": ["architecture", "approach", "api", "data_model", "interface", "dependency", "other"],
                        "description": "Category of decision"
                    },
                    "decision": {
                        "type": "string",
                        "description": "The decision made (e.g., 'Using REST with /api/auth/* endpoints')"
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why this decision was made"
                    }
                },
                "required": ["workflow_id", "agent_id", "decision_type", "decision"]
            }
        ),
        Tool(
            name="chitter_complete",
            description="Mark agent task as complete. Include summary of work done and files modified.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "The workflow ID"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "The agent completing"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Summary of what was accomplished"
                    },
                    "files_modified": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of files created or modified"
                    }
                },
                "required": ["workflow_id", "agent_id", "summary", "files_modified"]
            }
        ),
        Tool(
            name="chitter_status",
            description="Check status of all active workflows. Call this before starting a new workflow to see if one is already in progress.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:

    # Auto-cleanup old workflows on any call
    cleanup_old_workflows()

    if name == "chitter_workflow_start":
        workflow_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        log(f"WORKFLOW START: {workflow_id} - {arguments['description']}")

        workflow = {
            "workflow_id": workflow_id,
            "description": arguments["description"],
            "agents_planned": arguments["agents_planned"],
            "status": "active",
            "agents": {},
            "created_at": now,
            "updated_at": now
        }

        save_workflow(workflow)

        # Generate context for agent prompts
        agent_context = f"""CHITTER COORDINATION PROTOCOL
=============================
Workflow ID: {workflow_id}
Goal: {arguments['description']}
Parallel agents: {', '.join(arguments['agents_planned'])}

You are part of a coordinated parallel workflow. Other agents are working simultaneously.

REQUIRED ACTIONS:
1. Call chitter_agent_start immediately with your task summary and areas of concern
2. Call chitter_decision for ANY choice affecting: architecture, APIs, data models, interfaces, or dependencies
3. Call chitter_complete when done with summary and files modified

This ensures your work integrates cleanly with other agents."""

        return [TextContent(
            type="text",
            text=f"""Workflow created: {workflow_id}

Inject this into each agent's task prompt:

---
{agent_context}
---

After all agents complete, call chitter_workflow_review("{workflow_id}") to check for conflicts."""
        )]

    elif name == "chitter_workflow_review":
        workflow_id = arguments["workflow_id"]
        log(f"WORKFLOW REVIEW: {workflow_id}")
        workflow = load_workflow(workflow_id)

        if not workflow:
            return [TextContent(type="text", text=f"Workflow {workflow_id} not found")]

        workflow["status"] = "reviewing"
        save_workflow(workflow)

        # Gather all decisions
        all_decisions = []
        all_files = []
        agent_summaries = []

        for agent_id, agent in workflow.get("agents", {}).items():
            agent_summaries.append(f"**{agent_id}**: {agent.get('summary', 'No summary')}")
            all_decisions.extend(agent.get("decisions", []))
            all_files.extend(agent.get("files_modified", []))

        # Detect conflicts
        conflicts = detect_conflicts(workflow)

        # Build review report
        report = [f"# Workflow Review: {workflow_id}"]
        report.append(f"\n## Goal\n{workflow['description']}")

        report.append(f"\n## Agents ({len(workflow.get('agents', {}))} of {len(workflow.get('agents_planned', []))} completed)")
        for summary in agent_summaries:
            report.append(f"- {summary}")

        report.append(f"\n## Decisions ({len(all_decisions)} total)")
        for d in all_decisions:
            report.append(f"- [{d.get('type', 'unknown')}] {d.get('decision', 'No description')}")

        report.append(f"\n## Files Modified ({len(set(all_files))} unique)")
        for f in sorted(set(all_files)):
            report.append(f"- {f}")

        if conflicts:
            report.append(f"\n## CONFLICTS DETECTED ({len(conflicts)})")
            for c in conflicts:
                severity_icon = "🔴" if c["severity"] == "high" else "🟡"
                report.append(f"{severity_icon} **{c['type']}**: {c['message']}")
        else:
            report.append("\n## No Conflicts Detected ✓")

        report.append(f"\n---\nCall chitter_workflow_close('{workflow_id}') when done reviewing.")

        return [TextContent(type="text", text="\n".join(report))]

    elif name == "chitter_workflow_close":
        workflow_id = arguments["workflow_id"]
        workflow = load_workflow(workflow_id)

        if not workflow:
            return [TextContent(type="text", text=f"Workflow {workflow_id} not found")]

        resolution_notes = arguments.get("resolution_notes", "")

        # Log closure for potential Goldfish integration
        closure_summary = {
            "workflow_id": workflow_id,
            "description": workflow["description"],
            "agents_count": len(workflow.get("agents", {})),
            "decisions_count": sum(len(a.get("decisions", [])) for a in workflow.get("agents", {}).values()),
            "files_modified": list(set(
                f for a in workflow.get("agents", {}).values()
                for f in a.get("files_modified", [])
            )),
            "conflicts_found": len(detect_conflicts(workflow)),
            "resolution_notes": resolution_notes,
            "closed_at": datetime.now().isoformat()
        }

        # Delete the workflow file
        delete_workflow(workflow_id)

        return [TextContent(
            type="text",
            text=f"""Workflow {workflow_id} closed.

Summary:
- Agents: {closure_summary['agents_count']}
- Decisions logged: {closure_summary['decisions_count']}
- Files modified: {len(closure_summary['files_modified'])}
- Conflicts resolved: {closure_summary['conflicts_found']}

Workflow state cleared."""
        )]

    elif name == "chitter_agent_start":
        workflow_id = arguments["workflow_id"]
        agent_id = arguments["agent_id"]
        log(f"AGENT START: {agent_id} in {workflow_id} - {arguments['task_summary']}")
        workflow = load_workflow(workflow_id)

        if not workflow:
            return [TextContent(type="text", text=f"Workflow {workflow_id} not found. Was it created with chitter_workflow_start?")]

        workflow["agents"][agent_id] = {
            "task": arguments["task_summary"],
            "areas_of_concern": arguments["areas_of_concern"],
            "status": "working",
            "started_at": datetime.now().isoformat(),
            "decisions": [],
            "files_modified": [],
            "summary": None
        }
        workflow["updated_at"] = datetime.now().isoformat()

        save_workflow(workflow)

        # Show what other agents are doing
        other_agents = [
            f"- {aid}: {a['task']} (areas: {', '.join(a['areas_of_concern'])})"
            for aid, a in workflow["agents"].items()
            if aid != agent_id
        ]

        other_info = "\n".join(other_agents) if other_agents else "No other agents registered yet."

        return [TextContent(
            type="text",
            text=f"""Registered in workflow {workflow_id}.

Your task: {arguments['task_summary']}
Your areas: {', '.join(arguments['areas_of_concern'])}

Other agents in this workflow:
{other_info}

Remember to call chitter_decision for key choices and chitter_complete when done."""
        )]

    elif name == "chitter_decision":
        workflow_id = arguments["workflow_id"]
        agent_id = arguments["agent_id"]
        log(f"DECISION: [{agent_id}] {arguments['decision_type']} - {arguments['decision'][:60]}")
        workflow = load_workflow(workflow_id)

        if not workflow:
            return [TextContent(type="text", text=f"Workflow {workflow_id} not found")]

        if agent_id not in workflow["agents"]:
            return [TextContent(type="text", text=f"Agent {agent_id} not registered. Call chitter_agent_start first.")]

        decision = {
            "type": arguments["decision_type"],
            "decision": arguments["decision"],
            "rationale": arguments.get("rationale", ""),
            "timestamp": datetime.now().isoformat()
        }

        workflow["agents"][agent_id]["decisions"].append(decision)
        workflow["updated_at"] = datetime.now().isoformat()

        save_workflow(workflow)

        return [TextContent(
            type="text",
            text=f"Decision logged: [{arguments['decision_type']}] {arguments['decision']}"
        )]

    elif name == "chitter_complete":
        workflow_id = arguments["workflow_id"]
        agent_id = arguments["agent_id"]
        log(f"AGENT COMPLETE: {agent_id} - {arguments['summary'][:60]}")
        workflow = load_workflow(workflow_id)

        if not workflow:
            return [TextContent(type="text", text=f"Workflow {workflow_id} not found")]

        if agent_id not in workflow["agents"]:
            return [TextContent(type="text", text=f"Agent {agent_id} not registered")]

        workflow["agents"][agent_id]["status"] = "complete"
        workflow["agents"][agent_id]["completed_at"] = datetime.now().isoformat()
        workflow["agents"][agent_id]["summary"] = arguments["summary"]
        workflow["agents"][agent_id]["files_modified"] = arguments["files_modified"]
        workflow["updated_at"] = datetime.now().isoformat()

        save_workflow(workflow)

        # Check if all planned agents are complete
        completed = sum(1 for a in workflow["agents"].values() if a["status"] == "complete")
        planned = len(workflow.get("agents_planned", []))

        return [TextContent(
            type="text",
            text=f"""Task complete: {arguments['summary']}
Files modified: {', '.join(arguments['files_modified']) or 'None'}

Progress: {completed}/{planned} agents complete."""
        )]

    elif name == "chitter_status":
        workflows = get_active_workflows()

        if not workflows:
            return [TextContent(
                type="text",
                text="No active workflows. Ready to start a new one with chitter_workflow_start."
            )]

        report = [f"# Active Workflows ({len(workflows)})"]

        for wf in workflows:
            agents = wf.get("agents", {})
            completed = sum(1 for a in agents.values() if a.get("status") == "complete")
            total = len(agents)
            planned = len(wf.get("agents_planned", []))

            report.append(f"\n## {wf['workflow_id']}")
            report.append(f"**Goal:** {wf['description']}")
            report.append(f"**Status:** {wf['status']}")
            report.append(f"**Agents:** {completed}/{total} complete ({planned} planned)")
            report.append(f"**Created:** {wf.get('created_at', 'unknown')}")

            if agents:
                report.append("\n**Registered agents:**")
                for aid, a in agents.items():
                    status_icon = "✓" if a.get("status") == "complete" else "⋯"
                    report.append(f"- {status_icon} {aid}: {a.get('task', 'No task')}")

        return [TextContent(type="text", text="\n".join(report))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
