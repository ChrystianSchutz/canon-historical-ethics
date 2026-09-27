"""`canon eval/probe/gandhi/openers` add a request timeout unless one is given."""

from __future__ import annotations

from canon.cli import DEFAULT_TIMEOUT_SECONDS, with_default_timeout


def test_timeout_is_added_when_missing() -> None:
    assert with_default_timeout(["--model", "m"]) == [
        "--model",
        "m",
        "--timeout",
        DEFAULT_TIMEOUT_SECONDS,
    ]


def test_explicit_timeout_is_kept() -> None:
    assert with_default_timeout(["--timeout", "60"]) == ["--timeout", "60"]
    assert with_default_timeout(["--timeout=60"]) == ["--timeout=60"]
