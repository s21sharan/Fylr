# Fylr MCP Server

Fylr exposes its file-organization tools through the Model Context Protocol (MCP) over stdio. Any MCP-compatible client can connect and use these tools.

## Prerequisites

- Python 3.10+
- Project dependencies: `pip install -r requirements.txt`
- An API key for the online LLM provider (set `GOOGLE_API_KEY` or `OPENAI_API_KEY` in `.env`)
- Optional: `pip install google-adk google-genai` for the ADK example

## Starting the Server

```bash
# From the project root
FYLR_ROOT=/path/to/sandbox python backend/mcp_server.py
```

`FYLR_ROOT` restricts all file operations to that directory tree. If omitted, it defaults to your home directory.

The server communicates over stdin/stdout using the MCP stdio transport.

## Available Tools

| Tool | Description |
|------|-------------|
| `search_files(query, k=5)` | Search indexed files with a text query. Returns up to k results with paths and relevance scores. |
| `summarize_file(path)` | Read a file and return a short summary. Supports text, PDF, and images. |
| `propose_organization(dir)` | Dry-run: analyze files in a directory and propose a folder structure. Returns a `plan_id` and list of moves. Nothing is changed on disk. |
| `apply_plan(plan_id, confirm)` | Apply a previously proposed plan. The `confirm` parameter must be `True`. |
| `undo_last()` | Reverse the most recently applied plan, moving files back to their original locations. |

## Safety Model

**Path confinement.** Every path argument is resolved to an absolute path and checked against `FYLR_ROOT`. Paths containing `..` or resolving outside the root are rejected.

**Confirm gate.** `propose_organization` never moves files. It returns a plan with a unique ID. The client must explicitly call `apply_plan` with `confirm=True` to execute moves. This two-step flow gives users (or agents) a chance to review before anything changes.

**Undo.** `undo_last` reverses the most recent apply, restoring files to their original locations. The undo stack is maintained for the lifetime of the server process.

## Connecting from Gemini CLI

Gemini CLI supports MCP servers natively. Add the Fylr server to your settings file.

**Project-level config** (`.gemini/settings.json` in the Fylr repo):

```json
{
  "mcpServers": {
    "fylr": {
      "command": "python",
      "args": ["backend/mcp_server.py"],
      "env": {
        "FYLR_ROOT": "/path/to/sandbox"
      },
      "cwd": "/path/to/Fylr"
    }
  }
}
```

**User-level config** (`~/.gemini/settings.json`):

Same format, but use absolute paths for both `args` and `cwd`.

Once configured, start Gemini CLI in the project directory. The Fylr tools will appear automatically. Run `/mcp` inside Gemini CLI to verify the server is connected.

## Connecting from Google ADK

The `examples/adk_agent.py` script demonstrates a complete ADK agent that connects to the Fylr MCP server.

Key pattern:

```python
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

fylr_tools = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["backend/mcp_server.py"],
            env={"FYLR_ROOT": "/path/to/sandbox"},
        ),
        timeout=30,
    ),
)
```

Pass `fylr_tools` to an `LlmAgent` as a tool, then run it with `InMemoryRunner`. See `examples/adk_agent.py` for the full working script.

## Connecting from Claude Desktop

Add the following to your Claude Desktop configuration file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "fylr": {
      "command": "python",
      "args": ["/absolute/path/to/Fylr/backend/mcp_server.py"],
      "env": {
        "FYLR_ROOT": "/path/to/sandbox"
      }
    }
  }
}
```

Restart Claude Desktop after saving. The Fylr tools will be available in the tool picker.

## Example Session

A typical propose, apply, undo flow:

```
User: Organize the files in /tmp/messy-folder

Agent calls: propose_organization(dir="/tmp/messy-folder")
Server returns:
{
  "plan_id": "a1b2c3d4-...",
  "moves": [
    {"src": "/tmp/messy-folder/receipt.pdf",  "dst": "/tmp/messy-folder/Finance/receipt.pdf"},
    {"src": "/tmp/messy-folder/photo.jpg",    "dst": "/tmp/messy-folder/Photos/photo.jpg"},
    {"src": "/tmp/messy-folder/notes.txt",    "dst": "/tmp/messy-folder/Documents/notes.txt"}
  ]
}

Agent: Here is the proposed plan:
  - receipt.pdf -> Finance/receipt.pdf
  - photo.jpg -> Photos/photo.jpg
  - notes.txt -> Documents/notes.txt
  Shall I apply it?

User: Yes, go ahead.

Agent calls: apply_plan(plan_id="a1b2c3d4-...", confirm=True)
Server returns: {"success": true, "moved": [...]}

Agent: Done. 3 files organized into 3 folders.

User: Actually, undo that.

Agent calls: undo_last()
Server returns: {"success": true, "restored": [...]}

Agent: Reverted. All files are back in their original locations.
```
