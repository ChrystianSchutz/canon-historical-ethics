from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from canon.schema import Case


def test_fixture_is_valid(case: Case) -> None:
    assert case.id == "EXAMPLE-1900"
    assert not case.is_verified


def test_every_item_has_hypothesis_link(case_data: dict[str, Any]) -> None:
    case_data["hypothesis_link"] = []
    with pytest.raises(ValidationError, match="hypothesis_link"):
        Case.model_validate(case_data)


def test_option_sets_have_legal_availability_flags(case_data: dict[str, Any]) -> None:
    del case_data["options"][0]["legally_available"]
    with pytest.raises(ValidationError, match="legally_available"):
        Case.model_validate(case_data)


def test_option_needs_role_authority_and_consequence(case_data: dict[str, Any]) -> None:
    del case_data["options"][0]["within_role_authority"]
    del case_data["options"][1]["personal_consequence"]
    with pytest.raises(ValidationError) as exc:
        Case.model_validate(case_data)
    assert "within_role_authority" in str(exc.value)
    assert "personal_consequence" in str(exc.value)


def test_template_requires_single_hindsight_placeholder(case_data: dict[str, Any]) -> None:
    case_data["templates"][0]["prompt"] = "No placeholder here about {subject}."
    with pytest.raises(ValidationError, match="exactly once"):
        Case.model_validate(case_data)


def test_hindsight_placeholder_must_be_its_own_paragraph(case_data: dict[str, Any]) -> None:
    case_data["templates"][0]["prompt"] = "Inline {hindsight} verdict about {subject}."
    with pytest.raises(ValidationError, match="own line"):
        Case.model_validate(case_data)


def test_template_must_not_hardcode_named_subject(case_data: dict[str, Any]) -> None:
    case_data["templates"][0]["prompt"] += "\n\nVarnholt appealed."
    with pytest.raises(ValidationError, match="named subject"):
        Case.model_validate(case_data)


def test_unknown_placeholder_rejected(case_data: dict[str, Any]) -> None:
    case_data["templates"][0]["prompt"] += "\n\n{year}"
    with pytest.raises(ValidationError, match="unknown placeholders"):
        Case.model_validate(case_data)


def test_action_cell_requires_options(case_data: dict[str, Any]) -> None:
    case_data["options"] = []
    case_data["consistency_rules"] = []
    with pytest.raises(ValidationError, match="at least 2 options"):
        Case.model_validate(case_data)


def test_deference_ranks_are_unique(case_data: dict[str, Any]) -> None:
    case_data["options"][1]["deference_rank"] = 1
    with pytest.raises(ValidationError, match="deference_rank"):
        Case.model_validate(case_data)


def test_consistency_rule_references_existing_cell(case_data: dict[str, Any]) -> None:
    case_data["consistency_rules"][0]["then_cell"] = "executor.named.nonexistent"
    with pytest.raises(ValidationError, match="unknown cell"):
        Case.model_validate(case_data)


def test_consistency_rule_answers_match_cell_response_set(case_data: dict[str, Any]) -> None:
    # A scale answer used where the cell answers with options.
    case_data["consistency_rules"][0]["then_answers"] = ["impermissible"]
    with pytest.raises(ValidationError, match="not valid"):
        Case.model_validate(case_data)


def test_extra_fields_rejected(case_data: dict[str, Any]) -> None:
    case_data["ethics_score"] = 0.9
    with pytest.raises(ValidationError, match="ethics_score"):
        Case.model_validate(case_data)
