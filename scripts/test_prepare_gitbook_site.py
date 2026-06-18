"""Tests for prepare_gitbook_site helpers."""

from __future__ import annotations

from prepare_gitbook_site import _inject_version_badge


class TestInjectVersionBadge:
    def test_inserts_after_heading_with_blank_line(self) -> None:
        content = "# Title\n\nBody text"
        result = _inject_version_badge(content, "1.2.3")
        assert result == "# Title\n\n*Version: 1.2.3*\n\nBody text"

    def test_inserts_after_heading_without_blank_line(self) -> None:
        content = "# Title\nBody text"
        result = _inject_version_badge(content, "1.2.3")
        assert result == "# Title\n*Version: 1.2.3*\n\nBody text"

    def test_no_heading_returns_unchanged(self) -> None:
        content = "No heading here"
        result = _inject_version_badge(content, "1.0.0")
        assert result == content

    def test_only_first_heading_is_modified(self) -> None:
        content = "# First\n\nText\n\n# Second\n\nMore text"
        result = _inject_version_badge(content, "2.0.0")
        assert result.count("*Version:") == 1
        assert result.startswith("# First\n\n*Version: 2.0.0*\n\nText")

    def test_heading_only_content(self) -> None:
        content = "# Title"
        result = _inject_version_badge(content, "0.1.0")
        assert result == "# Title\n*Version: 0.1.0*\n"

    def test_h2_not_treated_as_top_level(self) -> None:
        content = "## Subtitle\n\nBody"
        result = _inject_version_badge(content, "1.0.0")
        assert result == content
