"""Validate checked-in docs before publishing.

Checks all source files that will be published to the GitBook site for broken
internal links. External links are skipped so the checker stays fast and works
offline.

Usage:
    python scripts/check_docs.py
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"

# Source files outside docs/ that are published to the site.
# Must stay in sync with ROOT_FILES in prepare_gitbook_site.py.
PUBLISHED_ROOT_FILES: tuple[Path, ...] = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "DEVELOPMENT.md",
    REPO_ROOT / "LICENSE",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CONTRIBUTOR_AGREEMENT.md",
    REPO_ROOT / "cli" / "README.md",
    REPO_ROOT / "cli" / "DEVELOPMENT.md",
    REPO_ROOT / "sdk" / "go" / "README.md",
    REPO_ROOT / "sdk" / "go" / "DEVELOPMENT.md",
    REPO_ROOT / "sdk" / "python" / "README.md",
    REPO_ROOT / "sdk" / "python" / "DEVELOPMENT.md",
    REPO_ROOT / "server" / "backend" / "README.md",
)

# SUMMARY.md uses site-relative paths by design (GitBook navigation file).
# Source-relative resolution would produce false negatives, so skip it.
SKIP_LINK_CHECK: frozenset[Path] = frozenset({(DOCS_DIR / "SUMMARY.md").resolve()})

LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)\n]+)\)|(?<!!)\[([^\]]*)\]\(([^)\n]+)\)")
HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CODE_FENCE_RE = re.compile(r"^```")
SKIPPED_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:")


def all_published_sources() -> set[Path]:
    """Return resolved paths of every source file that will appear in the site."""
    sources = {p.resolve() for p in PUBLISHED_ROOT_FILES if p.exists()}
    sources.update(p.resolve() for p in DOCS_DIR.rglob("*") if p.is_file())
    return sources


def strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks so code samples are not linted as page links."""
    output: list[str] = []
    in_fence = False

    for line in text.splitlines():
        if CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            output.append("")
            continue
        output.append("" if in_fence else line)

    return "\n".join(output)


def slugify_heading(raw_heading: str) -> str:
    """Approximate the anchor slugs used by common Markdown site generators."""
    heading = re.sub(r"`([^`]*)`", r"\1", raw_heading.strip().lower())
    heading = re.sub(r"[^\w\s-]", "", heading)
    heading = re.sub(r"\s+", "-", heading)
    heading = re.sub(r"-{2,}", "-", heading)
    return heading.strip("-")


def extract_anchors(path: Path) -> set[str]:
    """Collect heading anchors from a Markdown document."""
    anchors: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADER_RE.match(line)
        if match:
            anchors.add(slugify_heading(match.group(2)))
    return anchors


def split_target(raw_target: str) -> tuple[str, str]:
    """Split a Markdown link target into path and optional anchor."""
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if " " in target and not target.startswith("#"):
        target = target.split(" ", 1)[0]
    if "#" in target:
        path_part, anchor = target.split("#", 1)
        return path_part, anchor
    return target, ""


def resolve_target(source_path: Path, target_path: str) -> Path | None:
    """Resolve a relative link target from a source file.

    Returns None for directory targets with no publishable index (source-code
    directory references) rather than raising an error.
    """
    base = source_path.parent
    resolved = (base / target_path).resolve()

    if resolved.is_dir():
        for name in ("README.md", "index.md"):
            candidate = resolved / name
            if candidate.exists():
                return candidate
        return resolved  # Directory with no index; caller will flag as unpublished

    if resolved.exists():
        return resolved

    if resolved.suffix == "":
        md = resolved.with_suffix(".md")
        if md.exists():
            return md

    return resolved  # May not exist; caller checks


def validate_summary(errors: list[str]) -> None:
    """Ensure docs/SUMMARY.md exists."""
    if not (DOCS_DIR / "SUMMARY.md").exists():
        errors.append("docs/SUMMARY.md is missing")


def iter_link_targets(text: str) -> list[str]:
    """Extract raw link targets from Markdown text (code blocks already stripped)."""
    targets: list[str] = []
    for m in LINK_RE.finditer(text):
        raw = m.group(1) or m.group(3)
        if raw:
            targets.append(raw)
    return targets


def main() -> int:
    """Validate docs links and anchors. Returns a process exit code."""
    errors: list[str] = []
    published = all_published_sources()

    anchors_by_file: dict[Path, set[str]] = {}
    for path in published:
        if path.suffix == ".md":
            anchors_by_file[path] = extract_anchors(path)

    validate_summary(errors)

    sources_to_check = [
        p for p in sorted(published)
        if p.suffix == ".md" and p not in SKIP_LINK_CHECK
    ]

    for source_path in sources_to_check:
        text = strip_code_blocks(source_path.read_text(encoding="utf-8"))

        for raw_target in iter_link_targets(text):
            if raw_target.startswith(SKIPPED_PREFIXES):
                continue

            target_path, anchor = split_target(raw_target)

            if target_path == "":
                target_file = source_path
            else:
                target_file = resolve_target(source_path, target_path)
                if not target_file.exists():
                    errors.append(
                        f"{source_path.relative_to(REPO_ROOT)} -> missing target `{target_path}`"
                    )
                    continue
                if target_file.resolve() not in published:
                    errors.append(
                        f"{source_path.relative_to(REPO_ROOT)} -> `{target_path}` exists but is not published to the site"
                    )
                    continue

            if anchor and target_file.suffix == ".md":
                target_anchors = anchors_by_file.get(target_file.resolve())
                if target_anchors is not None and slugify_heading(anchor) not in target_anchors:
                    errors.append(
                        f"{source_path.relative_to(REPO_ROOT)} -> missing anchor `#{anchor}` in "
                        f"{target_file.relative_to(REPO_ROOT)}"
                    )

    if errors:
        print("Documentation checks failed:\n")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Documentation checks passed ({len(sources_to_check)} files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
