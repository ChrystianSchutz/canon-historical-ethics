# Contributing to CANON

Bug reports, new cases, replications on other models and critiques of the design are welcome.
Open an issue before a large change, and read the design invariants below first: a change that
breaks one of them invalidates the measurement, however clean the code.

## Development setup

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy canon
uv run canon validate cases/
```

All four checks run in CI and must pass. The code is typed (`mypy --strict`), formatted and linted
with `ruff` (line length 100), and written in English.

## The drift test

Before any change, answer this question:

> Does CANON still measure whether a model applies the **same rule** when (a) it knows history's
> verdict on the law and when it does not, and (b) it judges from outside and when it is part of
> the apparatus enforcing the law?

If the answer is not a plain yes, open an issue instead of a pull request.

## Design invariants

Breaking any one of these invalidates the benchmark. Most are enforced by `canon validate` or by
the structural gates in `tests/test_gates.py` and `tests/test_falsification.py`.

1. **No LLM-as-judge in primary scoring.** Primary outcomes come from deterministic parsing of a
   single letter (`canon/scoring.py`). Core modules may not import any model client; a test
   enforces this.
2. **Facts come from cited sources, never from model generation.** Every fact is verified before a
   confirmatory run (`verified_by`, `verified_at`); see [`docs/VERIFIER.md`](docs/VERIFIER.md).
3. **Paired frames differ in exactly one variable.** `carried` and `stripped` differ only by the
   hindsight paragraph; `named` and `anonymous` only by the subject. This is enforced
   structurally through templates. Never hand-write separate prompts per cell.
4. **`stripped` frames present the law as it was seen then:** its contemporary justification in
   its strongest form, no evaluative language, and every morally relevant fact present.
5. **Every case has a non-empty `hypothesis_link`,** and each linked metric must be computable from
   the case.
6. **Option sets reflect the real discretion of the institution** on the decision date, with
   `legally_available`, `within_role_authority` and `personal_consequence` on every option.
7. **Refusal is never coded as a middle answer.** Truncated output (`max_tokens`) is a failed
   call.
8. **No single ethics score.** Metrics are reported separately; deflection (M6) is reported next to
   the headline metrics.
9. **A model that answers identically in all frames must not score badly.**
10. **No operational instructions** in any prompt. They trigger safety refusals and confound the
    measurement.
11. **Reproducibility metadata on every sample:** case hash, prompt hashes, permutation seed,
    generation config, raw output and stop reason.
12. **The bank must be able to falsify its thesis.** Headline claims about legalism or resistance
    use matched pairs (`expectation.pair_id`), each with exactly one resistance-expected and one
    compliance-expected case, and only for roles that pass structural matching
    (`canon/pairs.py`). Both cases must ask about the same kind of act; a human reviewer checks
    that, the validator cannot. Unpaired cases are exploratory. Never add only cases where history
    vindicated the resister.
13. **No answer leakage.** Hindsight for action roles comes from a later judgment by another body,
    never from the outcome of the decision asked (a lint checks the decision year). Records
    contain facts and attributed claims, never narrator arguments.
14. **Officials need a costly refusal option where history supports one.** A lenient lawful exit
    is not disobedience. If one case of a pair offers a lawful exit and the other does not, its
    action roles are excluded from M12.
15. **Never average answer letters.** Pair contrasts use category distributions, median shifts,
    probability of superiority and Wilcoxon signed-rank with Holm correction.
16. **Reject cases that cannot discriminate.** A question on which every model gives the same
    answer in every role measures only whether models know the historical canon.
    - *Screening criterion:* at least 3 models; the `named.stripped.neutral_source` cell of every
      scale and action role; at least 2 samples each. Scale ranks 0–1 count as the resistance
      side, rank 2 as the middle, ranks 3–4 as the law's side; action roles either uphold the order
      or do not. A case is uninformative when every valid answer, across all models and roles,
      falls on the same side.
    - *Exempt:* members of a matched pair. The compliance-side controls are meant to be easy, and
      removing one would break the falsification test.
    - *Procedure:* move the YAML to `rejected/cases/` (never delete it), record the evidence and
      a route to making the case informative again in [`REJECTED.md`](REJECTED.md), and never
      reuse screening data as confirmatory evidence.
17. **The subject is inconsistency, not historical recall.** Prefer questions that place the model
    inside a concrete decision: advising the person, acting as the official, or choosing between
    lawful compliance and illegal refusal at a cost. Abstract verdicts on famous events are
    context, not headline evidence.

## The case bank is frozen

`cases/` and `rejected/cases/` are frozen at the text every model in the paper answered. A change
to a case changes its hash and invalidates every result on it. Report errors in a case as an
issue, with the source; do not edit the YAML in a pull request.

New cases are welcome as proposals for a future bank revision. Follow
[`docs/CASE_AUTHORING.md`](docs/CASE_AUTHORING.md): the tooling (`canon new`, `canon validate`,
`canon review`) already exists and adding a case requires no code.

## Running models

- Start runs with `canon eval`, `canon probe` or `canon gandhi`, not `inspect eval`. The `canon`
  commands load `.env` and add `--timeout 300`; Inspect has no request timeout by default, and a
  plain `inspect eval` cannot see `OPEN_ROUTER_KEY`.
- Use `--model mockllm/model` for smoke tests. Real runs cost money: measure the per-session cost
  on a few sessions before sizing a run.
- Reasoning models need a larger `max_tokens`; a truncated answer is a failed call, not an answer.
- `--max-connections` sets how many conversations run at once and cannot be changed mid-run.
- Some providers honour the sampling seed exactly; use `per_sample_seed` and check that replicates
  actually differ before paying for many of them.
- The `claudecli/` and `codexcli/` providers (`canon/inspect_adapter/cli_models.py`) run a model
  through its vendor CLI. The CLI adds its own system context, which is a confound compared with a
  bare API call; report it with any result obtained that way.
- The optional judge must come from a different model family than the model it codes, and it never
  enters primary scoring.

## Pull requests

- Keep a pull request to one purpose and describe what it changes and why.
- Pin any bug fix with a test that fails on the old code.
- If a change alters a reported number, update `scripts/check_claims.py` and say so in the pull
  request.
- Never commit `.env`, raw logs or model API keys.
