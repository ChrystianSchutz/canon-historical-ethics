from __future__ import annotations

from canon.provenance import case_hash
from canon.schema import Case
from canon.summary import AnswerRecord, format_summary, outcome_counts, rule_rates


def _records(case: Case, model: str, cell_id: str, outcomes: list[str]) -> list[AnswerRecord]:
    return [
        AnswerRecord(
            model=model,
            case_id=case.id,
            case_sha256=case_hash(case),
            cell_id=cell_id,
            replicate=i,
            outcome=outcome,
        )
        for i, outcome in enumerate(outcomes)
    ]


def test_rule_rates_count_hits_including_refusals_in_denominator(case: Case) -> None:
    records = [
        *_records(case, "m", "observer.named.carried", ["impermissible", "permissible", "REFUSAL"]),
        *_records(case, "m", "executor.named.stripped", ["imprisonment", "discharge"]),
    ]
    (rate,) = rule_rates(records, [case])
    assert (rate.if_hits, rate.if_n) == (1, 3)
    assert (rate.then_hits, rate.then_n) == (1, 2)
    assert outcome_counts(records)[("m", case.id, "observer.named.carried")]["REFUSAL"] == 1


def test_summary_warns_when_case_changed(case: Case) -> None:
    records = _records(case, "m", "observer.named.carried", ["impermissible"])
    stale = [r.__class__(**{**r.__dict__, "case_sha256": "0" * 64}) for r in records]
    assert "sha256 mismatch" in format_summary(stale, [case])
    assert "Warnings" not in format_summary(records, [case])
