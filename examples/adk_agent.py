"""Example: Google ADK agent that organizes files via the Fylr MCP server.

Connects to backend/mcp_server.py over stdio, proposes an organization
plan for a sample folder, and asks for confirmation before applying.

Requirements:
    pip install google-adk google-genai

You also need a GOOGLE_API_KEY (Gemini) in your environment or .env file.

Usage:
    python examples/adk_agent.py /path/to/messy-folder
"""

from __future__ import annotations

import asyncio
import os
import sys

# ---------------------------------------------------------------------------
# Graceful handling when ADK or the API key is not available
# ---------------------------------------------------------------------------

try:
    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner
    from google.adk.tools.mcp_tool import McpToolset
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from google.genai import types
    from mcp import StdioServerParameters
except ImportError:
    print(
        "Google ADK is not installed.\n"
        "Install it with:  pip install google-adk google-genai\n"
        "Then re-run this script."
    )
    sys.exit(1)

if not os.environ.get("GOOGLE_API_KEY"):
    print(
        "GOOGLE_API_KEY is not set.\n"
        "Export it in your shell or add it to a .env file at the project root."
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Resolve the project root (one level up from examples/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP_SERVER = os.path.join(PROJECT_ROOT, "backend", "mcp_server.py")
PYTHON = sys.executable  # use the same interpreter running this script


def get_target_dir() -> str:
    """Return the folder to organize, from argv or a default."""
    if len(sys.argv) > 1:
        target = os.path.abspath(sys.argv[1])
        if not os.path.isdir(target):
            print(f"Not a directory: {target}")
            sys.exit(1)
        return target
    # Fall back to a sample folder in the project
    sample = os.path.join(PROJECT_ROOT, "sample_files")
    if not os.path.isdir(sample):
        print(
            "Usage: python examples/adk_agent.py /path/to/folder\n"
            "No folder provided and no sample_files/ directory found."
        )
        sys.exit(1)
    return sample


# ---------------------------------------------------------------------------
# Build the ADK agent with Fylr MCP tools
# ---------------------------------------------------------------------------

def build_agent(target_dir: str) -> LlmAgent:
    """Create an LlmAgent wired to the Fylr MCP server."""

    # Connect to the Fylr MCP server via stdio.  The server will be
    # started as a child process by the ADK runtime.
    fylr_tools = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=PYTHON,
                args=[MCP_SERVER],
                env={
                    **os.environ,
                    "FYLR_ROOT": target_dir,
                },
            ),
            timeout=30,
        ),
    )

    agent = LlmAgent(
        name="fylr_organizer",
        model="gemini-2.5-flash",
        instruction=(
            "You are a file organization assistant powered by Fylr.\n"
            "The user wants to organize the files in a directory.\n"
            f"The target directory is: {target_dir}\n\n"
            "Steps:\n"
            "1. Call propose_organization with the target directory.\n"
            "2. Print the proposed moves clearly for the user.\n"
            "3. Wait for the user to confirm before calling apply_plan.\n"
            "4. If the user declines, do NOT apply the plan.\n"
        ),
        tools=[fylr_tools],
    )
    return agent


# ---------------------------------------------------------------------------
# Main loop: propose, confirm, apply
# ---------------------------------------------------------------------------

async def main() -> None:
    target_dir = get_target_dir()
    print(f"Target directory: {target_dir}\n")

    agent = build_agent(target_dir)

    runner = InMemoryRunner(
        agent=agent,
        app_name="fylr_adk_example",
    )

    session = await runner.session_service.create_session(
        app_name="fylr_adk_example",
        user_id="user",
    )

    # Step 1 -- ask the agent to propose organization
    print("Asking Fylr to analyze the folder and propose a plan...\n")

    propose_msg = types.Content(
        role="user",
        parts=[types.Part.from_text(
            text=f"Please propose an organization plan for: {target_dir}"
        )],
    )

    async for event in runner.run_async(
        user_id="user",
        session_id=session.id,
        new_message=propose_msg,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text)

    # Step 2 -- ask the user whether to proceed
    print()
    answer = input("Apply this plan? [y/N] ").strip().lower()
    if answer != "y":
        print("Skipped. No files were moved.")
        return

    # Step 3 -- tell the agent to apply
    confirm_msg = types.Content(
        role="user",
        parts=[types.Part.from_text(
            text="Yes, please apply the plan."
        )],
    )

    async for event in runner.run_async(
        user_id="user",
        session_id=session.id,
        new_message=confirm_msg,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
