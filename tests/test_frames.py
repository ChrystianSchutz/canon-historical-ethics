from __future__ import annotations

from canon.frames import render_cell, render_verdict
from canon.schema import Case, Cell, Hindsight, Identity, Role


def _cell(role: Role, identity: Identity, hindsight: Hindsight) -> Cell:
    return Cell(role=role, identity=identity, hindsight=hindsight)


def test_stripped_and_carried_differ_only_by_verdict_paragraph(case: Case) -> None:
    for role in (Role.OBSERVER, Role.EXECUTOR):
        carried = render_cell(
            case, _cell(role, Identity.NAMED, Hindsight.CARRIED), permutation_seed=7
        )
        stripped = render_cell(
            case, _cell(role, Identity.NAMED, Hindsight.STRIPPED), permutation_seed=7
        )
        verdict = render_verdict(case, Identity.NAMED)

        assert verdict in carried.turn1
        assert verdict not in stripped.turn1
        assert carried.turn1.replace(verdict + "\n\n", "", 1) == stripped.turn1
        assert carried.turn2 == stripped.turn2


def test_named_and_anonymous_differ_only_by_subject(case: Case) -> None:
    for hindsight in Hindsight:
        named = render_cell(
            case, _cell(Role.EXECUTOR, Identity.NAMED, hindsight), permutation_seed=3
        )
        anonymous = render_cell(
            case, _cell(Role.EXECUTOR, Identity.ANONYMOUS, hindsight), permutation_seed=3
        )
        assert case.subject.named not in anonymous.turn1
        assert named.turn1.replace(case.subject.named, case.subject.anonymous) == anonymous.turn1


def test_scales_identical_across_frames(case: Case) -> None:
    evaluative = {
        render_cell(case, cell).turn2 for cell in case.cells if cell.role is Role.OBSERVER
    }
    assert len(evaluative) == 1


def test_option_permutation_is_deterministic_and_complete(case: Case) -> None:
    cell = _cell(Role.EXECUTOR, Identity.NAMED, Hindsight.STRIPPED)
    option_ids = {o.id for o in case.options}

    first = render_cell(case, cell, permutation_seed=11).choices
    assert first == render_cell(case, cell, permutation_seed=11).choices

    orders = set()
    for seed in range(20):
        choices = render_cell(case, cell, permutation_seed=seed).choices
        assert {c.answer_id for c in choices} == option_ids
        assert [c.letter for c in choices] == ["A", "B", "C", "D"]
        orders.add(tuple(c.answer_id for c in choices))
    assert len(orders) > 1


def test_observer_turn1_has_no_forced_format(case: Case) -> None:
    rendered = render_cell(case, _cell(Role.OBSERVER, Identity.NAMED, Hindsight.STRIPPED))
    assert "Options:" not in rendered.turn1
    assert "letter" not in rendered.turn1
