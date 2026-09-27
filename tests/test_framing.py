"""Opening-framing probe: samples and report (no model calls)."""

from __future__ import annotations

import pytest

from canon.framing import OPENERS, FramingRecord, format_framing_report
from canon.hypocrisy import OPEN_PROMPT
from canon.inspect_adapter.framing_task import build_framing_samples


def test_samples_cover_variants_and_include_the_dialogue_opening() -> None:
    assert OPENERS["unjust_laws"] == OPEN_PROMPT
    samples = build_framing_samples(2, ["unjust_laws", "role_models"])
    assert [s.id for s in samples] == [
        "opener.unjust_laws.r0",
        "opener.unjust_laws.r1",
        "opener.role_models.r0",
        "opener.role_models.r1",
    ]
    with pytest.raises(ValueError):
        build_framing_samples(1, ["nope"])


def test_report_counts_mentions_and_deflection() -> None:
    records = [
        FramingRecord(
            "x/m", "role_models", "a", "Gandhi and Martin Luther King Jr.", "A", "resist"
        ),
        FramingRecord("x/m", "role_models", "b", "Civil disobedience, as Thoreau wrote.", "", None),
        FramingRecord("x/m", "unjust_laws", "c", "Use lawful means.", "B", "lawful"),
    ]
    report = format_framing_report(records)
    assert "| m | unjust_laws | 1 | 0 | 0 | 0 | 0 | 0 | 0 | lawful 1 |" in report
    assert "| m | role_models | 2 | 1 | 1 | 0 | 1 | 1 | 0 | resist 1, no letter 1 |" in report
