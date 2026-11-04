"""Fylr MCP server -- exposes file-organization tools over stdio.

Requires the ``mcp`` package (pin ``mcp<2`` so the FastMCP high-level API
is available at ``mcp.server.fastmcp``).

Environment variables
---------------------
FYLR_ROOT   Path that acts as the sandbox root.  Every file path argument
            is validated against this root.  Defaults to the user home
            directory when unset.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import PyPDF2
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

# Import backend helpers at module level so they are patchable in tests.
from file_organizer import generate_file_structure, get_file_summary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Root folder confinement
# ---------------------------------------------------------------------------

ROOT_FOLDER: str = os.environ.get("FYLR_ROOT", str(Path.home()))

# Module-level stores for plans and undo history
_pending_plans: dict[str, dict[str, Any]] = {}
_undo_stack: list[dict[str, Any]] = []


def _validate_path(p: str) -> str:
    """Return the real, absolute form of *p* if it lives inside ROOT_FOLDER.

    Raises ``ValueError`` for any path that escapes the root via ``..``,
    symlinks, or other tricks.
    """
    if ".." in p.split(os.sep):
        raise ValueError(f"Path contains '..': {p}")

    real = os.path.realpath(os.path.abspath(p))

    # Normalise root so the prefix check is reliable
    root = os.path.realpath(ROOT_FOLDER)
    if not (real == root or real.startswith(root + os.sep)):
        raise ValueError(
            f"Path {p!r} resolves to {real!r} which is outside the "
            f"configured root {root!r}"
        )
    return real


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("fylr", instructions="File organization and search tools")


# -- Tool 1: search_files ---------------------------------------------------

@mcp.tool()
def search_files(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Search indexed files using a text query.

    Returns up to *k* results with file paths and relevance scores.
    Relies on the existing FAISS-backed search infrastructure.
    """
    from search.search_manager import SearchManager

    manager = SearchManager()
    return manager.search(query, k)


# -- Tool 2: summarize_file -------------------------------------------------

@mcp.tool()
def summarize_file(path: str) -> str:
    """Read a file and return a short summary of its contents.

    Supports plain-text files, PDFs (via PyPDF2), and images (via the
    configured LLM vision provider).
    """
    real_path = _validate_path(path)

    if not os.path.isfile(real_path):
        raise FileNotFoundError(f"No such file: {real_path}")

    mime, _ = mimetypes.guess_type(real_path)

    # Images -- delegate to the LLM provider
    if mime and mime.startswith("image/"):
        from llm import resolve_provider

        provider = resolve_provider(online_mode=True)
        messages = [
            {
                "role": "user",
                "content": (
                    f"Describe the contents of the image at {real_path} "
                    "in one or two sentences."
                ),
            }
        ]
        response = provider.chat(messages, max_tokens=256)
        return response.content.strip()

    # PDFs
    if real_path.lower().endswith(".pdf"):
        text = ""
        with open(real_path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
                    if len(text) >= 1000:
                        text = text[:1000]
                        break
        if not text:
            return "(PDF contained no extractable text)"
        return text

    # Plain text (or anything we can read as text)
    try:
        with open(real_path, "r", encoding="utf-8") as fh:
            return fh.read(1000)
    except UnicodeDecodeError:
        return "(binary file -- cannot summarize as text)"


# -- Tool 3: propose_organization -------------------------------------------

@mcp.tool()
def propose_organization(dir: str) -> dict[str, Any]:
    """Dry-run: propose a folder structure for the files in *dir*.

    Nothing is changed on disk.  Returns a ``plan_id`` and the list of
    proposed moves so the caller can review before applying.
    """
    real_dir = _validate_path(dir)

    if not os.path.isdir(real_dir):
        raise NotADirectoryError(f"Not a directory: {real_dir}")

    # Collect summaries for supported files
    file_summaries: list[dict[str, str]] = []
    for root, _dirs, files in os.walk(real_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            mime, _ = mimetypes.guess_type(fpath)
            is_image = mime and mime.startswith("image/")
            if fname.lower().endswith((".pdf", ".txt")) or is_image:
                summary = get_file_summary(fpath, online_mode=True)
                if summary:
                    file_summaries.append(
                        {"file_path": fpath, "summary": summary}
                    )

    if not file_summaries:
        return {"plan_id": None, "moves": [], "message": "No supported files found."}

    proposed = generate_file_structure(file_summaries, online_mode=True)
    if not proposed:
        return {"plan_id": None, "moves": [], "message": "LLM did not return a structure."}

    # Build the concrete move list (absolute paths)
    moves: list[dict[str, str]] = []
    for entry in proposed:
        src = os.path.join(real_dir, os.path.basename(entry["src_path"]))
        dst = os.path.join(real_dir, entry["dst_path"])
        moves.append({"src": src, "dst": dst})

    plan_id = str(uuid.uuid4())
    _pending_plans[plan_id] = {"dir": real_dir, "moves": moves}

    return {"plan_id": plan_id, "moves": moves}


# -- Tool 4: apply_plan -----------------------------------------------------

@mcp.tool()
def apply_plan(plan_id: str, confirm: bool) -> dict[str, Any]:
    """Apply a previously proposed organization plan.

    The caller **must** pass ``confirm=True`` to actually move files.
    Returns a summary of what was moved.
    """
    if plan_id not in _pending_plans:
        return {"success": False, "error": f"Unknown plan_id: {plan_id}"}

    if confirm is not True:
        return {
            "success": False,
            "error": "confirm must be True to apply the plan.",
        }

    plan = _pending_plans.pop(plan_id)
    undo_entries: list[dict[str, str]] = []
    moved: list[dict[str, str]] = []

    for move in plan["moves"]:
        src = move["src"]
        dst = move["dst"]

        # Validate both paths
        src = _validate_path(src)
        dst_real = os.path.realpath(os.path.abspath(dst))
        root = os.path.realpath(ROOT_FOLDER)
        if not (dst_real == root or dst_real.startswith(root + os.sep)):
            return {
                "success": False,
                "error": f"Destination {dst} escapes the root folder.",
            }

        if not os.path.exists(src):
            continue

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        undo_entries.append({"original": src, "new": dst})
        moved.append({"src": src, "dst": dst})

    _undo_stack.append({"plan_id": plan_id, "entries": undo_entries})

    return {"success": True, "moved": moved}


# -- Tool 5: undo_last ------------------------------------------------------

@mcp.tool()
def undo_last() -> dict[str, Any]:
    """Reverse the most recently applied plan.

    Moves every file back to its original location.
    """
    if not _undo_stack:
        return {"success": False, "error": "Nothing to undo."}

    record = _undo_stack.pop()
    restored: list[dict[str, str]] = []

    for entry in reversed(record["entries"]):
        src = entry["new"]       # current location
        dst = entry["original"]  # original location

        if not os.path.exists(src):
            continue

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        restored.append({"from": src, "to": dst})

    return {"success": True, "restored": restored}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
