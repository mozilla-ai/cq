"""Prepare a deployable GitBook site in site/.

Copies docs/ into site/ and maps root files (README.md → index.md,
CONTRIBUTING.md, DEVELOPMENT.md, LICENSE, SECURITY.md) and component docs
(cli/, sdk/, server/) into the site. Rewrites relative links in every
published file so they resolve correctly in the new site structure.
Also expands {{#include path/to/file}} markers.

Usage:
    python scripts/prepare_gitbook_site.py
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
SITE_DIR = REPO_ROOT / "site"
INCLUDE_PREFIX = "{{#include "
INCLUDE_SUFFIX = "}}"
ROOT_FILES = {
    REPO_ROOT / ".gitbook.yaml": SITE_DIR / ".gitbook.yaml",
    REPO_ROOT / ".gitbook-branch-readme.md": SITE_DIR / "README-BRANCH.md",
    REPO_ROOT / "README.md": SITE_DIR / "index.md",
    REPO_ROOT / "CONTRIBUTING.md": SITE_DIR / "CONTRIBUTING.md",
    REPO_ROOT / "DEVELOPMENT.md": SITE_DIR / "DEVELOPMENT.md",
    REPO_ROOT / "LICENSE": SITE_DIR / "LICENSE",
    REPO_ROOT / "SECURITY.md": SITE_DIR / "SECURITY.md",
    REPO_ROOT / "CONTRIBUTOR_AGREEMENT.md": SITE_DIR / "CONTRIBUTOR_AGREEMENT.md",
    REPO_ROOT / "cli" / "README.md": SITE_DIR / "cli" / "README.md",
    REPO_ROOT / "cli" / "DEVELOPMENT.md": SITE_DIR / "cli" / "DEVELOPMENT.md",
    REPO_ROOT / "sdk" / "go" / "README.md": SITE_DIR / "sdk" / "go" / "README.md",
    REPO_ROOT / "sdk" / "go" / "DEVELOPMENT.md": SITE_DIR / "sdk" / "go" / "DEVELOPMENT.md",
    REPO_ROOT / "sdk" / "python" / "README.md": SITE_DIR / "sdk" / "python" / "README.md",
    REPO_ROOT / "sdk" / "python" / "DEVELOPMENT.md": SITE_DIR / "sdk" / "python" / "DEVELOPMENT.md",
    REPO_ROOT / "server" / "backend" / "README.md": SITE_DIR / "server" / "README.md",
}
IGNORE_PATTERNS = shutil.ignore_patterns(".DS_Store", "__pycache__")

LINK_RE = re.compile(r"(!?\[[^\]]*\])\(([^)\n]+)\)")
CODE_FENCE_RE = re.compile(r"^```")
SKIPPED_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:", "#")


def build_path_map() -> dict[Path, Path]:
    """Return a mapping of resolved source paths to resolved site paths."""
    path_map: dict[Path, Path] = {}
    for src in DOCS_DIR.rglob("*"):
        rel = src.relative_to(DOCS_DIR)
        path_map[src.resolve()] = (SITE_DIR / rel).resolve()
    for src, dest in ROOT_FILES.items():
        if src.exists():
            path_map[src.resolve()] = dest.resolve()
    return path_map


def rewrite_links(site_file: Path, source_file: Path, path_map: dict[Path, Path]) -> None:
    """Rewrite relative links so they resolve correctly within the published site."""
    lines = site_file.read_text(encoding="utf-8").splitlines()
    output_lines: list[str] = []
    in_fence = False

    for line in lines:
        if CODE_FENCE_RE.match(line.strip()):
            in_fence = not in_fence
        if in_fence:
            output_lines.append(line)
            continue

        def replace(m: re.Match, _src: Path = source_file, _site: Path = site_file) -> str:
            label = m.group(1)
            raw = m.group(2).strip()

            if raw.startswith(SKIPPED_PREFIXES):
                return m.group(0)

            anchor = ""
            target_str = raw
            if not raw.startswith("#") and "#" in raw:
                target_str, frag = raw.split("#", 1)
                anchor = f"#{frag}"
            elif raw.startswith("#"):
                return m.group(0)

            if not target_str:
                return m.group(0)

            resolved = (_src.parent / target_str).resolve()
            if resolved.is_dir():
                # Try common index files for directory references
                for name in ("README.md", "index.md"):
                    candidate = (resolved / name).resolve()
                    if candidate in path_map:
                        resolved = candidate
                        break
                else:
                    return m.group(0)  # Source dir without a publishable index; leave as-is

            site_target = path_map.get(resolved)
            if site_target is None:
                return m.group(0)  # Target not in published set; leave as-is

            rel = os.path.relpath(site_target, _site.parent)
            return f"{label}({rel}{anchor})"

        output_lines.append(LINK_RE.sub(replace, line))

    site_file.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def expand_includes(path: Path) -> None:
    """Replace explicit include markers with canonical file contents.

    The marker syntax is intentionally narrow and line-based:

        {{#include path/to/file}}

    The included file path is resolved relative to the repository root.
    """
    output_lines: list[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(INCLUDE_PREFIX) and stripped.endswith(INCLUDE_SUFFIX):
            include_path = stripped[len(INCLUDE_PREFIX) : -len(INCLUDE_SUFFIX)].strip()
            source_path = REPO_ROOT / include_path
            if not source_path.exists():
                raise FileNotFoundError(
                    f"Missing include `{include_path}` referenced from {path.relative_to(REPO_ROOT)}"
                )

            output_lines.extend(source_path.read_text(encoding="utf-8").splitlines())
            continue

        output_lines.append(line)

    path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def main() -> None:
    """Rebuild the GitBook publication directory from checked-in docs."""
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)

    shutil.copytree(DOCS_DIR, SITE_DIR, ignore=IGNORE_PATTERNS)

    for src, dest in ROOT_FILES.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    path_map = build_path_map()
    site_to_src = {site: src for src, site in path_map.items()}

    for md_file in sorted(SITE_DIR.rglob("*.md")):
        expand_includes(md_file)
        source = site_to_src.get(md_file.resolve())
        if source is not None:
            rewrite_links(md_file, source, path_map)

    md_files = sorted(SITE_DIR.rglob("*.md"))
    print(f"Prepared {len(md_files)} markdown files in {SITE_DIR}/")


if __name__ == "__main__":
    main()
