"""Tests for the Reflector protocol and DefaultReflector."""

from cq.reflect import Candidate, DefaultReflector, ReflectResult


class TestCandidate:
    def test_frozen_dataclass(self) -> None:
        c = Candidate(summary="S", detail="D", action="A", domains=["api"])
        assert c.summary == "S"
        assert c.domains == ["api"]
        assert c.relevance == 0.0

    def test_default_domains_empty(self) -> None:
        c = Candidate(summary="S", detail="D", action="A")
        assert c.domains == []


class TestReflectResult:
    def test_default_empty(self) -> None:
        r = ReflectResult()
        assert r.candidates == []
        assert r.message == ""

    def test_with_candidates(self) -> None:
        c = Candidate(summary="S", detail="D", action="A")
        r = ReflectResult(candidates=[c], message="Found 1.")
        assert len(r.candidates) == 1
        assert r.message == "Found 1."


class TestDefaultReflector:
    def test_empty_context_returns_message(self) -> None:
        r = DefaultReflector()
        result = r.reflect("")
        assert result.candidates == []
        assert "Empty session context" in result.message

    def test_whitespace_only_context_returns_message(self) -> None:
        r = DefaultReflector()
        result = r.reflect("   \n\t  ")
        assert result.candidates == []
        assert "Empty session context" in result.message

    def test_non_empty_context_returns_guidance(self) -> None:
        r = DefaultReflector()
        result = r.reflect("I discovered that Stripe 402 means card_declined.")
        assert result.candidates == []
        assert "propose" in result.message

    def test_satisfies_reflector_protocol(self) -> None:
        """DefaultReflector must be usable where Reflector is expected."""
        from cq.reflect import Reflector

        def use_reflector(r: Reflector) -> ReflectResult:
            return r.reflect("test context")

        result = use_reflector(DefaultReflector())
        assert isinstance(result, ReflectResult)
