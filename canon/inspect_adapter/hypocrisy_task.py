"""Inspect entry point for the "be like Gandhi" hypocrisy dialogue.

uv run canon gandhi --model openrouter/<provider>/<model> [-T samples=5] [-T orders=...]
uv run canon gandhi-summary logs/
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ChatMessageSystem, ChatMessageUser, GenerateConfig
from inspect_ai.scorer import Score, Scorer, Target, scorer
from inspect_ai.solver import Generate, Solver, TaskState, solver

from canon import __version__
from canon.env import load_env
from canon.hypocrisy import (
    CANARY,
    OPEN_PROMPT,
    ORDER_NAMES,
    QUESTION_BY_ID,
    TOPIC_SETS,
    Stage,
    analyze,
    orders_for,
    questions_sha256,
    reckoning_prompt,
    record_turn,
)
from canon.provenance import derive_seed, sha256_text

load_env()


def _parts(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    items = value if isinstance(value, list) else value.split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def build_hypocrisy_samples(
    samples: int,
    orders: list[str],
    topic_set: str = "core",
    seed: int | None = None,
) -> list[Sample]:
    """``seed`` set: each conversation gets its own reproducible generation seed (see
    ``canon_eval``'s ``per_sample_seed``); ``None`` keeps the task-wide seed."""
    unknown = sorted(set(orders) - set(ORDER_NAMES))
    if unknown:
        raise ValueError(f"unknown orders {unknown}; choose from {list(ORDER_NAMES)}")
    if topic_set not in TOPIC_SETS:
        raise ValueError(f"unknown topic set {topic_set!r}; choose from {sorted(TOPIC_SETS)}")
    prefix = "gandhi" if topic_set == "core" else f"gandhi_{topic_set}"
    return [
        Sample(
            id=f"{prefix}.{order}.r{replicate}",
            input=OPEN_PROMPT,
            metadata={
                "order": order,
                "topic_set": topic_set,
                "replicate": replicate,
                "canary": CANARY,
                "questions_sha256": questions_sha256(topic_set),
                "generation_seed": None
                if seed is None
                else derive_seed(seed, prefix, order, replicate, "generation") % 2**31,
            },
        )
        for order in orders
        for replicate in range(samples)
    ]


@solver
def hypocrisy_dialogue(system_prompt: str | None = None) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        if system_prompt:
            state.messages.insert(0, ChatMessageSystem(content=system_prompt))
        turns: list[dict[str, object]] = []
        sequence = orders_for(state.metadata["order"], state.metadata.get("topic_set", "core"))
        seed = state.metadata.get("generation_seed")
        extra = {} if seed is None else {"seed": seed}
        for index, question_id in enumerate(sequence):
            question = QUESTION_BY_ID[question_id]
            if index == 0:
                prompt = OPEN_PROMPT  # already the sample input
            else:
                prompt = (
                    reckoning_prompt(turns)
                    if question.stage is Stage.RECKONING
                    else question.render()
                )
                state.messages.append(ChatMessageUser(content=prompt))
            state = await generate(state, **extra)
            turns.append(
                record_turn(
                    question,
                    prompt,
                    state.output.completion,
                    state.output.stop_reason,
                )
            )
            state.metadata["turns"] = turns
        return state

    return solve


@scorer(metrics=[])
def hypocrisy_scorer() -> Scorer:
    """Separate observable outcomes and coverage, with no aggregate metric.

    An earlier version returned the sum of all flag hits and averaged it, which is exactly the
    single ethics score AGENTS invariant 8 forbids: flag families overlap, so one topic could
    contribute four hits, while a conversation that answered nothing scored a clean zero.
    """

    async def score(state: TaskState, target: Target) -> Score:
        analysis = analyze(state.metadata.get("turns") or [])
        return Score(value=dict(analysis.outcomes()), metadata=analysis.to_dict())

    return score


@task
def canon_gandhi(
    samples: int = 5,
    orders: str | list[str] = "example_first,concrete_first,present_first",
    seed: int = 42,
    temperature: float | None = None,
    max_tokens: int = 16000,
    system_prompt_file: str | None = None,
    topic_set: str = "core",
    per_sample_seed: bool = False,
) -> Task:
    """The "be like Gandhi" hypocrisy dialogue: one multi-turn conversation per sample.

    ``topic_set=authoritarian`` swaps the Gandhi and King acts for resistance to authoritarian
    law (Tiananmen 1989, Soviet samizdat, the 1952 Defiance Campaign, White Rose, Polish martial
    law), keeping the Little Rock control.
    """
    selected = _parts(orders)
    system_prompt = (
        Path(system_prompt_file).read_text(encoding="utf-8") if system_prompt_file else None
    )
    return Task(
        dataset=MemoryDataset(
            build_hypocrisy_samples(samples, selected, topic_set, seed if per_sample_seed else None)
        ),
        solver=hypocrisy_dialogue(system_prompt),
        scorer=hypocrisy_scorer(),
        config=GenerateConfig(temperature=temperature, max_tokens=max_tokens, seed=seed),
        metadata={
            "canon_version": __version__,
            "seed": seed,
            "samples": samples,
            "orders": selected,
            "topic_set": topic_set,
            "per_sample_seed": per_sample_seed,
            "questions_sha256": questions_sha256(topic_set),
            "system_prompt_sha256": sha256_text(system_prompt) if system_prompt else None,
        },
    )
