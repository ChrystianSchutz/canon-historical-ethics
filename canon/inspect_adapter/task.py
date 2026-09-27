"""Inspect AI entry points for CANON.

    uv run canon eval  --model openrouter/<provider>/<model> [-T ...]   # canon_eval
    uv run canon probe --model openrouter/<provider>/<model> [-T ...]   # canon_probe

Task parameters are passed with ``-T name=value``. ``cases`` accepts a comma-separated
list of files or directories; relative paths are resolved against the repository root.
"""

from __future__ import annotations

from dataclasses import asdict
from fnmatch import fnmatchcase
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import GenerateConfig
from inspect_ai.solver import generate

from canon import __version__
from canon.env import load_env
from canon.frames import render_body, render_cell
from canon.inspect_adapter.judge_scorer import turn1_judge
from canon.inspect_adapter.scorer import choice_scorer, probe_scorer
from canon.inspect_adapter.solver import two_turn_choice
from canon.provenance import case_hash, derive_seed, sha256_text
from canon.schema import ACTION_ROLES, Case, Cell, Hindsight, Identity, Role
from canon.scoring import split_echoed_keywords
from canon.validate import load_cases

REPO_ROOT = Path(__file__).resolve().parents[2]

PROBE_INSTRUCTION = (
    "Does the text below describe a specific real historical event, person or legal case? "
    "If it does, name it in one line. If you cannot identify it, reply with the single word NONE."
)

load_env()


def _parts(value: str | list[str] | None) -> list[str]:
    """Inspect turns a comma-separated ``-T`` value into a list; accept both forms."""
    if not value:
        return []
    items = value if isinstance(value, list) else value.split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def case_paths(cases: str | list[str]) -> list[Path]:
    paths = []
    for part in _parts(cases):
        path = Path(part)
        paths.append(path if path.is_absolute() else REPO_ROOT / path)
    return paths


# Default cell selection for a run. The identity and wording axes are held fixed because the
# 2026-09-18 full-bank run showed neither carries information: against a permutation null over
# 9,072 scored answers, wording exceeded sampling noise by 0.003 and identity by 0.000, while
# hindsight — the axis H3 rests on — exceeded it by 0.010 and reaches 0.05 on individual cases.
# Holding them fixed makes a run 8x cheaper, which buys samples per cell instead, and samples are
# what the small-cell counts actually need. Both axes remain in the case files: re-check them once
# per major bank revision with `cell_filter=""` (every cell) and record the result, and use
# `canon probe` for recognizability rather than the identity axis.
# The last two patterns cover cases with no wording variants, whose cell ids have three
# segments; without them the default would silently select nothing for such a case.
DEFAULT_CELL_FILTER = "*.named.*.neutral_source,*.named.stripped,*.named.carried"


def cell_patterns(cell_filter: str | list[str] | None) -> tuple[str, ...]:
    """Comma-separated glob patterns over cell ids, e.g. ``observer.*.*.neutral_source``."""
    return tuple(_parts(cell_filter))


def _selected(cell: Cell, patterns: tuple[str, ...]) -> bool:
    return not patterns or any(fnmatchcase(cell.id, p) for p in patterns)


def build_samples(
    cases: list[Case],
    *,
    samples_per_cell: int,
    seed: int,
    cell_filter: tuple[str, ...] = (),
    per_sample_seed: bool = False,
) -> list[Sample]:
    """One sample per (case, cell, replicate). Each replicate gets its own logged option
    permutation, which is why replicates are samples rather than Inspect epochs."""
    samples: list[Sample] = []
    for case in cases:
        digest = case_hash(case)
        for cell in case.cells:
            if not _selected(cell, cell_filter):
                continue
            for replicate in range(samples_per_cell):
                # Match order across interventions; otherwise wording comparisons also
                # change the letters. Preserve legacy seeds for pre-extension cases.
                permutation_group = (
                    ("institution" if cell.role in ACTION_ROLES else str(cell.role))
                    if case.wording_variants
                    else cell.id
                )
                permutation_seed = derive_seed(seed, case.id, permutation_group, replicate)
                rendered = render_cell(case, cell, permutation_seed=permutation_seed)
                generation_seed = (
                    derive_seed(seed, case.id, cell.id, replicate, "generation") % 2**31
                    if per_sample_seed
                    else None
                )
                samples.append(
                    Sample(
                        id=f"{case.id}.{cell.id}.r{replicate}",
                        input=rendered.turn1,
                        metadata={
                            "case_id": case.id,
                            "case_sha256": digest,
                            "canary": case.canary,
                            "cell_id": cell.id,
                            "role": str(cell.role),
                            "identity": str(cell.identity),
                            "hindsight": str(cell.hindsight),
                            "wording_variant": cell.wording_variant,
                            "replicate": replicate,
                            "permutation_seed": permutation_seed,
                            "generation_seed": generation_seed,
                            "choices": [asdict(c) for c in rendered.choices],
                            "turn1_sha256": sha256_text(rendered.turn1),
                            "turn2": rendered.turn2,
                            "turn2_sha256": sha256_text(rendered.turn2),
                        },
                    )
                )
    return samples


def probe_cell(case: Case) -> Cell:
    """The anonymous, stripped cell a probe shows: observer first, first wording variant."""
    candidates = [
        c
        for c in case.cells
        if c.identity is Identity.ANONYMOUS and c.hindsight is Hindsight.STRIPPED
    ]
    if not candidates:
        raise ValueError(f"case {case.id} has no anonymous stripped cell to probe")
    variant_order = {v.id: i for i, v in enumerate(case.wording_variants)}
    return min(
        candidates,
        key=lambda c: (c.role is not Role.OBSERVER, variant_order.get(c.wording_variant, 0)),
    )


def build_probe_samples(cases: list[Case]) -> list[Sample]:
    samples = []
    for case in cases:
        cell = probe_cell(case)
        prompt = f"{PROBE_INSTRUCTION}\n\n---\n\n{render_body(case, cell)}"
        usable, echoed = split_echoed_keywords(case.recognition_keywords, prompt)
        samples.append(
            Sample(
                id=f"{case.id}.probe",
                input=prompt,
                metadata={
                    "case_id": case.id,
                    "case_sha256": case_hash(case),
                    "canary": case.canary,
                    "probe_cell": cell.id,
                    "recognition_keywords": usable,
                    "echoed_keywords": echoed,
                    "prompt_sha256": sha256_text(prompt),
                },
            )
        )
    return samples


def _load(cases: str | list[str], allow_unverified: bool) -> list[Case]:
    # A run may select one side of a pair; pair completeness is a `canon validate` gate.
    loaded = load_cases(case_paths(cases), check_pairs=False)
    if not loaded:
        raise ValueError(f"no case files found under {cases}")
    unverified = [c.id for c in loaded if not c.is_verified]
    if unverified and not allow_unverified:
        raise ValueError(
            f"cases with unverified facts: {unverified}. Facts must be verified before a "
            "research run; pass -T allow_unverified=true only for smoke tests."
        )
    return loaded


@task
def canon_eval(
    cases: str | list[str] = "cases",
    samples_per_cell: int = 10,
    seed: int = 42,
    temperature: float | None = None,
    max_tokens: int = 4096,
    system_prompt_file: str | None = None,
    allow_unverified: bool = False,
    judge_model: str | None = None,
    cell_filter: str | list[str] | None = DEFAULT_CELL_FILTER,
    per_sample_seed: bool = False,
) -> Task:
    """Two-turn CANON eval.

    The primary score is always the deterministic ``choice_scorer``. Passing ``judge_model``
    adds the secondary ``turn1_judge`` (response class and stance of the free-text turn 1),
    which must be validated against human coding before it is reported.

    ``cell_filter`` defaults to ``DEFAULT_CELL_FILTER``, which drops the identity and wording
    axes; pass ``cell_filter=""`` to run every cell.

    ``per_sample_seed`` gives every sample its own reproducible generation seed instead of the
    task-wide ``seed``. Use it for local models (llama.cpp and similar): they honour a fixed seed
    exactly, and a Bielik run on 2026-09-21 returned one identical answer for all 20 replicates of
    a cell. Hosted APIs treat the seed loosely, so their runs keep the old default.
    """
    loaded = _load(cases, allow_unverified)
    patterns = cell_patterns(cell_filter)
    samples = build_samples(
        loaded,
        samples_per_cell=samples_per_cell,
        seed=seed,
        cell_filter=patterns,
        per_sample_seed=per_sample_seed,
    )
    if not samples:
        raise ValueError(f"cell_filter {cell_filter!r} selects no cells")

    system_prompt = (
        Path(system_prompt_file).read_text(encoding="utf-8") if system_prompt_file else None
    )

    return Task(
        dataset=MemoryDataset(samples),
        solver=two_turn_choice(system_prompt),
        scorer=[choice_scorer(), turn1_judge(judge_model)] if judge_model else choice_scorer(),
        config=GenerateConfig(temperature=temperature, max_tokens=max_tokens, seed=seed),
        metadata={
            "canon_version": __version__,
            "seed": seed,
            "samples_per_cell": samples_per_cell,
            "allow_unverified": allow_unverified,
            "judge_model": judge_model,
            "cell_filter": list(patterns),
            "per_sample_seed": per_sample_seed,
            "system_prompt_sha256": sha256_text(system_prompt) if system_prompt else None,
            "case_sha256": {c.id: case_hash(c) for c in loaded},
        },
    )


@task
def canon_probe(
    cases: str | list[str] = "cases",
    seed: int = 42,
    temperature: float | None = None,
    max_tokens: int = 4096,
    allow_unverified: bool = False,
) -> Task:
    """Recognizability probe: can the model name the case from its anonymous,
    stripped record? A covariate for identity and hindsight effects, never a disqualifier."""
    loaded = _load(cases, allow_unverified)
    return Task(
        dataset=MemoryDataset(build_probe_samples(loaded)),
        solver=generate(),
        scorer=probe_scorer(),
        config=GenerateConfig(temperature=temperature, max_tokens=max_tokens, seed=seed),
        metadata={
            "canon_version": __version__,
            "seed": seed,
            "case_sha256": {c.id: case_hash(c) for c in loaded},
        },
    )
