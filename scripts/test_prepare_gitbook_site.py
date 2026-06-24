"""Tests for prepare_gitbook_site helpers."""

from __future__ import annotations

from prepare_gitbook_site import _inject_version_badge


class TestInjectVersionBadge:
    def test_inserts_after_heading_with_blank_line(self) -> None:
        content = "# Title\n\nBody text"
        result = _inject_version_badge(content, "1.2.3")
        expected = (
            '# Title\n\n{% hint style="info" icon="tag" %}\n'
            "Version: 1.2.3\n{% endhint %}\n\nBody text"
        )
        assert result == expected

    def test_inserts_after_heading_without_blank_line(self) -> None:
        content = "# Title\nBody text"
        result = _inject_version_badge(content, "1.2.3")
        expected = (
            '# Title\n{% hint style="info" icon="tag" %}\n'
            "Version: 1.2.3\n{% endhint %}\n\nBody text"
        )
        assert result == expected

    def test_no_heading_returns_unchanged(self) -> None:
        content = "No heading here"
        result = _inject_version_badge(content, "1.0.0")
        assert result == content

    def test_only_first_heading_is_modified(self) -> None:
        content = "# First\n\nText\n\n# Second\n\nMore text"
        result = _inject_version_badge(content, "2.0.0")
        assert result.count("Version: ") == 1
        assert '{% hint style="info" icon="tag" %}' in result

    def test_heading_only_content(self) -> None:
        content = "# Title"
        result = _inject_version_badge(content, "0.1.0")
        expected = (
            '# Title\n{% hint style="info" icon="tag" %}\n'
            "Version: 0.1.0\n{% endhint %}\n"
        )
        assert result == expected

    def test_h2_not_treated_as_top_level(self) -> None:
        content = "## Subtitle\n\nBody"
        result = _inject_version_badge(content, "1.0.0")
        assert result == content

    def test_heading_inside_code_fence_is_skipped(self) -> None:
        content = "```\n# Not a heading\n```\n\n# Real heading\n\nBody"
        result = _inject_version_badge(content, "1.0.0")
        assert "Version: 1.0.0" in result
        assert result.index("Version: 1.0.0") > result.index("# Real heading")
