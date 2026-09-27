"""Two-turn solver: natural answer first, forced single-letter choice second."""

from __future__ import annotations

from inspect_ai.model import ChatMessageSystem, ChatMessageUser
from inspect_ai.solver import Generate, Solver, TaskState, solver


@solver
def two_turn_choice(system_prompt: str | None = None) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        if system_prompt:
            state.messages.insert(0, ChatMessageSystem(content=system_prompt))

        # Set only by `per_sample_seed` (see canon_eval): a local server honours a fixed seed
        # exactly, so one task-wide seed would make every replicate the same answer.
        seed = state.metadata.get("generation_seed")
        extra = {} if seed is None else {"seed": seed}

        state = await generate(state, **extra)
        state.metadata["turn1_completion"] = state.output.completion
        state.metadata["turn1_stop_reason"] = state.output.stop_reason

        state.messages.append(ChatMessageUser(content=state.metadata["turn2"]))
        state = await generate(state, **extra)
        state.metadata["turn2_stop_reason"] = state.output.stop_reason
        return state

    return solve
