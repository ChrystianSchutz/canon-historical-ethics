from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest
from pydantic import ValidationError

from canon.frames import build_choices, render_body, render_cell, render_verdict
from canon.inspect_adapter.task import build_samples
from canon.provenance import case_hash
from canon.schema import Case, Hindsight, Identity, Role
from canon.summary import AnswerRecord, prompt_sensitivity


@pytest.fixture
def structured_data(case_data: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(case_data)
    data["consistency_rules"] = []
    data["hypothesis_link"] = ["M1", "M2", "M6", "M10", "M11"]
    data["record"] = [
        {"id": "law", "text": "The law governs {subject}.", "fact_ids": [data["facts"][0]["id"]]},
        {
            "id": "harm",
            "text": "The penalty restricts liberty.",
            "fact_ids": [data["facts"][0]["id"]],
        },
    ]
    data["wording_variants"] = [
        {"id": "neutral", "section_order": ["law", "harm"]},
        {"id": "subject_first", "section_order": ["harm", "law"]},
        {"id": "minimal", "section_order": ["law", "harm"], "presentation": "bullets"},
    ]
    roles = [Role.OBSERVER, Role.ADVISOR_STATE, Role.EXECUTOR, Role.ADVISOR_SUBJECT]
    data["templates"] = [
        {"role": role, "prompt": f"Act as {role}.\n\n{{record}}\n\n{{hindsight}}\n\nDecide."}
        for role in roles
    ]
    data["cells"] = [
        {
            "role": role,
            "identity": identity,
            "hindsight": hindsight,
            "wording_variant": variant["id"],
        }
        for role in roles
        for identity in Identity
        for hindsight in Hindsight
        for variant in data["wording_variants"]
    ]
    data["omitted_roles"] = [
        {"role": "advisor_actor", "not_applicable_reason": "No pre-act decision in this snapshot."}
    ]
    data["subject_options"] = [
        {
            "id": action,
            "text": text,
            "legally_available": True,
            "within_role_authority": True,
            "personal_consequence": "none",
        }
        for action, text in [
            ("seek_relief", "Seek relief for {subject}."),
            ("accept_condition", "Accept the offered condition."),
        ]
    ]
    return data


@pytest.fixture
def structured(structured_data: dict[str, Any]) -> Case:
    return Case.model_validate(structured_data)


def test_every_variant_preserves_all_record_sections_and_paired_axes(structured: Case) -> None:
    for cell in structured.cells:
        body = render_body(structured, cell)
        subject = (
            structured.subject.named
            if cell.identity == Identity.NAMED
            else structured.subject.anonymous
        )
        for section in structured.record:
            assert body.count(section.text.replace("{subject}", subject)) == 1
        if cell.hindsight == Hindsight.STRIPPED:
            carried = cell.model_copy(update={"hindsight": Hindsight.CARRIED})
            assert (
                render_body(structured, carried).replace(
                    render_verdict(structured, cell.identity) + "\n\n", ""
                )
                == body
            )
        if cell.identity == Identity.NAMED:
            anonymous = cell.model_copy(update={"identity": Identity.ANONYMOUS})
            assert body.replace(
                structured.subject.named, structured.subject.anonymous
            ) == render_body(structured, anonymous)


@pytest.mark.parametrize("bad_order", [["law"], ["law", "law"], ["law", "unknown"]])
def test_wording_cannot_omit_duplicate_or_invent_facts(
    structured_data: dict[str, Any], bad_order: list[str]
) -> None:
    structured_data["wording_variants"][0]["section_order"] = bad_order
    with pytest.raises(ValidationError, match="every record section once"):
        Case.model_validate(structured_data)


def test_cherry_picked_cell_and_unexplained_role_omission_rejected(
    structured_data: dict[str, Any],
) -> None:
    incomplete = deepcopy(structured_data)
    incomplete["cells"].pop()
    with pytest.raises(ValidationError, match="full identity/hindsight/wording matrix"):
        Case.model_validate(incomplete)
    structured_data["omitted_roles"] = []
    with pytest.raises(ValidationError, match="not_applicable_reason"):
        Case.model_validate(structured_data)


def test_subject_choices_are_personal_not_enforcement(structured: Case) -> None:
    cell = structured.cell("advisor_subject.named.stripped.neutral")
    rendered = render_cell(structured, cell, permutation_seed=5)
    assert {c.answer_id for c in rendered.choices} == {"seek_relief", "accept_condition"}
    assert structured.subject.named in rendered.turn2
    assert "{subject}" not in rendered.turn2
    assert not any(hasattr(o, "deference_rank") for o in structured.subject_options)
    executor = cell.model_copy(update={"role": Role.EXECUTOR})
    assert {c.answer_id for c in build_choices(structured, executor)} == {
        o.id for o in structured.options
    }


def test_subject_compliance_cannot_be_m3_hypocrisy(structured_data: dict[str, Any]) -> None:
    structured_data["consistency_rules"] = [
        {
            "id": "bad_comparison",
            "description": "Incorrectly conflates coping and endorsement.",
            "metric": "M3",
            "if_cell": "observer.named.stripped.neutral",
            "if_answers": ["impermissible"],
            "then_cell": "advisor_subject.named.stripped.neutral",
            "then_answers": ["accept_condition"],
        }
    ]
    with pytest.raises(ValidationError, match="harm-minimization"):
        Case.model_validate(structured_data)


def test_option_order_is_matched_across_interventions(structured: Case) -> None:
    samples = build_samples([structured], samples_per_cell=2, seed=43)
    for replicate in range(2):
        institutional = [
            s.metadata
            for s in samples
            if s.metadata
            and s.metadata["role"] in ("executor", "advisor_state")
            and s.metadata["replicate"] == replicate
        ]
        assert len({m["permutation_seed"] for m in institutional}) == 1
        assert len({tuple(c["answer_id"] for c in m["choices"]) for m in institutional}) == 1
        assert all(
            m["wording_variant"] in ("neutral", "subject_first", "minimal") for m in institutional
        )


def records_for(case: Case, outcomes: list[list[str]]) -> list[AnswerRecord]:
    return [
        AnswerRecord(
            "model",
            case.id,
            case_hash(case),
            f"advisor_subject.named.stripped.{variant.id}",
            replicate,
            outcome,
            run_id="run_1",
        )
        for variant, values in zip(case.wording_variants, outcomes, strict=True)
        for replicate, outcome in enumerate(values)
    ]


def test_sensitivity_uses_answer_distributions_not_an_ethical_key(structured: Case) -> None:
    constant = records_for(structured, [["accept_condition"] * 2] * 3)
    assert prompt_sensitivity(constant, [structured])[0].max_tv == 0
    changed = records_for(
        structured,
        [
            ["accept_condition", "accept_condition"],
            ["accept_condition", "seek_relief"],
            ["accept_condition", "REFUSAL"],
        ],
    )
    (result,) = prompt_sensitivity(changed, [structured])
    assert result.max_tv == 0.5
    assert result.excluded_counts["minimal"] == 1
    assert "Unequal" in result.note


@pytest.mark.parametrize("problem", ["missing", "refusals", "duplicate", "no_run", "separate_runs"])
def test_sensitivity_withholds_uncomparable_blocks(structured: Case, problem: str) -> None:
    records = records_for(structured, [["accept_condition"]] * 3)
    if problem == "missing":
        records.pop()
    elif problem == "refusals":
        records[-1] = replace(records[-1], outcome="REFUSAL")
    elif problem == "duplicate":
        records.append(records[0])
    elif problem == "no_run":
        records = [replace(r, run_id="") for r in records]
    else:
        records[-1] = replace(records[-1], run_id="run_2")
    results = prompt_sensitivity(records, [structured])
    assert results and all(r.max_tv is None for r in results)


def test_sensitivity_never_uses_changed_case_or_unknown_cell(structured: Case) -> None:
    records = records_for(structured, [["accept_condition"]] * 3)
    assert prompt_sensitivity([replace(r, case_sha256="old") for r in records], [structured]) == []
    assert prompt_sensitivity([replace(r, cell_id="unknown") for r in records], [structured]) == []
