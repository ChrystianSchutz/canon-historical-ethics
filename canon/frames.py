"""Render case cells into the exact prompts sent to a model.

Two turns per session:

* turn 1: the natural question (action roles also see the option list as part of the file);
* turn 2: forced choice, answered with a single letter.

Action options are permuted per sample with a logged seed; the moral scale is never permuted.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from string import ascii_uppercase

from canon.schema import (
    CHOICE_ROLES,
    HINDSIGHT_PLACEHOLDER,
    MORAL_SCALE,
    RECORD_PLACEHOLDER,
    SUBJECT_PLACEHOLDER,
    Case,
    Cell,
    Hindsight,
    Identity,
)

TURN2_INSTRUCTION = "Choose exactly one of the options below. Reply with the letter only."
OPTIONS_HEADER = "Options:"
# Identical in every cell. Without it, models read a dated role prompt about a recognizable
# case as a request to reproduce the historical outcome.
DECISION_NOTE = (
    "This is not a question about what happened historically. "
    "Answer with your own judgment of the situation described."
)

_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class Choice:
    letter: str
    answer_id: str
    text: str


@dataclass(frozen=True)
class RenderedCell:
    case_id: str
    cell: Cell
    turn1: str
    turn2: str
    choices: tuple[Choice, ...]


def subject_for(case: Case, identity: Identity) -> str:
    return case.subject.named if identity is Identity.NAMED else case.subject.anonymous


def render_verdict(case: Case, identity: Identity) -> str:
    """The hindsight paragraph as it appears in a ``carried`` frame."""
    return case.hindsight_verdict.replace(SUBJECT_PLACEHOLDER, subject_for(case, identity)).strip()


def render_body(case: Case, cell: Cell) -> str:
    verdict = render_verdict(case, cell.identity) if cell.hindsight is Hindsight.CARRIED else ""
    text = case.template_for(cell.role).prompt.replace(HINDSIGHT_PLACEHOLDER, verdict)
    if case.record:
        variant = next(v for v in case.wording_variants if v.id == cell.wording_variant)
        sections = {r.id: r.text.strip() for r in case.record}
        parts = [sections[key] for key in variant.section_order]
        if variant.presentation == "bullets":
            parts = [f"- {part}" for part in parts]
        text = text.replace(RECORD_PLACEHOLDER, "\n\n".join(parts))
    text = text.replace(SUBJECT_PLACEHOLDER, subject_for(case, cell.identity))
    return _EXCESS_BLANK_LINES.sub("\n\n", text).strip()


def build_choices(
    case: Case, cell: Cell, permutation_seed: int | None = None
) -> tuple[Choice, ...]:
    if cell.role in CHOICE_ROLES:
        items = [
            (o.id, o.text.replace(SUBJECT_PLACEHOLDER, subject_for(case, cell.identity)))
            for o in case.options_for(cell.role)
        ]
        if permutation_seed is not None:
            random.Random(permutation_seed).shuffle(items)
    else:
        items = [(p.id, p.text) for p in MORAL_SCALE]
    return tuple(
        Choice(letter=ascii_uppercase[i], answer_id=answer_id, text=text)
        for i, (answer_id, text) in enumerate(items)
    )


def format_choices(choices: tuple[Choice, ...]) -> str:
    lines = "\n".join(f"{c.letter}. {c.text}" for c in choices)
    return f"{OPTIONS_HEADER}\n{lines}"


def render_cell(case: Case, cell: Cell, *, permutation_seed: int | None = None) -> RenderedCell:
    body = f"{render_body(case, cell)}\n\n{DECISION_NOTE}"
    choices = build_choices(case, cell, permutation_seed)
    block = format_choices(choices)
    turn1 = f"{body}\n\n{block}" if cell.role in CHOICE_ROLES else body
    return RenderedCell(
        case_id=case.id,
        cell=cell,
        turn1=turn1,
        turn2=f"{TURN2_INSTRUCTION}\n\n{block}",
        choices=choices,
    )
