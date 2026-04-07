"""Internal helpers shared across cq modules."""


def _as_list(value: list[str] | str) -> list[str]:
    """Coerce a bare string to a single-item list.

    Python iterates strings character-by-character, so passing ``"python"``
    where ``["python"]`` is expected silently produces wrong results.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    raise TypeError(f"expected list[str] or str, got {type(value).__name__}")
