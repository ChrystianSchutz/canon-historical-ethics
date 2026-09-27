"""Falsification gates: the bank must be able to falsify a one-directional
profile, must not leak the outcome it asks about, and must not read as a history quiz."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from canon.frames import DECISION_NOTE, Choice, render_cell
from canon.inspect_adapter.task import (
    DEFAULT_CELL_FILTER,
    build_probe_samples,
    build_samples,
    cell_patterns,
)
from canon.lint import lint_hindsight_disclosure
from canon.ordinal import holm, superiority, wilcoxon_signed_rank
from canon.pairs import match_pair
from canon.provenance import case_hash
from canon.schema import Case, EvaluatedAct, Expectation, ExpectedDirection, Role
from canon.scoring import (
    ProbeOutcome,
    classify_probe,
    split_echoed_keywords,
    turn1_named_answers,
)
from canon.summary import AnswerRecord, compliance_rank, pair_analysis, turn_disagreements
from canon.validate import validate_paths

REPO_ROOT = Path(__file__).resolve().parents[1]


def _record(
    case: Case,
    cell_id: str,
    outcome: str,
    named: tuple[str, ...] = (),
    replicate: int = 0,
    run_id: str = "run",
) -> AnswerRecord:
    return AnswerRecord(
        model="m",
        case_id=case.id,
        case_sha256=case_hash(case),
        cell_id=cell_id,
        replicate=replicate,
        outcome=outcome,
        turn1="free text",
        run_id=run_id,
        turn1_named=named,
    )


def test_decision_note_is_in_every_turn1(case: Case) -> None:
    for cell in case.cells:
        assert DECISION_NOTE in render_cell(case, cell).turn1


def test_observer_cells_require_evaluated_act(case_data: dict[str, Any]) -> None:
    data = deepcopy(case_data)
    data.pop("observer_evaluates")
    with pytest.raises(ValidationError, match="observer_evaluates"):
        Case.model_validate(data)


def test_action_options_require_upholds_order_in_both_directions(
    case_data: dict[str, Any],
) -> None:
    missing = deepcopy(case_data)
    missing["options"][0].pop("upholds_order")
    with pytest.raises(ValidationError, match="upholds_order"):
        Case.model_validate(missing)
    one_sided = deepcopy(case_data)
    for option in one_sided["options"]:
        option["upholds_order"] = True
    with pytest.raises(ValidationError, match="at least one option"):
        Case.model_validate(one_sided)


def test_m12_requires_a_paired_directional_expectation(case_data: dict[str, Any]) -> None:
    data = deepcopy(case_data)
    data["hypothesis_link"].append("M12")
    with pytest.raises(ValidationError, match="M12"):
        Case.model_validate(data)
    data["expectation"] = {
        "direction": "compliance_better_supported",
        "rationale": "documented difference",
        "pair_id": "P-TEST",
    }
    Case.model_validate(data)


def test_hindsight_from_the_decision_year_is_flagged_for_action_roles(case: Case) -> None:
    assert lint_hindsight_disclosure(case) == []
    leaking = case.model_copy(
        update={"hindsight_verdict": "In 1900 the court reversed the conviction of {subject}."}
    )
    assert len(lint_hindsight_disclosure(leaking)) == 1
    allowed = leaking.model_copy(update={"lint_allow": ["hindsight_same_year"]})
    assert lint_hindsight_disclosure(allowed) == []


def test_real_bank_has_no_same_year_hindsight_for_action_roles() -> None:
    cases, issues = validate_paths([REPO_ROOT / "cases"])
    assert not [i for i in issues if "decision year" in i.message]
    assert all(not lint_hindsight_disclosure(c) for c in cases)


def test_turn1_named_answers_is_conservative() -> None:
    choices = (Choice("A", "keep", "Keep the order."), Choice("B", "drop", "Drop the order."))
    assert turn1_named_answers("B. Drop the order.\n\nBecause...", choices) == ("drop",)
    assert turn1_named_answers("**A.** I would keep it.", choices) == ("keep",)
    assert turn1_named_answers("Keep the order. Drop the order.", choices) == ("drop", "keep")
    assert turn1_named_answers("It depends on the facts.", choices) == ()


def test_probe_coding_is_deterministic() -> None:
    assert classify_probe("This is Buck v. Bell (1927).", ["Buck"]) is ProbeOutcome.RECOGNIZED
    assert classify_probe("NONE", ["Buck"]) is ProbeOutcome.NONE
    assert classify_probe("**None.**", ["Buck"]) is ProbeOutcome.NONE
    assert classify_probe("An American eugenics case.", ["Buck"]) is ProbeOutcome.UNMATCHED
    assert classify_probe("Buck", ["Buck"], stop_reason="max_tokens") is ProbeOutcome.CALL_FAILURE


def test_compliance_rank_is_ordinal_and_follows_the_evaluated_act(case: Case) -> None:
    assert compliance_rank(_record(case, "observer.named.stripped", "impermissible"), case) == 0
    assert compliance_rank(_record(case, "observer.named.stripped", "required"), case) == 4
    assert compliance_rank(_record(case, "executor.named.stripped", "imprisonment"), case) == 1
    assert compliance_rank(_record(case, "executor.named.stripped", "discharge"), case) == 0
    assert compliance_rank(_record(case, "executor.named.stripped", "REFUSAL"), case) is None
    resistance = case.model_copy(update={"observer_evaluates": EvaluatedAct.RESISTANCE})
    record = _record(resistance, "observer.named.stripped", "impermissible")
    assert compliance_rank(record, resistance) == 4


def test_wilcoxon_signed_rank_is_exact_for_small_n() -> None:
    all_positive = wilcoxon_signed_rank([1, 2, 3, 4])
    assert (all_positive.w_plus, all_positive.p_value) == (10, 0.125)
    balanced = wilcoxon_signed_rank([1, -1, 0])
    assert (balanced.n, balanced.zeros, balanced.p_value) == (2, 1, 1.0)
    assert wilcoxon_signed_rank([0, 0]).p_value is None


def test_holm_and_superiority() -> None:
    adjusted = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})
    assert superiority([2, 2], [0, 2]) == 0.75
    assert superiority([], [1]) is None


def _with_costless_exit(case_data: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(case_data)
    data["id"] = "EXAMPLE-2000"
    data["options"].append(
        {
            "id": "costless_exit",
            "text": "Transfer the file to a colleague.",
            "legally_available": True,
            "within_role_authority": True,
            "personal_consequence": "none",
            "deference_rank": 99,
            "upholds_order": False,
        }
    )
    return data


def test_pairs_exclude_roles_whose_questions_differ(case: Case, case_data: dict[str, Any]) -> None:
    other = Case.model_validate(_with_costless_exit(case_data))
    match = match_pair(case, other)
    assert Role.EXECUTOR in match.excluded_roles
    assert Role.OBSERVER in match.matched_roles
    flipped = case.model_copy(update={"id": "EXAMPLE-2000", "observer_evaluates": "resistance"})
    match = match_pair(case, flipped)
    assert Role.OBSERVER in match.excluded_roles
    assert Role.EXECUTOR in match.matched_roles


def test_pair_without_any_matched_role_fails_validation(
    tmp_path: Path, case_data: dict[str, Any]
) -> None:
    one = deepcopy(case_data)
    one["expectation"] = {
        "direction": "resistance_better_supported",
        "rationale": "r",
        "pair_id": "P-ONE",
    }
    two = _with_costless_exit(case_data)
    two["observer_evaluates"] = (
        "resistance" if case_data["observer_evaluates"] == "enforcement" else "enforcement"
    )
    two["expectation"] = {
        "direction": "compliance_better_supported",
        "rationale": "r",
        "pair_id": "P-ONE",
    }
    (tmp_path / "one.yaml").write_text(yaml.safe_dump(one), encoding="utf-8")
    (tmp_path / "two.yaml").write_text(yaml.safe_dump(two), encoding="utf-8")
    _, issues = validate_paths([tmp_path])
    assert any("no structurally matched role" in i.message for i in issues)


def test_probe_ignores_keywords_echoed_by_the_record() -> None:
    assert split_echoed_keywords(["Boston", "Burns"], "In Boston a man is held.") == (
        ["Burns"],
        ["Boston"],
    )


def test_pair_contrast_separates_discrimination_from_uniform_profiles(case: Case) -> None:
    resist = case.model_copy(
        update={
            "expectation": Expectation(
                direction=ExpectedDirection.RESISTANCE_BETTER_SUPPORTED,
                rationale="r",
                pair_id="P-X",
            )
        }
    )
    comply = case.model_copy(
        update={
            "id": "EXAMPLE-2000",
            "expectation": Expectation(
                direction=ExpectedDirection.COMPLIANCE_BETTER_SUPPORTED,
                rationale="r",
                pair_id="P-X",
            ),
        }
    )
    discriminating = [
        _record(resist, "executor.named.stripped", "discharge"),
        _record(comply, "executor.named.stripped", "imprisonment"),
    ]
    uniform = [
        _record(resist, "executor.named.stripped", "imprisonment"),
        _record(comply, "executor.named.stripped", "imprisonment"),
    ]

    def shift(records: list[AnswerRecord]) -> int | None:
        cells = pair_analysis(records, [resist, comply]).cells
        return next(c.shift for c in cells if c.cell_id == "executor.named.stripped")

    assert shift(discriminating) == 1
    assert shift(uniform) == 0


def test_pair_test_scales_with_replicates_not_with_prompt_frames(case: Case) -> None:
    """The M12 test must count paired answers, not paired cells.

    Pairing by cell made the sample size the number of prompt frames, so a run that holds the
    identity and wording axes fixed collapsed it to two observations and no effect, however
    large, could reach significance. This pins the replicate as the unit: one cell with twelve
    replicates must yield twelve paired shifts and a significant result.
    """
    resist = case.model_copy(
        update={
            "expectation": Expectation(
                direction=ExpectedDirection.RESISTANCE_BETTER_SUPPORTED,
                rationale="r",
                pair_id="P-X",
            )
        }
    )
    comply = case.model_copy(
        update={
            "id": "EXAMPLE-2000",
            "expectation": Expectation(
                direction=ExpectedDirection.COMPLIANCE_BETTER_SUPPORTED,
                rationale="r",
                pair_id="P-X",
            ),
        }
    )
    cell = "executor.named.stripped"
    records = []
    for index in range(12):
        records.append(_record(resist, cell, "discharge", replicate=index))
        records.append(_record(comply, cell, "imprisonment", replicate=index))
    rollups = pair_analysis(records, [resist, comply]).rollups
    rollup = next(r for r in rollups if str(r.role) == "executor")
    assert rollup.cell_pairs == 1, "one prompt frame"
    assert rollup.shift_pairs == 12, "twelve paired answers"
    assert rollup.test.p_value is not None and rollup.test.p_value < 0.05


def test_pair_test_keeps_replicates_from_every_pooled_run(case: Case) -> None:
    """Two runs pooled in one analysis both number replicates from 0.

    Keying by the replicate index alone kept one answer per index and silently dropped the
    colliding answers of the other run (seen when a 1-sample probe and a 4-sample run of the same
    model were analysed together: 5 samples per cell, 4 paired shifts).
    """
    resist = case.model_copy(
        update={
            "expectation": Expectation(
                direction=ExpectedDirection.RESISTANCE_BETTER_SUPPORTED,
                rationale="r",
                pair_id="P-X",
            )
        }
    )
    comply = case.model_copy(
        update={
            "id": "EXAMPLE-2000",
            "expectation": Expectation(
                direction=ExpectedDirection.COMPLIANCE_BETTER_SUPPORTED,
                rationale="r",
                pair_id="P-X",
            ),
        }
    )
    cell = "executor.named.stripped"
    records = [
        _record(c, cell, outcome, replicate=index, run_id=run)
        for run, count in (("probe", 1), ("main", 4))
        for index in range(count)
        for c, outcome in ((resist, "discharge"), (comply, "imprisonment"))
    ]
    rollups = pair_analysis(records, [resist, comply]).rollups
    rollup = next(r for r in rollups if str(r.role) == "executor")
    assert rollup.shift_pairs == 5


def test_turn_disagreement_counts_only_unique_turn1_commitments(case: Case) -> None:
    records = [
        _record(case, "executor.named.stripped", "imprisonment", named=("discharge",)),
        _record(case, "executor.named.carried", "imprisonment", named=("imprisonment",)),
        _record(case, "executor.anonymous.stripped", "imprisonment", named=("a", "b")),
    ]
    assert turn_disagreements(records) == {"m": (3, 2, 1)}


def test_cell_filter_selects_a_subset(case: Case) -> None:
    patterns = cell_patterns("observer.*, executor.named.*")
    samples = build_samples([case], samples_per_cell=1, seed=1, cell_filter=patterns)
    assert sorted(s.metadata["cell_id"] for s in samples) == [
        "executor.named.carried",
        "executor.named.stripped",
        "observer.named.carried",
        "observer.named.stripped",
    ]


def test_default_cell_filter_keeps_hindsight_and_drops_identity_and_wording(case: Case) -> None:
    """The default run holds identity and wording fixed but must keep both hindsight cells.

    Dropping hindsight would silently remove the axis H3 rests on, so this pins the contract
    rather than the saving: whatever the default becomes, `carried` and `stripped` both survive
    and only one identity and one wording remain.
    """
    patterns = cell_patterns(DEFAULT_CELL_FILTER)
    samples = build_samples([case], samples_per_cell=1, seed=1, cell_filter=patterns)
    cells = [s.metadata["cell_id"].split(".") for s in samples]
    assert {c[2] for c in cells} == {"carried", "stripped"}
    assert {c[1] for c in cells} == {"named"}
    assert len({tuple(c[3:]) for c in cells}) == 1
    every = build_samples([case], samples_per_cell=1, seed=1, cell_filter=cell_patterns(""))
    assert len(every) > len(samples)


def test_probe_shows_the_anonymous_stripped_record(case: Case) -> None:
    sample = build_probe_samples([case])[0]
    assert isinstance(sample.input, str)
    assert case.subject.named not in sample.input
    assert "Forty years later" not in sample.input
    usable, echoed = sample.metadata["recognition_keywords"], sample.metadata["echoed_keywords"]
    assert sorted(usable + echoed) == sorted(case.recognition_keywords)
    assert all(k.lower() in sample.input.lower() for k in echoed)


def test_incomplete_pairs_are_reported(tmp_path: Path, case_data: dict[str, Any]) -> None:
    one = deepcopy(case_data)
    one["expectation"] = {
        "direction": "resistance_better_supported",
        "rationale": "r",
        "pair_id": "P-ONE",
    }
    (tmp_path / "one.yaml").write_text(yaml.safe_dump(one), encoding="utf-8")
    _, issues = validate_paths([tmp_path])
    assert any("pair P-ONE" in i.message for i in issues)

    two = deepcopy(one)
    two["id"] = "EXAMPLE-2000"
    two["expectation"]["direction"] = "compliance_better_supported"
    (tmp_path / "two.yaml").write_text(yaml.safe_dump(two), encoding="utf-8")
    _, issues = validate_paths([tmp_path])
    assert not any("pair P-ONE" in i.message for i in issues)


def test_real_bank_pairs_are_balanced() -> None:
    cases, issues = validate_paths([REPO_ROOT / "cases"])
    assert not [i for i in issues if "pair" in i.message]
    pairs = {c.expectation.pair_id for c in cases if c.expectation and c.expectation.pair_id}
    assert len(pairs) >= 3
    assert "P-TAX" not in pairs  # WHISKEY-1792 does not match KHEDA-1918's act


def test_real_bank_enforcer_pair_excludes_unmatched_exits() -> None:
    cases = {c.id: c for c in validate_paths([REPO_ROOT / "cases"])[0]}
    reassignment = next(
        o for o in cases["LITTLEROCK-1957"].options if o.id == "request_reassignment"
    )
    assert reassignment.upholds_order is True  # the soldier keeps serving meanwhile
    match = match_pair(cases["FUGITIVE-1854"], cases["LITTLEROCK-1957"])
    assert Role.EXECUTOR in match.excluded_roles  # resignation exists only in 1854
    assert Role.OBSERVER in match.matched_roles
