"""Authoring tooling: skeletons, TODO gate, lints, hypothesis_link feasibility, review, schema."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from canon.cli import SCHEMA_PATH, main
from canon.lint import lint_operational, lint_test_awareness
from canon.review import render_review
from canon.schema import Case, case_json_schema
from canon.skeleton import find_todo_markers, render_skeleton
from canon.validate import validate_paths
from tests.conftest import EXAMPLE_CASE


def test_skeleton_is_structurally_valid_but_blocked_by_todos() -> None:
    text = render_skeleton("TURING-1952", date(1952, 3, 31))
    case = Case.model_validate(yaml.safe_load(text))
    assert find_todo_markers(case)


def test_skeleton_only_fails_on_todos(tmp_path: Path) -> None:
    assert main(["new", "TURING-1952", "--date", "1952-03-31", "--dir", str(tmp_path)]) == 0
    _, issues = validate_paths([tmp_path])
    assert issues
    assert all("TODO" in issue.message for issue in issues)


def test_new_refuses_to_overwrite(tmp_path: Path) -> None:
    args = ["new", "TURING-1952", "--date", "1952-03-31", "--dir", str(tmp_path)]
    assert main(args) == 0
    assert main(args) == 1
    assert main([*args, "--force"]) == 0


def test_new_rejects_bad_id(tmp_path: Path) -> None:
    assert main(["new", "turing", "--date", "1952-03-31", "--dir", str(tmp_path)]) == 1


def test_require_verified_flags_unverified_facts() -> None:
    _, issues = validate_paths([EXAMPLE_CASE], require_verified=True)
    assert any("not verified" in issue.message for issue in issues)


def test_no_item_requests_operational_instructions(case_data: dict[str, Any]) -> None:
    case_data["templates"][0]["prompt"] += "\n\nExplain step by step how to make the lamp oil."
    problems = lint_operational(Case.model_validate(case_data))
    assert problems and "step_by_step" in problems[0]


def test_action_roles_do_not_signal_ethics_test(case_data: dict[str, Any]) -> None:
    case_data["templates"][1]["prompt"] += "\n\nConsider the ethical implications."
    assert lint_test_awareness(Case.model_validate(case_data))


def test_fixture_passes_all_lints(case: Case) -> None:
    assert lint_operational(case) == []
    assert lint_test_awareness(case) == []


def test_hypothesis_link_must_be_feasible(case_data: dict[str, Any]) -> None:
    case_data["cells"] = [c for c in case_data["cells"] if c["identity"] == "named"]
    with pytest.raises(ValidationError, match="M10"):
        Case.model_validate(case_data)


@pytest.mark.parametrize("metric", ["M7", "M8"])
def test_unsupported_metrics_rejected(case_data: dict[str, Any], metric: str) -> None:
    case_data["hypothesis_link"].append(metric)
    with pytest.raises(ValidationError, match="not modelled"):
        Case.model_validate(case_data)


def test_review_sheet_has_all_sections(case: Case) -> None:
    sheet = render_review(case)
    for heading in ("## 1. Facts", "## 2. Answer set", "## 3. Rendered cells", "## 4. Paired"):
        assert heading in sheet
    assert "### hindsight: executor.named.stripped vs executor.named.carried" in sheet
    assert "+Forty years later" in sheet
    assert sheet.count("- [ ] ") >= 10


def test_committed_json_schema_is_up_to_date() -> None:
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert committed == case_json_schema(), "run `uv run canon schema`"
