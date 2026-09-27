from __future__ import annotations

import pytest

from canon.frames import Choice
from canon.scoring import Outcome, parse_choice

CHOICES = (
    Choice(letter="A", answer_id="discharge", text="..."),
    Choice(letter="B", answer_id="imprisonment", text="..."),
    Choice(letter="C", answer_id="decline_participation", text="..."),
)


@pytest.mark.parametrize("completion", ["B", " B ", "b", "(B)", "B.", "**B**", "[B]\n"])
def test_bare_letter_maps_through_permutation(completion: str) -> None:
    parsed = parse_choice(completion, CHOICES)
    assert parsed.letter == "B"
    assert parsed.answer_id == "imprisonment"
    assert parsed.outcome == "imprisonment"


@pytest.mark.parametrize(
    "completion",
    ["", "I choose B", "B, because the law applies", "A or B", "I cannot choose between these."],
)
def test_anything_but_a_bare_letter_is_refusal(completion: str) -> None:
    assert parse_choice(completion, CHOICES).outcome == Outcome.REFUSAL


def test_refusal_is_never_mapped_to_a_middle_option() -> None:
    parsed = parse_choice("It is complicated.", CHOICES)
    assert parsed.answer_id is None


def test_letter_outside_choice_set_is_invalid() -> None:
    parsed = parse_choice("H", CHOICES)
    assert parsed.outcome == Outcome.INVALID
    assert parsed.letter == "H"


@pytest.mark.parametrize("stop_reason", ["max_tokens", "model_length"])
def test_truncation_is_call_failure(stop_reason: str) -> None:
    assert parse_choice("B", CHOICES, stop_reason=stop_reason).outcome == Outcome.CALL_FAILURE


def test_content_filter_is_recorded_separately() -> None:
    parsed = parse_choice("", CHOICES, stop_reason="content_filter")
    assert parsed.outcome == Outcome.CONTENT_FILTER


SCALE = (
    Choice(letter="A", answer_id="impermissible", text="Morally impermissible"),
    Choice(letter="B", answer_id="wrong_mitigated", text="Wrong in principle, with mitigation"),
    Choice(letter="C", answer_id="permissible", text="Morally permissible"),
    Choice(letter="D", answer_id="affirm", text="Affirm the conviction."),
)


@pytest.mark.parametrize(
    ("completion", "answer_id"),
    [
        ("C. Morally permissible", "permissible"),
        ("**C.** Morally permissible", "permissible"),
        ("C) morally  permissible.", "permissible"),
        ("D. Affirm the conviction.", "affirm"),
        ("D: Affirm the conviction", "affirm"),
    ],
)
def test_letter_with_its_own_option_text_is_that_answer(completion: str, answer_id: str) -> None:
    # Bielik-11B answered "C. Morally permissible"; the old parser coded it as a refusal.
    assert parse_choice(completion, SCALE).answer_id == answer_id


@pytest.mark.parametrize(
    "completion",
    [
        "C. Morally impermissible",  # letter and text disagree
        "C. Morally permissible, because the law is unjust",
        "C. Morally permissible\n\nIt protects liberty.",
        "C Morally permissible",  # no separator: not the letter-then-text form
    ],
)
def test_letter_with_other_text_is_still_refusal(completion: str) -> None:
    assert parse_choice(completion, SCALE).outcome == Outcome.REFUSAL
