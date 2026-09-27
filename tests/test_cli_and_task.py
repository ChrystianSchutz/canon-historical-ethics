from __future__ import annotations

import json
from pathlib import Path

import pytest

from canon.cli import main
from canon.inspect_adapter.task import build_samples
from canon.schema import Case
from tests.conftest import EXAMPLE_CASE, EXAMPLES_DIR


def test_validate_examples_ok() -> None:
    assert main(["validate", str(EXAMPLES_DIR)]) == 0


def test_validate_reports_broken_case(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("id: not-a-valid-id\n", encoding="utf-8")
    assert main(["validate", str(tmp_path)]) == 1


def test_validate_missing_path() -> None:
    assert main(["validate", "does/not/exist"]) == 1


def test_render_prints_both_turns(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["render", str(EXAMPLE_CASE), "--cell", "executor.named.stripped", "--seed", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "TURN 1" in out and "TURN 2" in out and "LETTER MAP" in out


def test_build_samples_are_unique_and_serialisable(case: Case) -> None:
    samples = build_samples([case], samples_per_cell=3, seed=42)
    assert len(samples) == len(case.cells) * 3
    assert len({s.id for s in samples}) == len(samples)
    for sample in samples:
        json.dumps(sample.metadata)
        assert sample.metadata["case_sha256"]
        assert sample.metadata["canary"] == case.canary


def test_generation_seed_is_off_by_default(case: Case) -> None:
    # API runs of 18 September used one task-wide seed; the default must not change them.
    samples = build_samples([case], samples_per_cell=3, seed=42)
    assert all(s.metadata["generation_seed"] is None for s in samples)


def test_per_sample_seed_differs_by_replicate_and_is_reproducible(case: Case) -> None:
    # Bielik (llama.cpp) honoured seed=42 exactly: 20 replicates, one identical answer.
    first = build_samples([case], samples_per_cell=3, seed=42, per_sample_seed=True)
    again = build_samples([case], samples_per_cell=3, seed=42, per_sample_seed=True)
    seeds = [s.metadata["generation_seed"] for s in first]
    assert seeds == [s.metadata["generation_seed"] for s in again]
    assert len(set(seeds)) == len(seeds)
    assert all(0 <= s < 2**31 for s in seeds)
