"""Inspect scorer running the secondary turn-1 LLM judge. See ``canon.judge`` for the rules."""

from __future__ import annotations

from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.scorer import Score, Scorer, Target, frequency, scorer
from inspect_ai.solver import TaskState

from canon.frames import Choice
from canon.judge import build_judge_prompt, parse_judge_output
from canon.provenance import sha256_text


@scorer(metrics=[frequency()])
def turn1_judge(judge_model: str, max_tokens: int = 4096) -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        model = get_model(
            judge_model, config=GenerateConfig(temperature=0.0, max_tokens=max_tokens)
        )
        choices = [Choice(**c) for c in state.metadata["choices"]]
        response = state.metadata.get("turn1_completion", "")
        prompt = build_judge_prompt(state.input_text, response, choices)

        output = await model.generate(prompt)
        verdict = parse_judge_output(output.completion, choices)

        return Score(
            value=verdict.label,
            answer=response,
            explanation=verdict.evidence,
            metadata={
                "judge_model": judge_model,
                "stance_letter": verdict.stance_letter,
                "stance_answer_id": verdict.stance_answer_id,
                "judge_prompt_sha256": sha256_text(prompt),
                "judge_raw": output.completion,
                "judge_stop_reason": output.stop_reason,
            },
        )

    return score
