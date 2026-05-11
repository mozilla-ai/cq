"""Prepare a deployable GitBook site in site/.

Copies docs/ into site/ and maps root files (README.md → index.md,
CONTRIBUTING.md, DEVELOPMENT.md) into the site root alongside the GitBook
metadata files. Also expands {{#include path/to/file}} markers so docs pages
can reference canonical source files without duplicating long code blocks.

Usage:
    python scripts/prepare_gitbook_site.py
"""

from __future__ import annotations

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
    REPO_ROOT / "cli" / "README.md": SITE_DIR / "cli" / "README.md",
    REPO_ROOT / "cli" / "DEVELOPMENT.md": SITE_DIR / "cli" / "DEVELOPMENT.md",
    REPO_ROOT / "sdk" / "go" / "README.md": SITE_DIR / "sdk" / "go" / "README.md",
    REPO_ROOT / "sdk" / "go" / "DEVELOPMENT.md": SITE_DIR / "sdk" / "go" / "DEVELOPMENT.md",
    REPO_ROOT / "sdk" / "python" / "README.md": SITE_DIR / "sdk" / "python" / "README.md",
    REPO_ROOT / "sdk" / "python" / "DEVELOPMENT.md": SITE_DIR / "sdk" / "python" / "DEVELOPMENT.md",
    REPO_ROOT / "server" / "backend" / "README.md": SITE_DIR / "server" / "README.md",
}
IGNORE_PATTERNS = shutil.ignore_patterns(".DS_Store", "__pycache__")


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

    for md_file in sorted(SITE_DIR.rglob("*.md")):
        expand_includes(md_file)

    md_files = sorted(SITE_DIR.rglob("*.md"))
    print(f"Prepared {len(md_files)} markdown files in {SITE_DIR}/")


if __name__ == "__main__":
    main()
