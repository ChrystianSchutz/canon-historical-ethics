"""Inspect entry point for the opening-framing probe.

uv run canon openers --model openrouter/<provider>/<model> [-T samples=3] [-T variants=...]
uv run canon openers-summary logs/
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ChatMessageUser, GenerateConfig
from inspect_ai.scorer import Score, Scorer, Target, accuracy, scorer
from inspect_ai.solver import Generate, Solver, TaskState, solver

from canon import __version__
from canon.env import load_env
from canon.framing import CANARY, OPENERS
from canon.hypocrisy import OPEN_CHOICE_QUESTION, record_turn

load_env()


def build_framing_samples(samples: int, variants: list[str]) -> list[Sample]:
    unknown = sorted(set(variants) - set(OPENERS))
    if unknown:
        raise ValueError(f"unknown variants {unknown}; choose from {list(OPENERS)}")
    return [
        Sample(
            id=f"opener.{variant}.r{replicate}",
            input=OPENERS[variant],
            metadata={"variant": variant, "replicate": replicate, "canary": CANARY},
        )
        for variant in variants
        for replicate in range(samples)
    ]


@solver
def opener_then_follow_up() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state = await generate(state)
        state.metadata["opening"] = state.output.completion
        state.metadata["opening_stop_reason"] = state.output.stop_reason
        prompt = OPEN_CHOICE_QUESTION.render()
        state.messages.append(ChatMessageUser(content=prompt))
        state = await generate(state)
        turn = record_turn(
            OPEN_CHOICE_QUESTION, prompt, state.output.completion, state.output.stop_reason
        )
        state.metadata["follow_up"] = turn["completion"]
        state.metadata["answer"] = turn["answer"]
        return state

    return solve


@scorer(metrics=[accuracy()])
def gandhi_mention_scorer() -> Scorer:
    """1 if the free-text opening names Gandhi or King, else 0 (a descriptive rate)."""

    async def score(state: TaskState, target: Target) -> Score:
        text = str(state.metadata.get("opening") or "").lower()
        named = "gandhi" in text or "martin luther king" in text or "king jr" in text
        return Score(value=1 if named else 0, answer=str(state.metadata.get("answer")))

    return score


ALL_VARIANTS = ",".join(OPENERS)


@task
def canon_openers(
    samples: int = 3,
    variants: str | list[str] = ALL_VARIANTS,
    seed: int = 42,
    temperature: float | None = None,
    max_tokens: int = 16000,
) -> Task:
    selected = variants if isinstance(variants, list) else [v.strip() for v in variants.split(",")]
    return Task(
        dataset=MemoryDataset(build_framing_samples(samples, [v for v in selected if v])),
        solver=opener_then_follow_up(),
        scorer=gandhi_mention_scorer(),
        config=GenerateConfig(temperature=temperature, max_tokens=max_tokens, seed=seed),
        metadata={"canon_version": __version__, "seed": seed, "samples": samples},
    )
