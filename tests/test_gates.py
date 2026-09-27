"""Structural CI gates: design invariants that must hold for every case and module."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from canon.lint import lint_stripped_cells
from canon.schema import Case

CANON_DIR = Path(__file__).resolve().parents[1] / "canon"
PRIMARY_SCORING_MODULES = (
    "schema",
    "frames",
    "scoring",
    "provenance",
    "lint",
    "validate",
    "skeleton",
    "review",
    "summary",
    "judge",
    "agreement",
)
MODEL_CLIENT_PACKAGES = {"inspect_ai", "openai", "anthropic", "httpx", "requests", "aiohttp"}


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("module", PRIMARY_SCORING_MODULES)
def test_primary_metrics_contain_no_model_call(module: str) -> None:
    imported = _imported_roots(CANON_DIR / f"{module}.py")
    assert not imported & MODEL_CLIENT_PACKAGES


def test_fixture_stripped_cells_pass_lint(case: Case) -> None:
    assert lint_stripped_cells(case) == []


def test_stripped_variant_has_no_evaluative_language(case_data: dict[str, Any]) -> None:
    case_data["templates"][1]["prompt"] = case_data["templates"][1]["prompt"].replace(
        "Prepare", "Under this regime, prepare"
    )
    problems = lint_stripped_cells(Case.model_validate(case_data))
    assert problems
    assert all("regime" in p for p in problems)


def test_lint_allow_whitelists_contemporary_terms(case_data: dict[str, Any]) -> None:
    case_data["templates"][1]["prompt"] = case_data["templates"][1]["prompt"].replace(
        "Prepare", "Under this regime, prepare"
    )
    case_data["lint_allow"] = ["regime"]
    assert lint_stripped_cells(Case.model_validate(case_data)) == []
