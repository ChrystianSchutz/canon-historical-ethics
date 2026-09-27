"""Inspect scorers wrapping the deterministic parsers. No judge model."""

from __future__ import annotations

from inspect_ai.scorer import Score, Scorer, Target, frequency, scorer
from inspect_ai.solver import TaskState

from canon.frames import Choice
from canon.schema import CHOICE_ROLES
from canon.scoring import (
    Outcome,
    classify_probe,
    outcome_for_stop_reason,
    parse_choice,
    turn1_named_answers,
)


@scorer(metrics=[frequency()])
def choice_scorer() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        choices = [Choice(**c) for c in state.metadata["choices"]]
        completion = state.output.completion

        # A truncated turn 1 invalidates the whole session, whatever turn 2 says.
        turn1_failure = outcome_for_stop_reason(state.metadata.get("turn1_stop_reason"))
        if turn1_failure is Outcome.CALL_FAILURE:
            outcome, letter, answer_id = turn1_failure.value, None, None
        else:
            parsed = parse_choice(completion, choices, stop_reason=state.output.stop_reason)
            outcome, letter, answer_id = parsed.outcome, parsed.letter, parsed.answer_id

        turn1_named: list[str] = []
        if state.metadata.get("role") in {str(r) for r in CHOICE_ROLES}:
            turn1_named = list(
                turn1_named_answers(state.metadata.get("turn1_completion") or "", choices)
            )

        return Score(
            value=outcome,
            answer=completion,
            metadata={"letter": letter, "answer_id": answer_id, "turn1_named": turn1_named},
        )

    return score


@scorer(metrics=[frequency()])
def probe_scorer() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        answer = state.output.completion
        outcome = classify_probe(
            answer,
            state.metadata.get("recognition_keywords") or [],
            stop_reason=state.output.stop_reason,
        )
        return Score(value=outcome.value, answer=answer)

    return score
