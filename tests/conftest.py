from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from canon.schema import Case

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples" / "cases"
EXAMPLE_CASE = EXAMPLES_DIR / "example_synthetic.yaml"


@pytest.fixture
def case_data() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(EXAMPLE_CASE.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def case(case_data: dict[str, Any]) -> Case:
    return Case.model_validate(case_data)
