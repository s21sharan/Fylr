"""Tests for the Fylr MCP server.

These tests verify tool registration, path confinement, the propose/apply
lifecycle, and undo behaviour.  File-system side effects are confined to
pytest's ``tmp_path`` fixture.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from unittest import mock

import pytest

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_module_state():
    """Clear the module-level dicts between tests."""
    import mcp_server

    mcp_server._pending_plans.clear()
    mcp_server._undo_stack.clear()


@pytest.fixture(autouse=True)
def _clean_state():
    """Ensure each test starts with empty plans and undo stack."""
    _reset_module_state()
    yield
    _reset_module_state()


@pytest.fixture()
def confined_root(tmp_path, monkeypatch):
    """Set FYLR_ROOT to tmp_path and update the module constant."""
    monkeypatch.setenv("FYLR_ROOT", str(tmp_path))
    import mcp_server

    monkeypatch.setattr(mcp_server, "ROOT_FOLDER", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Tool listing
# ---------------------------------------------------------------------------

def test_tool_listing():
    """All five expected tools must be registered on the MCP server."""
    import mcp_server

    server = mcp_server.mcp
    # list_tools may be sync or async depending on SDK version
    result = server.list_tools()
    if asyncio.iscoroutine(result):
        loop = asyncio.new_event_loop()
        try:
            tools = loop.run_until_complete(result)
        finally:
            loop.close()
    else:
        tools = result
    tool_names = {t.name for t in tools}

    expected = {
        "search_files",
        "summarize_file",
        "propose_organization",
        "apply_plan",
        "undo_last",
    }
    assert expected.issubset(tool_names), (
        f"Missing tools: {expected - tool_names}"
    )


# ---------------------------------------------------------------------------
# 2. propose_organization is a dry run
# ---------------------------------------------------------------------------

def test_propose_organization_dry_run(confined_root):
    """propose_organization must not move, rename, or delete any file."""
    import mcp_server

    # Create a few dummy files
    for name in ("a.txt", "b.txt", "c.txt"):
        (confined_root / name).write_text(f"content of {name}")

    before = sorted(os.listdir(confined_root))

    fake_structure = [
        {"src_path": "a.txt", "dst_path": "docs/a.txt"},
        {"src_path": "b.txt", "dst_path": "docs/b.txt"},
        {"src_path": "c.txt", "dst_path": "misc/c.txt"},
    ]

    with (
        mock.patch(
            "mcp_server.get_file_summary", return_value="dummy summary"
        ),
        mock.patch(
            "mcp_server.generate_file_structure", return_value=fake_structure
        ),
    ):
        result = mcp_server.propose_organization(str(confined_root))

    after = sorted(os.listdir(confined_root))
    assert before == after, "propose_organization must not change the filesystem"
    assert result["plan_id"] is not None
    assert len(result["moves"]) == 3


# ---------------------------------------------------------------------------
# 3. apply_plan refuses without confirm=True
# ---------------------------------------------------------------------------

def test_apply_plan_refuses_without_confirm(confined_root):
    """apply_plan must reject calls where confirm is not True."""
    import mcp_server

    (confined_root / "x.txt").write_text("hello")

    fake_structure = [
        {"src_path": "x.txt", "dst_path": "folder/x.txt"},
    ]

    with (
        mock.patch(
            "mcp_server.get_file_summary", return_value="dummy"
        ),
        mock.patch(
            "mcp_server.generate_file_structure", return_value=fake_structure
        ),
    ):
        proposal = mcp_server.propose_organization(str(confined_root))

    plan_id = proposal["plan_id"]
    result = mcp_server.apply_plan(plan_id, confirm=False)

    assert result["success"] is False
    assert "confirm" in result["error"].lower()
    # The plan should still be pending (not consumed)
    assert plan_id in mcp_server._pending_plans


# ---------------------------------------------------------------------------
# 4. apply_plan refuses unknown plan_id
# ---------------------------------------------------------------------------

def test_apply_plan_refuses_unknown_id():
    """apply_plan must reject an unrecognised plan_id."""
    import mcp_server

    result = mcp_server.apply_plan(str(uuid.uuid4()), confirm=True)
    assert result["success"] is False
    assert "unknown" in result["error"].lower() or "Unknown" in result["error"]


# ---------------------------------------------------------------------------
# 5. apply_plan moves files
# ---------------------------------------------------------------------------

def test_apply_plan_moves_files(confined_root):
    """apply_plan with confirm=True must actually relocate files."""
    import mcp_server

    (confined_root / "report.txt").write_text("quarterly earnings")

    fake_structure = [
        {"src_path": "report.txt", "dst_path": "finance/report.txt"},
    ]

    with (
        mock.patch(
            "mcp_server.get_file_summary", return_value="finance report"
        ),
        mock.patch(
            "mcp_server.generate_file_structure", return_value=fake_structure
        ),
    ):
        proposal = mcp_server.propose_organization(str(confined_root))

    plan_id = proposal["plan_id"]
    result = mcp_server.apply_plan(plan_id, confirm=True)

    assert result["success"] is True
    assert not (confined_root / "report.txt").exists()
    assert (confined_root / "finance" / "report.txt").exists()
    assert (confined_root / "finance" / "report.txt").read_text() == "quarterly earnings"


# ---------------------------------------------------------------------------
# 6. Path confinement
# ---------------------------------------------------------------------------

def test_path_confinement(confined_root):
    """Paths that escape the root via '..' must be rejected."""
    import mcp_server

    outside = str(confined_root / ".." / "etc" / "passwd")

    with pytest.raises(ValueError, match="outside|\\.\\."):
        mcp_server._validate_path(outside)


def test_path_confinement_summarize(confined_root):
    """summarize_file must reject paths outside the root."""
    import mcp_server

    outside = str(confined_root / ".." / "secret.txt")

    with pytest.raises(ValueError):
        mcp_server.summarize_file(outside)


# ---------------------------------------------------------------------------
# 7. Undo last
# ---------------------------------------------------------------------------

def test_undo_last(confined_root):
    """After applying a plan, undo_last must restore files to their originals."""
    import mcp_server

    (confined_root / "memo.txt").write_text("important memo")

    fake_structure = [
        {"src_path": "memo.txt", "dst_path": "archive/memo.txt"},
    ]

    with (
        mock.patch(
            "mcp_server.get_file_summary", return_value="memo summary"
        ),
        mock.patch(
            "mcp_server.generate_file_structure", return_value=fake_structure
        ),
    ):
        proposal = mcp_server.propose_organization(str(confined_root))

    mcp_server.apply_plan(proposal["plan_id"], confirm=True)

    # File should be in archive/
    assert not (confined_root / "memo.txt").exists()
    assert (confined_root / "archive" / "memo.txt").exists()

    # Undo
    undo_result = mcp_server.undo_last()
    assert undo_result["success"] is True
    assert (confined_root / "memo.txt").exists()
    assert (confined_root / "memo.txt").read_text() == "important memo"


def test_undo_last_empty_stack():
    """undo_last with nothing to undo must report failure."""
    import mcp_server

    result = mcp_server.undo_last()
    assert result["success"] is False
    assert "nothing" in result["error"].lower()
