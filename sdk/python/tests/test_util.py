"""Tests for the _as_list internal helper."""

import pytest

from cq._util import _as_list


class TestAsList:
    def test_bare_string_becomes_single_item_list(self):
        assert _as_list("python") == ["python"]

    def test_list_passes_through(self):
        assert _as_list(["python", "go"]) == ["python", "go"]

    def test_empty_list_passes_through(self):
        assert _as_list([]) == []

    def test_tuple_raises_type_error(self):
        with pytest.raises(TypeError):
            _as_list(("python",))  # type: ignore[arg-type]

    def test_int_raises_type_error(self):
        with pytest.raises(TypeError):
            _as_list(42)  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            _as_list(None)  # type: ignore[arg-type]
