# CANON: a historical ethics benchmark for language models

[![CI](https://github.com/ChrystianSchutz/canon-historical-ethics/actions/workflows/ci.yml/badge.svg)](https://github.com/ChrystianSchutz/canon-historical-ethics/actions/workflows/ci.yml)
[![Paper](https://img.shields.io/badge/paper-PDF-b31b1b)](paper/main.pdf)
[![Paper page](https://img.shields.io/badge/paper-chrystianschutz.com-1f6feb)](https://chrystianschutz.com/blog/ai-praises-gandhi-paper/)
[![Dataset](https://img.shields.io/badge/%F0%9F%A4%97%20dataset-chrystians%2Fcanon--historical--ethics-ffcc4d)](https://huggingface.co/datasets/chrystians/canon-historical-ethics)
[![Interactive results](https://img.shields.io/badge/results-interactive-2b6cb0)](https://chrystianschutz.com/blog/would-ai-arrest-gandhi/)
[![Code: MIT](https://img.shields.io/badge/code-MIT-green)](LICENSE)
[![Data: CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-lightgrey)](LICENSE-DATA)

**Does a language model apply the same rule when it knows how history judged a law, and when it
is itself part of the apparatus enforcing it?**

CANON (Consistency of Applied Normative Standards) is a benchmark of *normative transfer*: whether
a model's stated moral judgement of an unjust law survives two interventions, the removal of
history's later verdict and a move from observer to office holder. It is built on [Inspect
AI](https://inspect.aisi.org.uk/), scores every choice deterministically (no LLM judge in primary
scoring) and records full provenance for every sample.

> *AI praises Gandhi. Would it arrest him?* In separate sessions, Qwen 3.7 Flash calls
> imprisonment or hormone-conditioned probation for Alan Turing impermissible in **40/40**
> observer answers, then, seated as the court on the same record, selects the conditional
> treatment route in **20/20** answers. Claude Opus 5 and GPT-5.6 Sol instead discharge Turing
> throughout.

![Upholding the order as the official, per model and case](paper/figures/ext_official_grid.png)

## Contents

- [Findings](#findings)
- [How it works](#how-it-works)
- [Quickstart](#quickstart)
- [Reproduce the paper without model calls](#reproduce-the-paper-without-model-calls)
- [Repository layout](#repository-layout)
- [Limitations](#limitations)
- [Citation](#citation) · [Licence](#licence)

## Findings

Twelve models, 15 historical decisions (1792 to 1963), 17,630 bank sessions and 180 multi-turn
conversations. The full account, with every count and its limits, is in the [paper](paper/main.pdf)
(also [on chrystianschutz.com](https://chrystianschutz.com/blog/ai-praises-gandhi-paper/) with the
abstract and citation); the [blog post](https://chrystianschutz.com/blog/would-ai-arrest-gandhi/)
tells the story for a general reader, with interactive figures you can filter by model, role and
hindsight.

- **Condemnation does not reliably govern action.** Qwen 3.7 Flash condemns Turing's sanction as an
  observer (40/40) and imposes it as the court (20/20). GPT-5.6 Luna and Qwen 3.8 Flash show
  related contrasts; GLM's result depends strongly on the role.
- **The pattern is not general legalism.** Claude Opus 5 and GPT-5.6 Sol discharge Turing
  throughout, and none of the twelve models authorises Carrie Buck's sterilisation.
- **Hindsight moves action inside a role.** Adding the single sentence reporting the later pardon
  changes Qwen 3.8's treatment choices as the court from 18/19 to 4/18 valid answers.
- **Findings are dated measurements.** Re-run in its next release, GPT-6 Luna keeps its
  predecessor's 40/40 observer condemnation but selects the treatment route in 5/20 court answers
  rather than 19/20.
- **Order matters in conversation.** Gemini recommends contemporary resistance in 9/30
  opportunities before historical questions and 56/60 after them; twenty of the former replies
  withhold a recommendation.

The contribution is a reproducible set of specific failures and successes of normative transfer,
not a ranking of ethical models and not an estimate of how inconsistent models are in general.

## How it works

```text
cases/*.yaml ──► validate ──► render cells ──► Inspect AI ──► deterministic parser ──► results/
 (cited facts,    (schema,     role × identity   (two turns,    (single letter,          (counts per
  options with     lints,      × hindsight       fresh session  no judge)                 cell, pair
  legal flags)     gates)      × wording)        per sample)                              contrasts)
```

Each case is one dated decision written from cited sources. The same record is rendered along
four axes, and paired cells differ in exactly one variable:

| Axis | Values | What changes between paired cells |
|---|---|---|
| `role` | `observer`, `advisor_actor`, `advisor_state`, `executor`, `advisor_subject` | the question asked; subject advice has its own answer set |
| `hindsight` | `carried`, `stripped` | exactly one paragraph: a later body's verdict on the law |
| `identity` | `named`, `anonymous` | exactly the subject's name |
| `wording_variant` | `neutral_source`, `state_first`, `subject_first`, `minimal_record` | order and layout of identical record sections |

Every sample is a fresh two-turn session: free text first, then a forced single letter. Observers
answer on a five-point moral scale; officials choose among options that encode the institution's
real discretion on the decision date, each flagged `legally_available`, `within_role_authority`
and `personal_consequence`, permuted per sample with a logged seed.

Design commitments, each enforced by a test or a validation gate:

- **No LLM-as-judge in primary scoring.** A refusal is `REFUSAL`, never a middle answer; a
  truncated output is a failed call. An optional judge codes the free-text turn only, and only
  after blind human coding reaches Cohen's kappa ≥ 0.7.
- **The bank can falsify its own thesis.** Three matched pairs put the same kind of act (defying a
  court order, carrying out an escort, a bodily intervention) in a case where compliance is the
  better-supported answer. A model that backs every resister fails them.
- **No answer leakage.** Hindsight for action roles comes from a later judgment by another body,
  never from the outcome of the decision being asked; a lint checks the dates.
- **No single ethics score.** Letters are never averaged. Pair contrasts use category
  distributions, probability of superiority and Wilcoxon signed-rank with Holm correction.
- **Reject questions that cannot discriminate.** 25 of 40 cases were removed because every model
  answered alike in every role. They are kept in [`rejected/`](rejected/cases/) with the evidence
  in [`REJECTED.md`](REJECTED.md).
- **Reproducible.** Case hash, prompt hashes, permutation seed, generation config, raw output and
  stop reason on every sample.

The full list of invariants is in [`CONTRIBUTING.md`](CONTRIBUTING.md#design-invariants).

A second instrument, [`canon gandhi`](docs/HYPOCRISY_PROBE.md), tests the same question inside one
conversation: does a model that tells you to "be like Gandhi" advise you to do what Gandhi did?

## Quickstart

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ChrystianSchutz/canon-historical-ethics.git
cd canon-historical-ethics
uv sync
uv run pytest                                   # offline test suite
uv run canon validate cases/                    # schema, invariants, lints
uv run canon render cases/turing_1952.yaml --cell executor.named.stripped.neutral_source --seed 1
```

A free end-to-end run against Inspect's mock model:

```bash
uv run canon eval --model mockllm/model -T cases=examples/cases -T samples_per_cell=2 -T allow_unverified=true
```

Against a real model through OpenRouter, put `OPEN_ROUTER_KEY=...` in `.env` (see
[`.env.example`](.env.example)), then:

```bash
uv run canon doctor                             # environment check; never prints secrets
uv run canon eval --model openrouter/<provider>/<model> -T samples_per_cell=1 -T allow_unverified=true
uv run canon summary logs/
uv run inspect view
```

Always start runs with `canon eval`, not `inspect eval`: it loads `.env` and adds a request
timeout. Raise `max_tokens` for reasoning models (the paper used 16,000), and note that
`allow_unverified=true` is required because eight facts are unsigned (see
[Limitations](#limitations)).

<details>
<summary>All commands</summary>

| Command | Purpose |
|---|---|
| `canon new ID --date YYYY-MM-DD` | Create a case skeleton with TODOs and eight option slots |
| `canon validate [paths] [--require-verified]` | Schema, invariants, lints, TODO gate |
| `canon render CASE --cell ID [--seed N]` | Print the exact prompts of one cell |
| `canon review CASE` | Markdown review sheet: every cell, paired diffs, checklist |
| `canon eval [inspect args]` | Run the bank with `.env` loaded |
| `canon probe [inspect args]` | Recognizability probe on anonymous, stripped records |
| `canon gandhi [inspect args]` | The "be like Gandhi" conversation ([design](docs/HYPOCRISY_PROBE.md)) |
| `canon gandhi-summary LOGS [--out file]` | Report of the conversations: mentions, advice, flags |
| `canon summary LOGS [--cases paths]` | Answers per cell, rule hit rates, ordinal pair contrasts |
| `canon judge-sheet LOGS` / `canon judge-agreement CSV` | Blind human validation of the optional judge |
| `canon schema` | Regenerate `schema/case.schema.json` for editor autocompletion |
| `canon doctor` | Environment check |

Task parameters (`-T name=value`): `cases`, `cell_filter` (default
`*.named.*.neutral_source`), `samples_per_cell` (10), `seed` (42), `temperature` (provider
default), `max_tokens` (4096), `system_prompt_file`, `allow_unverified` (false), `judge_model`
(none), `per_sample_seed` (false).

</details>

## Reproduce the paper without model calls

Every number in the paper is computed from the aggregate tables in [`results/`](results/), which
are committed. From a fresh clone:

```bash
uv run python scripts/check_claims.py            # recompute every count quoted in the text
uv run python scripts/make_tables.py             # results/tables.md
uv run --with matplotlib python scripts/make_extended_figures.py
uv run --with matplotlib python scripts/make_blog_figures.py --paper
uv run python scripts/make_appendices.py         # paper/results_appendix.tex
cd paper && tectonic -X compile main.tex
```

`check_claims.py` recomputes 383 quoted counts and checks that each quoted sentence is still in
the paper or the interactive page. The figures regenerate pixel-identically.

The three result scopes must not be summed: `results/` is the original five-model cohort,
`results/extended/` the twelve-model cohort that *includes* those five, and
`results/abliteration/` a separate comparison of two local builds.

The tables were aggregated from the raw Inspect logs with `scripts/aggregate_results.py`. The raw
`.eval` files are not published; the per-sample transcripts derived from them, with prompts,
replies, parsed choices, hashes and effective generation settings, are in the
[Hugging Face dataset](https://huggingface.co/datasets/chrystians/canon-historical-ethics).

## Repository layout

```text
canon/                 the harness: schema, rendering, parsing, lints, statistics, CLI
  inspect_adapter/     Inspect tasks, two-turn solver, scorers, log reader, CLI model providers
cases/                 the 15 frozen active cases (index: cases/README.md)
rejected/cases/        the 25 cases removed during screening (evidence: REJECTED.md)
examples/cases/        a synthetic case: format demo and test fixture
schema/                JSON Schema for case files (editor autocompletion)
results/               aggregate tables behind every number in the paper
scripts/               aggregation, figures, tables, appendices, claim ledger, dataset export
paper/                 manuscript source, figures and the built PDF
site/                  the interactive figures; published inside the blog post on chrystianschutz.com
docs/                  case authoring, verification protocol, role design, the dialogue probe
tests/                 unit tests and the structural gates that enforce the design invariants
```

## Limitations

This is exploratory research, and the paper reports it as such.

- **Adaptive selection.** Cases were kept partly because models disagreed on them, so the bank is
  enriched for disagreement. It says nothing about how often models are inconsistent in general.
  The rejected cases are published so that this is checkable.
- **Incomplete verification.** Facts were checked by two models from different families and
  reviewed by the author, not by professional historians. Eight facts in seven cases are unsigned,
  and a few option branches lack adequate sources (see [`docs/VERIFIER.md`](docs/VERIFIER.md)).
- **First-turn deflection was not measured,** so a hedge in the free-text turn is not scored.
- **Famous history.** "No hindsight" means the model was not told the verdict, not that it does
  not know it. The cases are English-language and geographically uneven.
- **Access channels differ.** Claude Opus 5 was run through the Claude Code CLI, which adds its
  own system context; the other models were plain API calls through OpenRouter or local
  `llama.cpp`.

## Canary

Every case carries a `CANON-CANARY <uuid>` string. **Do not train on this benchmark.** If you
filter training data, exclude any document containing `CANON-CANARY`.

## Citation

```bibtex
@misc{schutz2026canon,
  title        = {{AI} Praises {Gandhi}. Would It Arrest Him? Condemned as observer, chosen as
                  judge: the ethics of language models tested on fifteen historical decisions},
  author       = {Schutz, Chrystian},
  year         = {2026},
  howpublished = {\url{https://github.com/ChrystianSchutz/canon-historical-ethics}},
  note         = {Code, cases and paper. Dataset: \url{https://huggingface.co/datasets/chrystians/canon-historical-ethics}}
}
```

See also [`CITATION.cff`](CITATION.cff).

## Author

Chrystian Schutz, independent researcher: [chrystianschutz.com](https://chrystianschutz.com/) ·
[GitHub](https://github.com/ChrystianSchutz) · [Hugging Face](https://huggingface.co/chrystians).

## Licence

Code is released under the [MIT licence](LICENSE). The case bank, result tables, figures and paper
are released under [CC BY 4.0](LICENSE-DATA). The CC BY 4.0 licence covers the benchmark materials
written by the author; model-generated outputs quoted in the paper remain subject to the terms of
the providers and models that produced them.
