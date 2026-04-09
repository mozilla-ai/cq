"""Idempotent file primitives for the cq installer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cq_install.context import Action, ChangeResult
from cq_install.manifest import hash_file, load_manifest, write_manifest


def copy_tree(
    src: Path,
    dst: Path,
    *,
    manifest_name: str,
    dry_run: bool = False,
) -> ChangeResult:
    """Copy `src` recursively into `dst`, tracking files in a manifest.

    Re-runs are idempotent: unchanged files stay UNCHANGED, modified
    sources overwrite stale destinations, and files removed from the
    source are removed from the destination on the next run.
    """
    desired_files = sorted(p for p in src.rglob("*") if p.is_file())
    return _copy_files(src, dst, desired_files, manifest_name=manifest_name, dry_run=dry_run)


def _copy_files(
    src_root: Path,
    dst_root: Path,
    desired_files: list[Path],
    *,
    manifest_name: str,
    dry_run: bool = False,
) -> ChangeResult:
    manifest_path = dst_root / manifest_name
    new_entries: list[dict] = []
    any_change = False
    previous = load_manifest(manifest_path) or {"files": []}
    previous_paths = {entry["path"] for entry in previous.get("files", [])}

    for source_file in desired_files:
        rel = source_file.relative_to(src_root).as_posix()
        target_file = dst_root / rel
        digest = hash_file(source_file)
        new_entries.append({"path": rel, "sha256": digest})

        if target_file.exists() and hash_file(target_file) == digest:
            continue

        any_change = True
        if not dry_run:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_bytes(source_file.read_bytes())

    desired_paths = {entry["path"] for entry in new_entries}
    for stale_rel in previous_paths - desired_paths:
        stale_path = dst_root / stale_rel
        if stale_path.exists():
            any_change = True
            if not dry_run:
                stale_path.unlink()

    is_first_install = not manifest_path.exists()
    if not any_change and not is_first_install:
        return ChangeResult(action=Action.UNCHANGED, path=dst_root)

    if not dry_run:
        write_manifest(manifest_path, new_entries)

    action = Action.CREATED if is_first_install else Action.UPDATED
    return ChangeResult(action=action, path=dst_root)


def copy_selected_paths(
    src_root: Path,
    dst_root: Path,
    *,
    relpaths: list[Path],
    manifest_name: str,
    dry_run: bool = False,
) -> ChangeResult:
    """Copy selected files or directories under `src_root` into `dst_root`.

    Each entry in `relpaths` is relative to `src_root`. Directory entries are
    copied recursively. The manifest records files relative to `src_root`, so
    re-runs remain idempotent and uninstall can remove only installer-owned
    files.
    """
    desired_files: list[Path] = []
    for relpath in relpaths:
        source = src_root / relpath
        if source.is_file():
            desired_files.append(source)
            continue
        if source.is_dir():
            desired_files.extend(sorted(path for path in source.rglob("*") if path.is_file()))
            continue
        raise FileNotFoundError(f"installer source path missing: {source}")

    return _copy_files(
        src_root,
        dst_root,
        desired_files,
        manifest_name=manifest_name,
        dry_run=dry_run,
    )


def remove_copied_tree(
    dst: Path,
    *,
    manifest_name: str,
    dry_run: bool = False,
) -> ChangeResult:
    """Remove files listed in the manifest, skipping any that were user-modified."""
    manifest_path = dst / manifest_name
    manifest = load_manifest(manifest_path)
    if manifest is None:
        return ChangeResult(action=Action.UNCHANGED, path=dst)

    skipped_any = False
    for entry in manifest["files"]:
        target = dst / entry["path"]
        if not target.exists():
            continue
        if hash_file(target) != entry["sha256"]:
            skipped_any = True
            continue
        if not dry_run:
            target.unlink()
            _prune_empty_dirs(target.parent, dst)

    if skipped_any:
        return ChangeResult(
            action=Action.SKIPPED,
            path=dst,
            detail="user-modified files left in place",
        )

    if not dry_run:
        manifest_path.unlink(missing_ok=True)
    return ChangeResult(action=Action.REMOVED, path=dst)


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
    if not isinstance(data, dict):
        return ChangeResult(
            action=Action.SKIPPED,
            path=file,
            detail=f"invalid hooks config in {file}: expected top-level JSON object",
        )
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return ChangeResult(
            action=Action.SKIPPED,
            path=file,
            detail=f"invalid hooks config in {file}: expected 'hooks' to be an object",
        )
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


def remove_markdown_block(
    file: Path,
    start_marker: str,
    end_marker: str,
    *,
    dry_run: bool = False,
) -> ChangeResult:
    """Remove a delimited block from a Markdown file.

    Deletes the file entirely if it becomes empty after the block is removed.
    """
    if not file.exists():
        return ChangeResult(action=Action.UNCHANGED, path=file)

    text = file.read_text()
    start_idx = text.find(start_marker)
    end_idx = text.find(end_marker)
    if start_idx == -1:
        return ChangeResult(action=Action.UNCHANGED, path=file)
    if end_idx == -1 or end_idx < start_idx:
        return ChangeResult(
            action=Action.SKIPPED,
            path=file,
            detail="start marker present without matching end marker",
        )

    block_end = end_idx + len(end_marker)
    new_text = (text[:start_idx] + text[block_end:]).strip("\n")

    if not new_text:
        if not dry_run:
            file.unlink()
        return ChangeResult(action=Action.REMOVED, path=file)

    if not dry_run:
        file.write_text(new_text + "\n")
    return ChangeResult(action=Action.REMOVED, path=file)


def remove_owned_file(
    path: Path,
    expected_content_hash: str | None,
    *,
    dry_run: bool = False,
) -> ChangeResult:
    """Remove a file we created. Skip with advisory if the user has edited it."""
    if not path.exists():
        return ChangeResult(action=Action.UNCHANGED, path=path)

    if expected_content_hash is not None:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected_content_hash:
            return ChangeResult(
                action=Action.SKIPPED,
                path=path,
                detail="file modified since install; left in place",
            )

    if not dry_run:
        path.unlink()
    return ChangeResult(action=Action.REMOVED, path=path)


def symlink_tree(src: Path, dst: Path, *, dry_run: bool = False) -> ChangeResult:
    """Create or update a symlink at `dst` pointing at `src`."""
    if dst.is_symlink():
        if dst.resolve() == src.resolve():
            return ChangeResult(action=Action.UNCHANGED, path=dst)
        if not dry_run:
            dst.unlink()
            dst.symlink_to(src, target_is_directory=src.is_dir())
        return ChangeResult(action=Action.UPDATED, path=dst)

    if dst.exists():
        return ChangeResult(
            action=Action.SKIPPED,
            path=dst,
            detail="destination exists and is not a symlink",
        )

    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.symlink_to(src, target_is_directory=src.is_dir())
    return ChangeResult(action=Action.CREATED, path=dst)


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
    if not isinstance(data, dict):
        raise ValueError(f"invalid hooks config in {file}: expected top-level JSON object, found {type(data).__name__}")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(
            f"invalid hooks config in {file}: expected 'hooks' to be an object, found {type(hooks).__name__}"
        )
    raw_entries = hooks.get(hook_name, [])
    if not isinstance(raw_entries, list):
        raise ValueError(
            f"invalid hooks config in {file}: expected hooks.{hook_name} to be a list, "
            f"found {type(raw_entries).__name__}"
        )
    entries: list[dict] = [dict(entry) for entry in raw_entries if isinstance(entry, dict)]

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
    return ChangeResult(action=action, path=file, detail=hook_name)


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
    parent = _walk_or_create(data, path[:-1], file=file)
    leaf_key = path[-1]

    existing = parent.get(leaf_key)
    if existing is None:
        parent[leaf_key] = dict(desired)
        action = Action.CREATED
    else:
        if not isinstance(existing, dict):
            dotted = ".".join(path)
            raise ValueError(f"invalid config in {file}: expected object at {dotted}, found {type(existing).__name__}")
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


def upsert_markdown_block(
    file: Path,
    start_marker: str,
    end_marker: str,
    content: str,
    *,
    dry_run: bool = False,
) -> ChangeResult:
    """Insert or replace a delimited block in a Markdown file.

    `content` must include the start and end markers; the primitive does
    not synthesize them. The block is appended to existing files (with a
    leading blank line separator) or used as the file body when creating.
    """
    if not file.exists():
        if not dry_run:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content + "\n")
        return ChangeResult(action=Action.CREATED, path=file)

    text = file.read_text()
    start_idx = text.find(start_marker)
    end_idx = text.find(end_marker)

    if start_idx == -1:
        new_text = text.rstrip("\n") + "\n\n" + content + "\n"
        if not dry_run:
            file.write_text(new_text)
        return ChangeResult(action=Action.UPDATED, path=file)

    if end_idx == -1 or end_idx < start_idx:
        return ChangeResult(
            action=Action.SKIPPED,
            path=file,
            detail="start marker present without matching end marker",
        )

    block_end = end_idx + len(end_marker)
    existing_block = text[start_idx:block_end]
    if existing_block == content:
        return ChangeResult(action=Action.UNCHANGED, path=file)

    new_text = text[:start_idx] + content + text[block_end:]
    if not dry_run:
        file.write_text(new_text)
    return ChangeResult(action=Action.UPDATED, path=file)


def write_if_missing(path: Path, content: str, *, dry_run: bool = False) -> ChangeResult:
    r"""Create the file with `content` if absent. Never overwrite existing files.

    Uses newline="\n" to preserve Unix line endings on all platforms,
    ensuring consistent hash checksums regardless of the OS.
    """
    if path.exists():
        return ChangeResult(action=Action.UNCHANGED, path=path)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, newline="\n")
    return ChangeResult(action=Action.CREATED, path=path)


def _load_json(file: Path) -> dict:
    if not file.exists():
        return {}
    try:
        return json.loads(file.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in config file {file}: {exc}") from exc


def _prune_empty_dirs(directory: Path, stop_at: Path) -> None:
    cursor = directory
    while cursor != stop_at and cursor.exists() and not any(cursor.iterdir()):
        cursor.rmdir()
        cursor = cursor.parent


def _walk_or_create(data: dict, path: list[str], *, file: Path | None = None) -> dict:
    cursor = data
    traversed: list[str] = []
    for key in path:
        traversed.append(key)
        existing = cursor.get(key)
        if existing is None:
            cursor[key] = {}
        elif not isinstance(existing, dict):
            dotted = ".".join(traversed)
            location = f" in {file}" if file else ""
            raise ValueError(f"invalid config{location}: expected object at {dotted}, found {type(existing).__name__}")
        cursor = cursor[key]
    return cursor


def _write_json(file: Path, data: dict) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, indent=2) + "\n")
