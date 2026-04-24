"""Tests for the prompts module.

Validates the structure of the canonical cq agent prompts to catch upstream
changes in the authoring sources.
"""

from cq.prompts import reflect, skill


def _normalize(body: str) -> str:
    """Collapse CRLF to LF so frontmatter assertions are not sensitive to
    Windows checkouts where ``core.autocrlf`` rewrites package-data Markdown.
    """
    return body.replace("\r\n", "\n")


def test_skill_not_empty():
    assert len(skill()) > 0


def test_skill_has_frontmatter():
    p = _normalize(skill())
    assert p.startswith("---\n")
    parts = p.split("---\n", 2)
    assert len(parts) == 3
    assert "name: cq" in parts[1]
    assert "description:" in parts[1]


def test_skill_contains_core_protocol():
    p = skill()
    assert "## Core Protocol" in p
    assert "Before acting" in p
    assert "Apply guidance" in p
    assert "After learning something non-obvious" in p
    assert "before completing the task" in p


def test_skill_contains_tool_sections():
    p = skill()
    sections = [
        "### Querying Knowledge (`query`)",
        "### Proposing Knowledge (`propose`)",
        "### Confirming Knowledge (`confirm`)",
        "### Flagging Knowledge (`flag`)",
        "### Session Reflection (`reflect`)",
        "### Post-Error Behaviour",
        "### Examples",
    ]
    for section in sections:
        assert section in p, f"missing section: {section}"


def test_skill_contains_query_guidance():
    p = skill()
    assert "#### When Not to Query" in p
    assert "#### Formulating Domain Tags" in p
    assert "#### Interpreting Results" in p
    assert "Confidence > 0.7" in p
    assert "Confidence 0.5" in p
    assert "Confidence < 0.5" in p


def test_skill_contains_proposal_guidance():
    p = skill()
    assert "#### Writing Good Proposals" in p
    assert "#### Longevity Check" in p
    assert "#### Proposal Fields" in p


def test_skill_contains_flag_reasons():
    p = skill()
    assert "stale" in p
    assert "incorrect" in p
    assert "duplicate" in p


def test_skill_contains_examples():
    p = skill()
    assert "#### Example 1" in p
    assert "#### Example 2" in p
    assert "#### Example 3" in p


def test_reflect_not_empty():
    assert len(reflect()) > 0


def test_reflect_has_frontmatter():
    p = _normalize(reflect())
    assert p.startswith("---\n")
    parts = p.split("---\n", 2)
    assert len(parts) == 3
    assert "name: cq:reflect" in parts[1]
    assert "description:" in parts[1]


def test_reflect_contains_workflow_steps():
    p = reflect()
    sections = [
        "### Step 1",
        "### Step 2",
        "### Step 3",
        "### Step 4",
        "### Step 5",
        "### Step 6",
    ]
    for section in sections:
        assert section in p, f"missing section: {section}"
