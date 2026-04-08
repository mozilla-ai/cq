"""Idempotent file primitives for the cq installer."""

from __future__ import annotations

import json
from pathlib import Path

from cq_install.context import Action, ChangeResult


def remove_hook_entry(
    file: Path,
    hook_name: str,
    command: str,
    *,
    dry_run: bool = False,
) -> ChangeResult:
    """Remove a hook entry whose `command` matches exactly. Prune empty lists."""
    if not file.exists():
        return ChangeResult(action=Action.UNCHANGED, path=file)

    data = _load_json(file)
    hooks = data.get("hooks", {})
    entries = hooks.get(hook_name, [])
    remaining = [entry for entry in entries if entry.get("command") != command]
    if len(remaining) == len(entries):
        return ChangeResult(action=Action.UNCHANGED, path=file)

    if remaining:
        hooks[hook_name] = remaining
    else:
        del hooks[hook_name]

    if not dry_run:
        _write_json(file, data)
    return ChangeResult(action=Action.REMOVED, path=file)


def remove_json_entry(
    file: Path,
    path: list[str],
    *,
    prune_empty: bool = True,
    dry_run: bool = False,
) -> ChangeResult:
    """Remove the entry at `path` from `file`. Returns UNCHANGED if absent.

    If `prune_empty`, intermediate objects that become empty after the
    removal are also deleted, walking back up the path.
    """
    if not file.exists():
        return ChangeResult(action=Action.UNCHANGED, path=file)

    data = _load_json(file)
    parents: list[tuple[dict, str]] = []
    cursor: dict = data
    for key in path[:-1]:
        if not isinstance(cursor, dict) or key not in cursor:
            return ChangeResult(action=Action.UNCHANGED, path=file)
        parents.append((cursor, key))
        cursor = cursor[key]

    leaf_key = path[-1]
    if not isinstance(cursor, dict) or leaf_key not in cursor:
        return ChangeResult(action=Action.UNCHANGED, path=file)

    del cursor[leaf_key]

    if prune_empty:
        for parent, key in reversed(parents):
            if parent[key] == {}:
                del parent[key]
            else:
                break

    if not dry_run:
        _write_json(file, data)
    return ChangeResult(action=Action.REMOVED, path=file)


def upsert_hook_entry(
    file: Path,
    hook_name: str,
    command: str,
    *,
    extra_fields: dict | None = None,
    legacy_commands: list[str] | None = None,
    dry_run: bool = False,
) -> ChangeResult:
    """Add or update a single hook entry under `hooks.<hook_name>`.

    Removes any entry whose `command` matches a string in `legacy_commands`
    before inserting the desired entry. Idempotent: a second call with the
    same arguments returns UNCHANGED.
    """
    data = _load_json(file)
    hooks = data.setdefault("hooks", {})
    entries: list[dict] = list(hooks.get(hook_name, []))

    legacy = set(legacy_commands or [])
    filtered = [entry for entry in entries if entry.get("command") not in legacy]
    legacy_removed = len(filtered) != len(entries)

    desired_entry: dict = {"command": command}
    if extra_fields:
        desired_entry.update(extra_fields)

    found_index = next(
        (i for i, entry in enumerate(filtered) if entry.get("command") == command),
        None,
    )

    if found_index is None:
        filtered.append(desired_entry)
        action = Action.CREATED if not legacy_removed else Action.UPDATED
    else:
        existing = filtered[found_index]
        merged = dict(existing)
        changed = legacy_removed
        for key, value in desired_entry.items():
            if merged.get(key) != value:
                merged[key] = value
                changed = True
        if not changed:
            return ChangeResult(action=Action.UNCHANGED, path=file)
        filtered[found_index] = merged
        action = Action.UPDATED

    hooks[hook_name] = filtered
    if not dry_run:
        _write_json(file, data)
    return ChangeResult(action=action, path=file)


def upsert_json_entry(
    file: Path,
    path: list[str],
    desired: dict,
    *,
    dry_run: bool,
) -> ChangeResult:
    """Merge `desired` into `file` at the dotted path, preserving sibling fields.

    Creates the file and any intermediate objects on the path if missing.
    Returns CREATED if the leaf entry was absent, UPDATED if any managed
    field changed, UNCHANGED otherwise.
    """
    data = _load_json(file)
    parent = _walk_or_create(data, path[:-1])
    leaf_key = path[-1]

    existing = parent.get(leaf_key)
    if existing is None:
        parent[leaf_key] = dict(desired)
        action = Action.CREATED
    else:
        merged = dict(existing)
        changed = False
        for key, value in desired.items():
            if merged.get(key) != value:
                merged[key] = value
                changed = True
        if not changed:
            return ChangeResult(action=Action.UNCHANGED, path=file)
        parent[leaf_key] = merged
        action = Action.UPDATED

    if not dry_run:
        _write_json(file, data)
    return ChangeResult(action=action, path=file)


def _load_json(file: Path) -> dict:
    if not file.exists():
        return {}
    return json.loads(file.read_text())


def _walk_or_create(data: dict, path: list[str]) -> dict:
    cursor = data
    for key in path:
        if key not in cursor or not isinstance(cursor[key], dict):
            cursor[key] = {}
        cursor = cursor[key]
    return cursor


def _write_json(file: Path, data: dict) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, indent=2) + "\n")
