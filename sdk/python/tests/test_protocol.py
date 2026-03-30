"""Tests for the protocol module.

Validates the structure of the cq skill prompt to catch upstream changes.
Ported from cq-go/internal/protocol/protocol_test.go.
"""

from cq.protocol import prompt


def test_prompt_not_empty():
    assert len(prompt()) > 0


def test_prompt_has_frontmatter():
    p = prompt()
    assert p.startswith("---\n")
    parts = p.split("---\n", 2)
    assert len(parts) == 3
    assert "name: cq" in parts[1]
    assert "description:" in parts[1]


def test_prompt_contains_core_protocol():
    p = prompt()
    assert "## Core Protocol" in p
    assert "Before acting" in p
    assert "Apply guidance" in p
    assert "After learning something non-obvious" in p
    assert "before completing the task" in p


def test_prompt_contains_tool_sections():
    p = prompt()
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


def test_prompt_contains_query_guidance():
    p = prompt()
    assert "#### When Not to Query" in p
    assert "#### Formulating Domain Tags" in p
    assert "#### Interpreting Results" in p
    assert "Confidence > 0.7" in p
    assert "Confidence 0.5" in p
    assert "Confidence < 0.5" in p


def test_prompt_contains_proposal_guidance():
    p = prompt()
    assert "#### Writing Good Proposals" in p
    assert "#### Longevity Check" in p
    assert "#### Proposal Fields" in p


def test_prompt_contains_flag_reasons():
    p = prompt()
    assert "stale" in p
    assert "incorrect" in p
    assert "duplicate" in p


def test_prompt_contains_examples():
    p = prompt()
    assert "#### Example 1" in p
    assert "#### Example 2" in p
    assert "#### Example 3" in p
