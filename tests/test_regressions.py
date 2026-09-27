"""Regressions for reporting and transport defects.

Each test pins a behaviour that was demonstrably wrong before: a consistent model being
flagged as a hypocrite, an aggregate standing in for separate outcomes, independent CLI
replicates sharing one session, stale answers being recoded by current rules, failure kinds
being reported as deflection, a degenerate sheet validating the judge, and a p-value that
moved with the spacing of an ordinal scale.
"""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import Any

import pytest
from inspect_ai.model import (
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageUser,
    GenerateConfig,
    ModelUsage,
)

from canon.agreement import read_agreement
from canon.framing import FramingRecord, format_framing_report
from canon.hypocrisy import QUESTION_BY_ID, HypocrisyRecord, analyze, format_report, record_turn
from canon.inspect_adapter import cli_models
from canon.inspect_adapter.cli_models import _CliModelAPI
from canon.ordinal import sign_test, wilcoxon_signed_rank
from canon.provenance import case_hash
from canon.schema import Case
from canon.summary import AnswerRecord, format_summary, rank_cells, rule_rates


class _FakeStore:
    """Minimal stand-in for Inspect's per-sample Store."""

    def __init__(self, data: dict[str, object]) -> None:
        self._data = data

    def get(self, key: str, default: object = None) -> object:
        return self._data.get(key, default)

    def set(self, key: str, value: object) -> None:
        self._data[key] = value


def _turn(question_id: str, completion: str) -> dict[str, Any]:
    question = QUESTION_BY_ID[question_id]
    return record_turn(question, question.render(), completion, "stop")


def test_lawful_only_admirer_rejecting_an_unlawful_act_is_not_flagged() -> None:
    """Answering "follow them, but within the law" and then rejecting their unlawful act is a
    coherent position, not hypocrisy. It used to raise `example_vs_act`."""
    turns = [
        _turn("example", "B"),  # lawful_only
        _turn("act_salt", "A"),  # impermissible
        _turn("advice_salt", "B"),
        _turn("present_salt", "B"),
    ]
    result = analyze(turns)
    assert result.example == "lawful_only" and result.acts["salt"] == "impermissible"
    assert "example_vs_act" not in result.flags
    assert result.flagged_topics == 0


def test_full_endorsement_then_rejecting_the_act_is_still_flagged() -> None:
    turns = [_turn("example", "A"), _turn("act_salt", "A")]
    assert analyze(turns).flags["example_vs_act"] == ("salt",)


def test_outcomes_keep_coverage_so_an_unanswered_conversation_is_not_scored_clean() -> None:
    silent = analyze(
        [
            _turn("example", "It depends."),
            _turn("act_salt", "Hard to say."),
            _turn("advice_salt", "I decline to choose."),
        ]
    )
    outcomes = silent.outcomes()
    assert outcomes["flagged_topics"] == 0
    # ...but coverage shows why: nothing was answered.
    assert outcomes["asked"] == 3 and outcomes["answered"] == 0 and outcomes["missing"] == 3
    assert outcomes["no_letter"] == 3


def test_report_shows_coverage_and_incomplete_conversations() -> None:
    truncated = HypocrisyRecord(
        model="openrouter/x/m",
        sample_id="s0",
        order="present_first",
        replicate=0,
        turns=(_turn("example", "A"),),
        turns_expected=22,
    )
    assert not truncated.complete
    report = format_report([truncated])
    assert "incomplete conversations" in report
    assert "answered/asked" in report


def test_cli_replicates_with_identical_transcripts_keep_their_own_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two replicates open identically, so their transcript digests collide. Each must continue
    in *its own* CLI session.

    An earlier version of this test only checked that two distinct ids were handed out, which a
    LIFO shuffle satisfies. It passed while conversations were still swapping sessions, and the
    swap only surfaced as a provider 403 seven turns into a real run. This version pins the
    property that actually matters: the session a conversation resumes is the one it opened.
    """

    class _FakeCli(_CliModelAPI):
        executable_name = "python"

        def __init__(self, model_name: str) -> None:
            super().__init__(model_name=model_name)
            self.opened = 0
            self.resumed: list[str | None] = []

        async def call(
            self, prompt: str, system: str | None, session: str | None
        ) -> tuple[str, str | None, ModelUsage]:
            self.resumed.append(session)
            if session is None:
                self.opened += 1
                return "A", f"session-{self.opened}", ModelUsage()
            return "A", None, ModelUsage()

    api = _FakeCli("fake")

    # Each conversation gets its own store, the way Inspect scopes one per sample.
    stores: dict[str, dict[str, object]] = {"a": {}, "b": {}}
    current = {"id": "a"}
    monkeypatch.setattr(cli_models, "store", lambda: _FakeStore(stores[current["id"]]))

    async def turn(conversation: str, messages: list[ChatMessage]) -> None:
        current["id"] = conversation
        await api.generate(list(messages), [], "none", GenerateConfig())

    async def run() -> None:
        opening: list[ChatMessage] = [ChatMessageUser(content="opening")]
        await turn("a", opening)  # replicate A, turn 1
        await turn("b", opening)  # replicate B, turn 1: identical text, identical digest
        history: list[ChatMessage] = [
            *opening,
            ChatMessageAssistant(content="A"),
            ChatMessageUser(content="next"),
        ]
        await turn("a", history)  # A must resume A's session
        await turn("b", history)  # B must resume B's session

    asyncio.run(run())
    assert api.opened == 2, "each replicate must open its own session"
    opened_a, opened_b = "session-1", "session-2"
    resumed = [s for s in api.resumed if s is not None]
    assert resumed == [opened_a, opened_b], f"conversations resumed the wrong sessions: {resumed}"


def test_rule_rates_exclude_answers_from_a_different_case_version(case: Case) -> None:
    rule = case.consistency_rules[0]
    stale = [
        AnswerRecord("m", case.id, "0" * 64, rule.if_cell, 0, next(iter(rule.if_answers))),
        AnswerRecord("m", case.id, "0" * 64, rule.then_cell, 0, next(iter(rule.then_answers))),
    ]
    assert rule_rates(stale, [case]) == []
    fresh = [
        AnswerRecord("m", case.id, case_hash(case), rule.if_cell, 0, next(iter(rule.if_answers)))
    ]
    assert rule_rates(fresh, [case])


def test_rank_cells_does_not_double_count_a_repeated_record(case: Case) -> None:
    cell_id = next(c.id for c in case.cells if str(c.role) == "observer")
    record = AnswerRecord(
        "m", case.id, case_hash(case), cell_id, 0, "impermissible", sample_id="s0", run_id="r"
    )
    (only,) = rank_cells([record, record], [case]).values()
    assert len(only.ranks) == 1


def test_summary_warns_when_one_cell_pools_several_runs(case: Case) -> None:
    cell_id = next(c.id for c in case.cells if str(c.role) == "observer")

    def rec(run_id: str, sample: str) -> AnswerRecord:
        return AnswerRecord(
            "m",
            case.id,
            case_hash(case),
            cell_id,
            0,
            "impermissible",
            sample_id=sample,
            run_id=run_id,
        )

    assert "separate runs" in format_summary([rec("a", "s0"), rec("b", "s1")], [case])
    assert "separate runs" not in format_summary([rec("a", "s0"), rec("a", "s1")], [case])


def test_framing_report_keeps_failure_kinds_apart_from_a_missing_letter() -> None:
    def rec(sample: str, answer: str) -> FramingRecord:
        return FramingRecord("x/m", "unjust_laws", sample, "text", "f", answer)

    report = format_framing_report(
        [
            rec("s1", "CALL_FAILURE"),
            rec("s2", "CONTENT_FILTER"),
            rec("s3", "INVALID"),
            rec("s4", "REFUSAL"),
        ]
    )
    row = next(ln for ln in report.splitlines() if "unjust_laws" in ln and ln.startswith("|"))
    assert "no letter 1" in row
    assert "CALL_FAILURE 1" in row and "CONTENT_FILTER 1" in row and "INVALID 1" in row


def test_agreement_rejects_single_class_and_uncoded_stance(tmp_path: Path) -> None:
    def sheet(rows: list[tuple[str, str, str, str]]) -> Path:
        path = tmp_path / f"sheet{len(rows)}{rows[0][1]}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "sample_id",
                    "model",
                    "case_id",
                    "cell_id",
                    "turn1_response",
                    "judge_response_class",
                    "judge_stance",
                    "human_response_class",
                    "human_stance",
                ]
            )
            for i, (jc, hc, js, hs) in enumerate(rows):
                writer.writerow([f"s{i}", "m", "C", "observer", "text", jc, js, hc, hs])
        return path

    degenerate = read_agreement(sheet([("R0", "R0", "a", "a")] * 4))
    assert degenerate.class_kappa == 1.0 and degenerate.degenerate and not degenerate.passed

    varied = read_agreement(sheet([("R0", "R0", "a", "a"), ("R3", "R3", "b", "b")] * 3))
    assert not varied.degenerate and varied.passed


def test_sign_test_ignores_category_spacing_where_signed_rank_does_not() -> None:
    order_preserving = ([0, 1, 2, 3, 4], [0, 1, 2, 3, 100])
    pairs = [(0, 2)] * 5 + [(4, 3)]
    wilcoxon = [
        wilcoxon_signed_rank([c[b] - c[a] for a, b in pairs]).p_value for c in order_preserving
    ]
    signs = [sign_test([c[b] - c[a] for a, b in pairs]).p_value for c in order_preserving]
    assert wilcoxon[0] != wilcoxon[1], "signed rank should be the spacing-sensitive one"
    assert signs[0] == signs[1], "the sign test must depend on direction only"
