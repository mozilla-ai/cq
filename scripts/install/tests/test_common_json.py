"""Tests for JSON entry primitives in common.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cq_install.common import remove_json_entry, upsert_json_entry
from cq_install.context import Action


def test_upsert_creates_file_when_missing(tmp_path: Path):
    target = tmp_path / "mcp.json"
    result = upsert_json_entry(
        target,
        ["mcpServers", "cq"],
        {"command": "python3", "args": ["/x/bootstrap.py"]},
        dry_run=False,
    )
    assert result.action == Action.CREATED
    data = json.loads(target.read_text())
    assert data == {"mcpServers": {"cq": {"command": "python3", "args": ["/x/bootstrap.py"]}}}


def test_upsert_creates_intermediate_objects(tmp_path: Path):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"other": True}))
    upsert_json_entry(
        target,
        ["mcpServers", "cq"],
        {"command": "python3", "args": []},
        dry_run=False,
    )
    data = json.loads(target.read_text())
    assert data["other"] is True
    assert data["mcpServers"]["cq"]["command"] == "python3"


def test_upsert_unchanged_when_identical(tmp_path: Path):
    target = tmp_path / "mcp.json"
    desired = {"command": "python3", "args": ["/x/bootstrap.py"]}
    upsert_json_entry(target, ["mcpServers", "cq"], desired, dry_run=False)
    result = upsert_json_entry(target, ["mcpServers", "cq"], desired, dry_run=False)
    assert result.action == Action.UNCHANGED


def test_upsert_updates_stale_command(tmp_path: Path):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {"cq": {"command": "old", "args": ["/old"]}}}))
    result = upsert_json_entry(
        target,
        ["mcpServers", "cq"],
        {"command": "python3", "args": ["/new"]},
        dry_run=False,
    )
    assert result.action == Action.UPDATED
    data = json.loads(target.read_text())
    assert data["mcpServers"]["cq"]["command"] == "python3"
    assert data["mcpServers"]["cq"]["args"] == ["/new"]


def test_upsert_preserves_user_added_fields(tmp_path: Path):
    target = tmp_path / "mcp.json"
    target.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "cq": {
                        "command": "old",
                        "args": ["/old"],
                        "env": {"CQ_API_KEY": "secret"},  # pragma: allowlist secret
                    }
                }
            }
        )
    )
    result = upsert_json_entry(
        target,
        ["mcpServers", "cq"],
        {"command": "python3", "args": ["/new"]},
        dry_run=False,
    )
    assert result.action == Action.UPDATED
    data = json.loads(target.read_text())
    assert data["mcpServers"]["cq"]["env"] == {"CQ_API_KEY": "secret"}  # pragma: allowlist secret
    assert data["mcpServers"]["cq"]["command"] == "python3"


def test_upsert_dry_run_does_not_write(tmp_path: Path):
    target = tmp_path / "mcp.json"
    result = upsert_json_entry(
        target,
        ["mcpServers", "cq"],
        {"command": "python3", "args": []},
        dry_run=True,
    )
    assert result.action == Action.CREATED
    assert not target.exists()


def test_remove_deletes_entry_and_prunes_empty_parent(tmp_path: Path):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {"cq": {"command": "x"}}}))
    result = remove_json_entry(target, ["mcpServers", "cq"], dry_run=False)
    assert result.action == Action.REMOVED
    data = json.loads(target.read_text())
    assert "mcpServers" not in data


def test_remove_preserves_sibling_entries(tmp_path: Path):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {"cq": {"command": "x"}, "other": {"command": "y"}}}))
    remove_json_entry(target, ["mcpServers", "cq"], dry_run=False)
    data = json.loads(target.read_text())
    assert "cq" not in data["mcpServers"]
    assert data["mcpServers"]["other"] == {"command": "y"}


def test_remove_no_op_when_missing(tmp_path: Path):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"other": True}))
    result = remove_json_entry(target, ["mcpServers", "cq"], dry_run=False)
    assert result.action == Action.UNCHANGED


def test_remove_no_op_when_file_missing(tmp_path: Path):
    target = tmp_path / "mcp.json"
    result = remove_json_entry(target, ["mcpServers", "cq"], dry_run=False)
    assert result.action == Action.UNCHANGED


def test_upsert_malformed_json_raises_with_path(tmp_path: Path):
    target = tmp_path / "mcp.json"
    target.write_text("{ not valid json")
    with pytest.raises(RuntimeError) as exc_info:
        upsert_json_entry(
            target,
            ["mcpServers", "cq"],
            {"command": "python3"},
            dry_run=False,
        )
    assert str(target) in str(exc_info.value)


def test_upsert_non_dict_leaf_raises_with_path(tmp_path: Path):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {"cq": "not-a-dict"}}))
    with pytest.raises(ValueError) as exc_info:
        upsert_json_entry(
            target,
            ["mcpServers", "cq"],
            {"command": "python3"},
            dry_run=False,
        )
    assert str(target) in str(exc_info.value)
    assert "mcpServers" in str(exc_info.value)


def test_upsert_raises_on_non_dict_intermediate(tmp_path: Path):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": "not-a-dict"}))
    with pytest.raises(ValueError) as exc_info:
        upsert_json_entry(
            target,
            ["mcpServers", "cq"],
            {"command": "python3"},
            dry_run=False,
        )
    assert str(target) in str(exc_info.value)
    assert "mcpServers" in str(exc_info.value)
