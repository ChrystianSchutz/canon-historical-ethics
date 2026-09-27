"""Secondary LLM judge: prompt, parser, human-agreement tooling. No model calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from canon.agreement import (
    cohen_kappa,
    read_agreement,
    select_for_validation,
    write_validation_sheet,
)
from canon.frames import Choice
from canon.judge import JUDGE_INVALID, build_judge_prompt, parse_judge_output
from canon.summary import AnswerRecord, format_summary

CHOICES = (
    Choice(letter="A", answer_id="discharge", text="Recommend an absolute discharge."),
    Choice(letter="B", answer_id="imprisonment", text="Recommend imprisonment."),
)


def test_prompt_contains_all_parts_and_no_leftover_markers() -> None:
    prompt = build_judge_prompt("Was it right?", "It was wrong.", CHOICES)
    assert "Was it right?" in prompt and "It was wrong." in prompt
    assert "A. Recommend an absolute discharge." in prompt
    assert "R5:" in prompt
    assert "<<" not in prompt


def test_parse_valid_output_in_code_fence() -> None:
    raw = '```json\n{"response_class": "r1", "stance": "b", "evidence": "prison"}\n```'
    verdict = parse_judge_output(raw, CHOICES)
    assert verdict.valid
    assert verdict.label == "R1"
    assert verdict.stance_answer_id == "imprisonment"
    assert verdict.evidence == "prison"


def test_parse_no_stance() -> None:
    verdict = parse_judge_output('{"response_class": "R2", "stance": "NONE"}', CHOICES)
    assert verdict.valid and verdict.stance_answer_id is None


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"response_class": "R9", "stance": "A"}',
        '{"response_class": "R0", "stance": "Z"}',
        '["R0"]',
    ],
)
def test_invalid_judge_output(raw: str) -> None:
    assert parse_judge_output(raw, CHOICES).label == JUDGE_INVALID


def test_cohen_kappa() -> None:
    assert cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0
    # observed 0.5, expected 0.5 -> 0
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        cohen_kappa(["a"], [])


def _judged(i: int, response_class: str, stance: str | None, outcome: str) -> AnswerRecord:
    return AnswerRecord(
        model="m",
        case_id="EXAMPLE-1900",
        case_sha256="x",
        cell_id="executor.named.stripped",
        replicate=i,
        outcome=outcome,
        sample_id=f"s{i}",
        turn1="free text",
        response_class=response_class,
        stance=stance,
    )


def test_validation_sheet_roundtrip(tmp_path: Path) -> None:
    records = [_judged(i, "R0", "discharge", "discharge") for i in range(10)]
    selected = select_for_validation(records, fraction=0.3, seed=1)
    assert len(selected) == 3

    sheet = tmp_path / "sheet.csv"
    write_validation_sheet(selected, sheet)
    text = sheet.read_text(encoding="utf-8")
    lines = text.splitlines()
    filled = [lines[0]] + [line.replace(",,", ",R0,discharge") for line in lines[1:]]
    sheet.write_text("\n".join(filled) + "\n", encoding="utf-8")

    report = read_agreement(sheet)
    # Every row coded R0/discharge: kappa is 1.0 by construction and carries no information,
    # so this must NOT pass the validation gate.
    assert report.n == 3 and report.class_kappa == 1.0
    assert report.degenerate and not report.passed


def test_summary_reports_judge_section() -> None:
    records = [
        _judged(0, "R0", "discharge", "discharge"),
        _judged(1, "R2", None, "imprisonment"),
    ]
    summary = format_summary(records, [])
    assert "LLM judge (secondary)" in summary
    assert "| 1/1 | 1 |" in summary
