"""Tests for the host registry."""

from __future__ import annotations

import pytest

from cq_install.hosts import REGISTRY, HostDef, get_host


def test_registry_lists_all_four_hosts():
    assert set(REGISTRY) == {"cursor", "windsurf", "opencode", "claude"}


def test_get_host_returns_host_def():
    host = get_host("opencode")
    assert isinstance(host, HostDef)
    assert host.name == "opencode"


def test_get_host_unknown_raises():
    with pytest.raises(ValueError, match="unknown host"):
        get_host("vscode")


def test_windsurf_does_not_support_project():
    assert get_host("windsurf").supports_project is False


def test_claude_does_not_support_host_isolated():
    assert get_host("claude").supports_host_isolated is False
