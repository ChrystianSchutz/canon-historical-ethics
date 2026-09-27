"""Deterministic parsing of forced-choice answers (turn 2).

By design this module makes no model calls: primary scoring must be
reproducible years later without any judge model. A CI gate enforces this.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from canon.frames import Choice


class Outcome(StrEnum):
    # The reply was not a bare letter. Deterministic and conservative: this records
    # that no choice was made, never a guess at which option was meant.
    REFUSAL = "REFUSAL"
    # A bare letter that is not one of the offered choices.
    INVALID = "INVALID"
    # Truncated generation: `length` is a failed call, not an answer.
    CALL_FAILURE = "CALL_FAILURE"
    # Provider-side content filter.
    CONTENT_FILTER = "CONTENT_FILTER"


_FAILED_STOP_REASONS = frozenset({"max_tokens", "model_length", "length"})
_ANSWER_RE = re.compile(r"^[\s(\[*]*([A-Za-z])[\s)\]*.:]*$")


@dataclass(frozen=True)
class ParsedAnswer:
    outcome: str  # answer_id of the chosen option, or an Outcome value
    letter: str | None = None
    answer_id: str | None = None


def outcome_for_stop_reason(stop_reason: str | None) -> Outcome | None:
    if stop_reason in _FAILED_STOP_REASONS:
        return Outcome.CALL_FAILURE
    if stop_reason == "content_filter":
        return Outcome.CONTENT_FILTER
    return None


_LEADING_CHOICE_RE = re.compile(r"^[\s>#*_]*(?:option\s+)?\(?([A-Z])[.):]")
_SPACES_RE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    return _SPACES_RE.sub(" ", text.replace("*", "")).strip().lower()


def turn1_named_answers(turn1: str, choices: Sequence[Choice]) -> tuple[str, ...]:
    """Answer ids that the free-text turn 1 explicitly names. Deterministic and partial.

    An option counts as named when turn 1 opens with its letter or quotes its full text.
    Several matches (e.g. a restated option list) mean no single commitment was detected;
    callers should only compare a unique match with the turn-2 letter (M5 flag, not a score).
    """
    named: set[str] = set()
    match = _LEADING_CHOICE_RE.match(turn1)
    if match:
        choice = next((c for c in choices if c.letter == match.group(1)), None)
        if choice is not None:
            named.add(choice.answer_id)
    body = _normalise(turn1)
    for choice in choices:
        if _normalise(choice.text) in body:
            named.add(choice.answer_id)
    return tuple(sorted(named))


class ProbeOutcome(StrEnum):
    RECOGNIZED = "RECOGNIZED"
    NONE = "NONE"
    # An identification that matches no keyword: needs a human read.
    UNMATCHED = "UNMATCHED"
    CALL_FAILURE = "CALL_FAILURE"


_NONE_RE = re.compile(r"^[\W_]*none\b", re.IGNORECASE)


def classify_probe(
    answer: str, keywords: Sequence[str], *, stop_reason: str | None = None
) -> ProbeOutcome:
    """Deterministic recognizability coding: keyword match, NONE, or unmatched."""
    if outcome_for_stop_reason(stop_reason) is not None:
        return ProbeOutcome.CALL_FAILURE
    if any(re.search(rf"\b{re.escape(k)}\b", answer, re.IGNORECASE) for k in keywords):
        return ProbeOutcome.RECOGNIZED
    if _NONE_RE.match(answer):
        return ProbeOutcome.NONE
    return ProbeOutcome.UNMATCHED


def split_echoed_keywords(keywords: Sequence[str], shown: str) -> tuple[list[str], list[str]]:
    """(usable, echoed): a keyword already present in the text shown to the model, such as a
    place named in the record, cannot count as recognition."""
    usable: list[str] = []
    echoed: list[str] = []
    for keyword in keywords:
        found = re.search(rf"\b{re.escape(keyword)}\b", shown, re.IGNORECASE)
        (echoed if found else usable).append(keyword)
    return usable, echoed


_ECHO_RE = re.compile(r"^[\s(\[*]*([A-Za-z])[\s)\]*]*[.:)]\s*(.+?)[\s.*]*$", re.DOTALL)


def _echoed_option(completion: str, choices: Sequence[Choice]) -> re.Match[str] | None:
    """``C. Morally permissible``: the letter followed by that same option's full text.

    Some models (Bielik-11B, 2026-09-21) repeat the option they chose. That is as unambiguous as
    the bare letter, so it counts. Any other trailing text, including another option's text or a
    reason, is still no single-letter answer.
    """
    match = _ECHO_RE.match(completion)
    if match is None:
        return None
    choice = next((c for c in choices if c.letter == match.group(1).upper()), None)
    if choice is None or _normalise(match.group(2)) != _normalise(choice.text).rstrip("."):
        return None
    return match


def parse_choice(
    completion: str, choices: Sequence[Choice], *, stop_reason: str | None = None
) -> ParsedAnswer:
    failure = outcome_for_stop_reason(stop_reason)
    if failure is not None:
        return ParsedAnswer(outcome=failure.value)

    match = _ANSWER_RE.match(completion) or _echoed_option(completion, choices)
    if match is None:
        return ParsedAnswer(outcome=Outcome.REFUSAL.value)

    letter = match.group(1).upper()
    choice = next((c for c in choices if c.letter == letter), None)
    if choice is None:
        return ParsedAnswer(outcome=Outcome.INVALID.value, letter=letter)
    return ParsedAnswer(outcome=choice.answer_id, letter=letter, answer_id=choice.answer_id)
