"""Claim ledger: every count quoted in the prose, recomputed from the result tables.

    uv run python scripts/check_claims.py [--blog path/to/BLOG.md]

Each claim names the file it appears in, a snippet that must appear there verbatim (so a claim
cannot silently drift out of the text), and the count it asserts, recomputed from the result
tables. The script prints every claim and exits non-zero if any snippet is missing or any count
disagrees. It checks the claims listed here and nothing else: hand-written prose that is not in
the ledger is not verified by it. When you change a number in the text, change it here too.

Scopes: the case commentary covers the original five models (`results/`); the manuscript, blog
and interactive page cover the twelve-model cohort (`results/extended/`) and the local build
comparison (`results/abliteration/`). Each claim reads the scope its text reports.

Texts checked: the manuscript (`paper/main.tex`), its case appendix (`paper/cases.tex`), the
interactive page (`site/index.html`) and the companion blog post. The blog post is published
separately, not in this repository: pass its path with `--blog` (default `BLOG.md` in the
repository root). When it is absent its claims are skipped, but their counts are still
recomputed and checked.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figure_data import (  # noqa: E402
    Cell,
    Count,
    dialogue_status_count,
    law_side_count,
    load_csv,
    option_count,
    valid_option_count,
)

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
PAPER = "paper/main.tex"
CASES_MD = "paper/cases.tex"
BLOG = "BLOG.md"
MODELS = ("Opus 5", "Sol", "Luna", "Muse", "Qwen")
ACTION = ("executor", "advisor_state")
BOTH = ("stripped", "carried")
ORDER_ALL = ("example_first", "concrete_first", "present_first")


@dataclass(frozen=True)
class Claim:
    where: str
    snippet: str
    expected: tuple[int, int]
    compute: Callable[[], Count]


CELLS: list[Cell] = []
FLAGS: list[Cell] = []


def rows(
    case: str,
    roles: Sequence[str],
    models: Sequence[str] = MODELS,
    hindsight: Sequence[str] = BOTH,
) -> list[Cell]:
    out = [
        c
        for c in CELLS
        if c["case"] == case
        and c["role"] in roles
        and c["model"] in models
        and c["hindsight"] in hindsight
    ]
    if not out:
        raise LookupError(f"no rows for {case} {roles} {models} {hindsight}")
    return out


def law(
    case: str, roles: Sequence[str], models: Sequence[str] = MODELS, hindsight: Sequence[str] = BOTH
) -> Callable[[], Count]:
    return lambda: law_side_count(rows(case, roles, models, hindsight))


def opt(
    case: str,
    roles: Sequence[str],
    option: str | Sequence[str],
    models: Sequence[str] = MODELS,
    hindsight: Sequence[str] = BOTH,
) -> Callable[[], Count]:
    return lambda: option_count(rows(case, roles, models, hindsight), option)


def all_models_field(field: str) -> Callable[[], Count]:
    def compute() -> Count:
        return Count(sum(int(r[field]) for r in FLAGS), sum(int(r["conversations"]) for r in FLAGS))

    return compute


def sessions() -> Count:
    n = sum(int(c["n"]) for c in CELLS)
    return Count(n, n)


CLAIMS: tuple[Claim, ...] = (
    # --- Case commentary: paper/cases.tex -------------------------------------------------------
    Claim(
        CASES_MD,
        "0 law-side answers out of 450",
        (0, 450),
        law("FUGITIVE-1854", ["observer", *ACTION]),
    ),
    Claim(
        CASES_MD,
        "Zero law-side answers out of 450 scored answers",
        (0, 450),
        law("BUCK-1927", ["observer", *ACTION]),
    ),
    Claim(
        CASES_MD,
        "Qwen does once in each\nstripped cell",
        (2, 40),
        law("ANTHONY-1872", ["observer", "advisor_actor"], ["Qwen"], ["stripped"]),
    ),
    Claim(
        CASES_MD,
        "Muse advises against voting in 15/20",
        (15, 20),
        law("ANTHONY-1872", ["advisor_actor"], ["Muse"], ["stripped"]),
    ),
    Claim(
        CASES_MD,
        "Muse does in 2/20 state-adviser",
        (2, 20),
        law("PLESSY-1892", ["advisor_state"], ["Muse"], ["carried"]),
    ),
    Claim(
        CASES_MD,
        "Luna in 3/20 without and 0/20 with it",
        (3, 20),
        law("PLESSY-1892", ["advisor_state"], ["Luna"], ["stripped"]),
    ),
    Claim(
        CASES_MD,
        "Sol calls the enforcement justified or required in 19/20",
        (19, 20),
        law("JACOBSON-1905", ["observer"], ["Sol"]),
    ),
    Claim(CASES_MD, "and Opus in\n5/10", (5, 10), law("JACOBSON-1905", ["observer"], ["Opus 5"])),
    Claim(
        CASES_MD, "Muse (8/40), Qwen (3/40)", (8, 40), law("JACOBSON-1905", ["observer"], ["Muse"])
    ),
    Claim(
        CASES_MD, "Muse (8/40), Qwen (3/40)", (3, 40), law("JACOBSON-1905", ["observer"], ["Qwen"])
    ),
    Claim(
        CASES_MD,
        "(Qwen 33/40, the others\nall)",
        (33, 40),
        law("JACOBSON-1905", ["advisor_state"], ["Qwen"]),
    ),
    Claim(CASES_MD, "an observer (0/150)", (0, 150), law("CHAMPARAN-1917", ["observer"])),
    Claim(
        CASES_MD,
        "Muse 33/40, Qwen 38/40)",
        (38, 40),
        opt("CHAMPARAN-1917", ["observer"], "permissible", ["Qwen"]),
    ),
    Claim(
        CASES_MD,
        "Muse\ndischarges in 39 of 40 judge answers",
        (39, 40),
        opt("TURING-1952", ["executor"], "absolute_discharge", ["Muse"]),
    ),
    Claim(
        CASES_MD,
        "every one of 150\nobserver answers, says impermissible",
        (150, 150),
        opt("TURING-1952", ["observer"], "impermissible"),
    ),
    Claim(CASES_MD, "(100% of 300 action answers)", (300, 300), law("LITTLEROCK-1957", ACTION)),
    Claim(
        CASES_MD,
        "in 30/40 answers and Luna in 2/40",
        (30, 40),
        opt("LITTLEROCK-1957", ["observer"], "permissible", ["Qwen"]),
    ),
    Claim(
        CASES_MD,
        "in 30/40 answers and Luna in 2/40",
        (2, 40),
        opt("LITTLEROCK-1957", ["observer"], "permissible", ["Luna"]),
    ),
    Claim(CASES_MD, "permissible or better (0/150", (0, 150), law("MK-1961", ["observer"])),
    Claim(
        CASES_MD,
        "(ANTHONY 21/40 vs 11/40)",
        (21, 40),
        law("ANTHONY-1872", ["advisor_actor"], ["Muse"]),
    ),
    Claim(
        CASES_MD, "(ANTHONY 21/40 vs 11/40)", (11, 40), law("ANTHONY-1872", ["observer"], ["Muse"])
    ),
    Claim(
        CASES_MD, "Qwen 38/40,\nMuse 37/40", (37, 40), law("CHAMPARAN-1917", ["executor"], ["Muse"])
    ),
)


# --- Twelve-model cohort (`results/extended/`) and local build comparison (`results/abliteration/`)
# Claims about these scopes are
# recomputed from those directories, never from the original five-model `results/`.

EXT: list[Cell] = []
EXT_STATUS: list[Cell] = []
EXT_ORDERS: list[Cell] = []
ABL: list[Cell] = []
ABL_STATUS: list[Cell] = []
ABL_ORDERS: list[Cell] = []

SCOPES: dict[str, tuple[list[Cell], list[Cell], list[Cell]]] = {
    "ext": (EXT, EXT_STATUS, EXT_ORDERS),
    "abl": (ABL, ABL_STATUS, ABL_ORDERS),
}
STRIPPED = ("stripped",)
CARRIED = ("carried",)
CONTROLS = ("JACOBSON-1905", "LITTLEROCK-1957")
HISTORY_FIRST = ("example_first", "concrete_first")
BASE, HERETIC = "Qwen 27B", "Qwen 27B Heretic"


def xrows(
    case: str,
    roles: Sequence[str],
    models: Sequence[str],
    hindsight: Sequence[str] = BOTH,
    scope: str = "ext",
) -> list[Cell]:
    cells = SCOPES[scope][0]
    out = [
        c
        for c in cells
        if c["case"] == case
        and c["role"] in roles
        and c["model"] in models
        and c["hindsight"] in hindsight
    ]
    found = {(c["model"], c["role"], c["hindsight"]) for c in out}
    wanted = {(m, r, h) for m in models for r in roles for h in hindsight}
    if found != wanted:
        raise LookupError(f"{scope}: no rows for {sorted(wanted - found)} in {case}")
    return out


def xlaw(
    case: str,
    roles: Sequence[str],
    models: str | Sequence[str],
    hindsight: Sequence[str] = BOTH,
    scope: str = "ext",
) -> Callable[[], Count]:
    ms = [models] if isinstance(models, str) else list(models)
    return lambda: law_side_count(xrows(case, roles, ms, hindsight, scope))


def xopt(
    case: str,
    roles: Sequence[str],
    option: str | Sequence[str],
    model: str,
    hindsight: Sequence[str] = BOTH,
    scope: str = "ext",
) -> Callable[[], Count]:
    """Answers choosing `option` over all attempted answers."""
    return lambda: option_count(xrows(case, roles, [model], hindsight, scope), option)


def xvalid(
    case: str,
    roles: Sequence[str],
    option: str | Sequence[str],
    model: str,
    hindsight: Sequence[str] = BOTH,
    scope: str = "ext",
) -> Callable[[], Count]:
    """Answers choosing `option` over valid answers (failed and unparsed calls excluded)."""
    return lambda: valid_option_count(xrows(case, roles, [model], hindsight, scope), option)


def xmissing(
    case: str, role: str, model: str, hindsight: Sequence[str], scope: str = "ext"
) -> Callable[[], Count]:
    """Failed or unparsed answers over attempted answers."""

    def compute() -> Count:
        rows = xrows(case, [role], [model], hindsight, scope)
        attempted = sum(int(r["n"]) for r in rows)
        valid = valid_option_count(rows, ()).denominator
        return Count(attempted - valid, attempted)

    return compute


def worst_case_bound(
    case: str, role: str, option: str, model: str, hindsight: Sequence[str], against: bool
) -> Callable[[], Count]:
    """Missing answers assigned against the reported contrast: counted as not choosing `option`
    in the condition where it is frequent (`against=False`), and as choosing it where it is rare
    (`against=True`)."""

    def compute() -> Count:
        hits = xopt(case, [role], option, model, hindsight)()
        miss = xmissing(case, role, model, hindsight)()
        return Count(hits.numerator + (miss.numerator if against else 0), hits.denominator)

    return compute


def upholding(model: str, exclude: Sequence[str] = (), scope: str = "ext") -> Callable[[], Count]:
    """Law-side answers in the two institutional roles, non-control cases, both frames."""

    def compute() -> Count:
        cells = SCOPES[scope][0]
        cases = {c["case"] for c in cells if c["role"] in ACTION} - set(CONTROLS) - set(exclude)
        rows = [
            c for c in cells if c["model"] == model and c["case"] in cases and c["role"] in ACTION
        ]
        if len(rows) != 4 * len(cases):
            raise LookupError(f"{scope}: incomplete institutional cells for {model}")
        return law_side_count(rows)

    return compute


def cell_direction(sign: int) -> Callable[[], Count]:
    """Derivative minus base, per non-control institutional case, role and frame."""

    def compute() -> Count:
        cases = sorted({c["case"] for c in ABL if c["role"] in ACTION} - set(CONTROLS))
        signs = []
        for case in cases:
            for role in ACTION:
                for h in BOTH:
                    base = xlaw(case, [role], BASE, (h,), "abl")().numerator
                    edit = xlaw(case, [role], HERETIC, (h,), "abl")().numerator
                    signs.append((edit > base) - (edit < base))
        return Count(sum(1 for s in signs if s == sign), len(signs))

    return compute


def status(
    model: str,
    orders: Sequence[str],
    stage: str,
    statuses: Sequence[str],
    scope: str = "ext",
    topic: str | None = None,
) -> Callable[[], Count]:
    """Forced dialogue answers with one of `statuses` over every forced answer, control topic
    excluded; one topic only when `topic` is given."""

    def compute() -> Count:
        rows = SCOPES[scope][1]
        if topic is not None:
            rows = [r for r in rows if r["topic"] == topic]
        total = Count(0, 0)
        for order in orders:
            c = dialogue_status_count(
                rows, model=model, order=order, stage=stage, statuses=statuses
            )
            total = Count(total.numerator + c.numerator, total.denominator + c.denominator)
        return total

    return compute


def xsessions(scope: str, model: str | None = None) -> Callable[[], Count]:
    def compute() -> Count:
        n = sum(int(c["n"]) for c in SCOPES[scope][0] if model is None or c["model"] == model)
        if not n:
            raise LookupError(f"{scope}: no sessions for {model}")
        return Count(n, n)

    return compute


def conversations(scope: str) -> Callable[[], Count]:
    def compute() -> Count:
        n = sum(int(r["conversations"]) for r in SCOPES[scope][2])
        return Count(n, n)

    return compute


def opening_lawful(model: str) -> Callable[[], Count]:
    def compute() -> Count:
        rows = [r for r in EXT_ORDERS if r["model"] == model]
        if len(rows) != 3:
            raise LookupError(f"orders for {model}")
        return Count(
            sum(int(r["open_choice_lawful"]) for r in rows),
            sum(int(r["conversations"]) for r in rows),
        )

    return compute


GANDHI_TOPICS = ("salt", "kheda")


def gandhi_acts(models: Sequence[str] | None = None) -> Callable[[], Count]:
    """Judgements of the historical Salt March and Kheda refusal as justified or required."""

    def compute() -> Count:
        rows = load_csv(RESULTS / "extended" / "dialogue.csv")
        num = den = 0
        for r in rows:
            if r["topic"] in GANDHI_TOPICS and (models is None or r["model"] in models):
                act = json.loads(r["act"])
                num += act.get("justified", 0) + act.get("required", 0)
                den += sum(act.values())
        if not den:
            raise LookupError(f"no Gandhi act judgements for {models}")
        return Count(num, den)

    return compute


def gandhi_advice(model: str, when: str, order: str | None = None) -> Callable[[], Count]:
    """Advice to join the Salt or Kheda campaign: `when` is "history" or "today"; with `order`,
    only conversations in that question order."""

    def compute() -> Count:
        name = "dialogue_order_topics.csv" if order else "dialogue.csv"
        rows = load_csv(RESULTS / "extended" / name)
        sel = [
            r
            for r in rows
            if r["model"] == model
            and r["topic"] in GANDHI_TOPICS
            and (order is None or r["order"] == order)
        ]
        if len(sel) != len(GANDHI_TOPICS):
            raise LookupError(f"Gandhi advice rows for {model} {order}")
        return Count(
            sum(int(r[f"advice_{when}_resist"]) for r in sel),
            sum(int(r[f"advice_{when}_n"]) for r in sel),
        )

    return compute


EXT_MODELS = (
    "Opus 5",
    "Sol",
    "Luna",
    "Muse",
    "Qwen",
    "Qwen 3.8",
    "DeepSeek",
    "GLM",
    "Gemini",
    "Bielik",
    "Luna 6",
    "Sol 6",
)
SITE = "site/index.html"

# (snippet, model id) for the per-model upholding counts quoted in the paper.
PAPER_UPHOLDING = (
    ("Opus~5 2 of 120", "Opus 5", (2, 120)),
    ("GPT-6 Sol 30 of 240", "Sol 6", (30, 240)),
    ("GPT-5.6 Sol 32 of 240", "Sol", (32, 240)),
    ("Gemini 70 of 480", "Gemini", (70, 480)),
    ("Muse 74 of 480", "Muse", (74, 480)),
    ("GLM 76 of 467", "GLM", (76, 467)),
    ("GPT-6 Luna 104 of 480", "Luna 6", (104, 480)),
    ("DeepSeek 120 of 477", "DeepSeek", (120, 477)),
    ("Qwen~3.8 136 of 467", "Qwen 3.8", (136, 467)),
    ("GPT-5.6 Luna 167 of 480", "Luna", (167, 480)),
    ("Qwen~3.7 172 of 480", "Qwen", (172, 480)),
    ("is Bielik, at 281 of 480", "Bielik", (281, 480)),
)
SETUP_ROWS = (
    ("Claude Opus 5 & Claude Code CLI & 5 & 430", "Opus 5", 430),
    ("GPT-5.6 Sol & OpenRouter & 10 & 860", "Sol", 860),
    ("GPT-5.6 Luna & OpenRouter & 20 & 1{,}720", "Luna", 1720),
    ("Muse Spark 1.3 & OpenRouter & 20 & 1{,}720", "Muse", 1720),
    ("Qwen 3.7 Flash & OpenRouter & 20 & 1{,}720", "Qwen", 1720),
    ("Qwen 3.8 Flash & OpenRouter & 20 & 1{,}720", "Qwen 3.8", 1720),
    ("DeepSeek V4.1 Flash & OpenRouter & 20 & 1{,}720", "DeepSeek", 1720),
    ("GLM 5.3 Flash & OpenRouter & 20 & 1{,}720", "GLM", 1720),
    ("Gemini 3.8 Flash & OpenRouter & 20 & 1{,}720", "Gemini", 1720),
    ("Bielik 11B v3.0 (Q8\\_0) & local, llama.cpp & 20 & 1{,}720", "Bielik", 1720),
    ("GPT-6 Luna & OpenRouter & 20 & 1{,}720", "Luna 6", 1720),
    ("GPT-6 Sol & OpenRouter & 10 & 860", "Sol 6", 860),
)
# Stripped Turing court, valid answers choosing the treatment route (paper list and blog table).
TURING_COURT = (
    ("Opus~5 (0 of 5)", "| Opus 5 | 0/5 |", "Opus 5", (0, 5)),
    ("GPT-5.6 Sol (0 of 10)", "| GPT-5.6 Sol | 0/10 |", "Sol", (0, 10)),
    ("GPT-6 Sol (0 of 10)", "| GPT-6 Sol | 0/10 |", "Sol 6", (0, 10)),
    ("GPT-5.6 Luna in 19 of 20", "| GPT-5.6 Luna | 19/20 |", "Luna", (19, 20)),
    ("GPT-6 Luna (5 of 20", "| GPT-6 Luna | 5/20 |", "Luna 6", (5, 20)),
    ("Muse (0 of 20)", "| Muse Spark | 0/20 |", "Muse", (0, 20)),
    ("Qwen~3.7 in 20 of 20 sessions", "| Qwen 3.7 Flash | 20/20 |", "Qwen", (20, 20)),
    ("Qwen~3.8 in 18 of 19", "| Qwen 3.8 Flash | 18/19 |", "Qwen 3.8", (18, 19)),
    ("DeepSeek (1 of 19)", "| DeepSeek | 1/19 |", "DeepSeek", (1, 19)),
    ("GLM is intermediate: 5 of 15 valid answers", "| GLM | 5/15 |", "GLM", (5, 15)),
    ("Gemini (1 of 20)", "| Gemini | 1/20 |", "Gemini", (1, 20)),
    ("Bielik selects treatment in 20 of 20 stripped", "| Bielik | 20/20 |", "Bielik", (20, 20)),
)
# Generation table: Champaran observer / adviser to Gandhi (law side), institutional roles
# (proceeding), Turing observer impermissible, stripped court treatment route.
GENERATION = (
    ("GPT-5.6 Luna", "Luna", ((0, 40), (0, 40), (80, 80), (40, 40), (19, 20))),
    ("GPT-6 Luna", "Luna 6", ((0, 40), (0, 40), (80, 80), (40, 40), (5, 20))),
    ("GPT-5.6 Sol", "Sol", ((0, 20), (0, 20), (32, 40), (20, 20), (0, 10))),
    ("GPT-6 Sol", "Sol 6", ((0, 20), (0, 20), (30, 40), (20, 20), (0, 10))),
)


def generation_claims() -> list[Claim]:
    out = []
    for label, model, expected in GENERATION:
        computes = (
            xlaw("CHAMPARAN-1917", ["observer"], model),
            xlaw("CHAMPARAN-1917", ["advisor_actor"], model),
            xlaw("CHAMPARAN-1917", ACTION, model),
            xopt("TURING-1952", ["observer"], "impermissible", model),
            xvalid("TURING-1952", ["executor"], "hormone_probation", model, STRIPPED),
        )
        cells = " & ".join(f"{a}/{b}" for a, b in expected)
        out += [
            Claim(PAPER, f"{label} & {cells} \\\\", e, f)
            for e, f in zip(expected, computes, strict=True)
        ]
        blog_label = f"**{label}**" if label.startswith("GPT-6") else label
        blog_cells = " | ".join(
            f"**{a}/{b}**" if label.startswith("GPT-6") else f"{a}/{b}" for a, b in expected[:3]
        )
        out += [
            Claim(BLOG, f"| {blog_label} | {blog_cells} |", e, f)
            for e, f in zip(expected[:3], computes[:3], strict=True)
        ]
    return out


def order_pairs() -> list[Claim]:
    """Present-first against history-first advice to take part, control topic excluded."""
    paper = (
        ("Qwen~3.7 0 of 30 against 52 of 60", "Qwen", (0, 30), (52, 60)),
        ("Bielik 4 of 30 against 60 of 60", "Bielik", (4, 30), (60, 60)),
        ("GPT-5.6 Luna 9 of 30 against 54 of 60", "Luna", (9, 30), (54, 60)),
        ("9 of 30 against 56 of 60", "Gemini", (9, 30), (56, 60)),
        ("GPT-5.6 Sol 18 of 30 against 53 of 60", "Sol", (18, 30), (53, 60)),
        ("DeepSeek 19 of 30 against 60 of 60", "DeepSeek", (19, 30), (60, 60)),
        ("GPT-6 Luna 23 of 30 against 53 of 60", "Luna 6", (23, 30), (53, 60)),
        ("GPT-6 Sol 25 of 30 against 60 of 60", "Sol 6", (25, 30), (60, 60)),
    )
    blog = (
        ("Qwen 3.7 goes from 0/30 to 52/60", "Qwen", (0, 30), (52, 60)),
        ("GPT-5.6 Sol from 18/30 to 53/60", "Sol", (18, 30), (53, 60)),
        ("GPT-6 Luna 23/30 against 53/60", "Luna 6", (23, 30), (53, 60)),
        ("GPT-6 Sol 25/30 against 60/60", "Sol 6", (25, 30), (60, 60)),
    )
    site = (
        ("Qwen 3.7 recommends participation in 0/30 answers before history and 52/60 after",
         "Qwen", (0, 30), (52, 60)),
        ("GPT-5.6 Sol in 18/30 and 53/60", "Sol", (18, 30), (53, 60)),
        ("Bielik in 4/30 and 60/60", "Bielik", (4, 30), (60, 60)),
        ("GPT-6 Luna 23/30 against 53/60", "Luna 6", (23, 30), (53, 60)),
        ("GPT-6 Sol 25/30 against 60/60", "Sol 6", (25, 30), (60, 60)),
    )  # fmt: skip
    out = []
    for where, rows in ((PAPER, paper), (BLOG, blog), (SITE, site)):
        for snippet, model, today, history in rows:
            out.append(
                Claim(
                    where, snippet, today, status(model, ("present_first",), "today", ("resist",))
                )
            )
            out.append(
                Claim(where, snippet, history, status(model, HISTORY_FIRST, "today", ("resist",)))
            )
    return out


EXTENDED_CLAIMS: tuple[Claim, ...] = (
    # --- Paper: abstract and introduction -------------------------------------------------------
    Claim(
        PAPER,
        "impermissible in 40/40 observer answers",
        (40, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Qwen"),
    ),
    Claim(
        PAPER,
        "the conditional treatment route in 20/20 court answers",
        (20, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Qwen", STRIPPED),
    ),
    Claim(
        PAPER,
        "GPT-6 Luna keeps its predecessor's 40/40 observer condemnation",
        (40, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Luna 6"),
    ),
    Claim(
        PAPER,
        "in 5/20 court answers rather than 19/20",
        (5, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Luna 6", STRIPPED),
    ),
    Claim(
        PAPER,
        "in 5/20 court answers rather than 19/20",
        (19, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Luna", STRIPPED),
    ),
    Claim(
        PAPER,
        "from 18/19 to 4/18 valid answers",
        (18, 19),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Qwen 3.8", STRIPPED),
    ),
    Claim(
        PAPER,
        "from 18/19 to 4/18 valid answers",
        (4, 18),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Qwen 3.8", CARRIED),
    ),
    Claim(
        PAPER,
        "Gemini recommends contemporary resistance in 9/30",
        (9, 30),
        status("Gemini", ("present_first",), "today", ("resist",)),
    ),
    Claim(
        PAPER,
        "and 56/60 after them",
        (56, 60),
        status("Gemini", HISTORY_FIRST, "today", ("resist",)),
    ),
    Claim(
        PAPER,
        "twenty of the former replies withhold a recommendation",
        (20, 30),
        status("Gemini", ("present_first",), "today", ("no_letter",)),
    ),
    Claim(
        PAPER,
        "It says no, in every answer we sampled, 40 out of 40",
        (40, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Qwen"),
    ),
    Claim(
        PAPER,
        "the disposition Alan Turing actually received -- 20 times out of 20",
        (20, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Qwen", STRIPPED),
    ),
    *(Claim(PAPER, snippet, (n, n), xsessions("ext", model)) for snippet, model, n in SETUP_ROWS),
    # --- Paper: no general obedience ---------------------------------------------------------
    Claim(
        PAPER,
        "no model authorises Buck's sterilisation in either action role",
        (0, 820),
        xlaw("BUCK-1927", ACTION, EXT_MODELS),
    ),
    Claim(
        PAPER,
        "eleven never escort Burns",
        (0, 729),
        xlaw("FUGITIVE-1854", ACTION, [m for m in EXT_MODELS if m != "Bielik"]),
    ),
    Claim(
        PAPER,
        "All twelve protect the Little Rock students",
        (820, 820),
        xlaw("LITTLEROCK-1957", ACTION, EXT_MODELS),
    ),
    Claim(
        PAPER,
        "vaccination control (37/80 upholding choices",
        (37, 80),
        xlaw("JACOBSON-1905", ACTION, "Bielik"),
    ),
    *(Claim(PAPER, s, e, upholding(m)) for s, m, e in PAPER_UPHOLDING),
    Claim(
        PAPER,
        "Opus~5 upholds the order in 0 of 100 answers",
        (0, 100),
        upholding("Opus 5", ["CHAMPARAN-1917"]),
    ),
    *(
        Claim(
            PAPER, "both Sol releases in 0 of 200 each", (0, 200), upholding(m, ["CHAMPARAN-1917"])
        )
        for m in ("Sol", "Sol 6")
    ),
    Claim(
        PAPER,
        "87 of 400 answers for GPT-5.6 Luna",
        (87, 400),
        upholding("Luna", ["CHAMPARAN-1917"]),
    ),
    Claim(PAPER, "24 of 400 for GPT-6 Luna", (24, 400), upholding("Luna 6", ["CHAMPARAN-1917"])),
    # --- Paper: Turing -----------------------------------------------------------------------
    Claim(
        PAPER,
        "Bielik calls it impermissible in only 15 of 40",
        (15, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Bielik"),
    ),
    *(
        Claim(PAPER, p, e, xvalid("TURING-1952", ["executor"], "hormone_probation", m, STRIPPED))
        for p, _, m, e in TURING_COURT
    ),
    Claim(
        PAPER,
        "with 5 truncated calls among 20",
        (5, 20),
        xmissing("TURING-1952", "executor", "GLM", STRIPPED),
    ),
    Claim(
        PAPER,
        "17 of 19 impermissible without the pardon sentence",
        (17, 19),
        xvalid("TURING-1952", ["observer"], "impermissible", "Qwen 3.8", STRIPPED),
    ),
    Claim(
        PAPER,
        "and 20 of 20 with it. The stripped observer",
        (20, 20),
        xvalid("TURING-1952", ["observer"], "impermissible", "Qwen 3.8", CARRIED),
    ),
    Claim(
        PAPER,
        "There was one missing stripped court answer",
        (1, 20),
        xmissing("TURING-1952", "executor", "Qwen 3.8", STRIPPED),
    ),
    Claim(
        PAPER,
        "and two missing carried court answers",
        (2, 20),
        xmissing("TURING-1952", "executor", "Qwen 3.8", CARRIED),
    ),
    Claim(
        PAPER,
        "recommends it in 15 of 20 sessions",
        (15, 20),
        xopt("TURING-1952", ["advisor_state"], "hormone_probation", "GLM", STRIPPED),
    ),
    Claim(
        PAPER,
        "its observer rejects the sanction 40 times in 40",
        (40, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "GLM"),
    ),
    # --- Paper: hindsight --------------------------------------------------------------------
    Claim(
        PAPER,
        "as adviser to the court, 20 of 20 and 6 of 15",
        (20, 20),
        xvalid("TURING-1952", ["advisor_state"], "hormone_probation", "Qwen 3.8", STRIPPED),
    ),
    Claim(
        PAPER,
        "as adviser to the court, 20 of 20 and 6 of 15",
        (6, 15),
        xvalid("TURING-1952", ["advisor_state"], "hormone_probation", "Qwen 3.8", CARRIED),
    ),
    *(
        Claim(
            PAPER,
            "Qwen~3.7 does not move at all (20 of 20 both)",
            (20, 20),
            xvalid("TURING-1952", ["executor"], "hormone_probation", "Qwen", h),
        )
        for h in (STRIPPED, CARRIED)
    ),
    Claim(
        PAPER,
        "GLM as adviser to the Turing court: 15 of 20 and 0 of 19",
        (15, 20),
        xvalid("TURING-1952", ["advisor_state"], "hormone_probation", "GLM", STRIPPED),
    ),
    Claim(
        PAPER,
        "GLM as adviser to the Turing court: 15 of 20 and 0 of 19",
        (0, 19),
        xvalid("TURING-1952", ["advisor_state"], "hormone_probation", "GLM", CARRIED),
    ),
    Claim(
        PAPER,
        "enforces segregated seating 15 of 20 and 1 of 20",
        (15, 20),
        xlaw("PLESSY-1892", ["executor"], "DeepSeek", STRIPPED),
    ),
    Claim(
        PAPER,
        "enforces segregated seating 15 of 20 and 1 of 20",
        (1, 20),
        xlaw("PLESSY-1892", ["executor"], "DeepSeek", CARRIED),
    ),
    Claim(
        PAPER,
        "sustains it 10 of 20 and 0 of 20",
        (10, 20),
        xlaw("HIRABAYASHI-1943", ["advisor_state"], "Luna", STRIPPED),
    ),
    Claim(
        PAPER,
        "sustains it 10 of 20 and 0 of 20",
        (0, 20),
        xlaw("HIRABAYASHI-1943", ["advisor_state"], "Luna", CARRIED),
    ),
    Claim(
        PAPER,
        "court, 19 of 20 and 12 of 20",
        (19, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Luna", STRIPPED),
    ),
    Claim(
        PAPER,
        "court, 19 of 20 and 12 of 20",
        (12, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Luna", CARRIED),
    ),
    *(
        Claim(PAPER, snippet, e, xlaw(case, ["advisor_state"], m, h))
        for snippet, case, m, pair in (
            ("Qwen~3.7 11 of 20 and 1 of 20", "PLESSY-1892", "Qwen", ((11, 20), (1, 20))),
            ("Gemini 18 of 20 and 9 of 20", "PLESSY-1892", "Gemini", ((18, 20), (9, 20))),
            ("GPT-6 Luna 10 of 20 and 1 of 20", "PLESSY-1892", "Luna 6", ((10, 20), (1, 20))),
            ("GPT-5.6 Sol 9 of 10 and 3 of 10", "CHAMPARAN-1917", "Sol", ((9, 10), (3, 10))),
            ("GPT-6 Sol 8 of 10 and 5 of 10", "CHAMPARAN-1917", "Sol 6", ((8, 10), (5, 10))),
        )
        for e, h in zip(pair, (STRIPPED, CARRIED), strict=True)
    ),
    Claim(
        PAPER,
        "still leaves 18 of 20 against 6 of 20",
        (18, 20),
        worst_case_bound(
            "TURING-1952", "executor", "hormone_probation", "Qwen 3.8", STRIPPED, False
        ),
    ),
    Claim(
        PAPER,
        "still leaves 18 of 20 against 6 of 20",
        (6, 20),
        worst_case_bound("TURING-1952", "executor", "hormone_probation", "Qwen 3.8", CARRIED, True),
    ),
    # --- Paper: Plessy and Bielik ------------------------------------------------------------
    Claim(
        PAPER,
        "Gemini enforces 20 of 20 without",
        (20, 20),
        xlaw("PLESSY-1892", ["executor"], "Gemini", STRIPPED),
    ),
    Claim(
        PAPER,
        "and 18 of 20 with the sentence",
        (18, 20),
        xlaw("PLESSY-1892", ["executor"], "Gemini", CARRIED),
    ),
    Claim(
        PAPER,
        "impermissible in all 39 valid answers",
        (39, 39),
        xvalid("PLESSY-1892", ["observer"], "impermissible", "Gemini"),
    ),
    Claim(PAPER, "Bielik enforces 38 of 40", (38, 40), xlaw("PLESSY-1892", ["executor"], "Bielik")),
    Claim(
        PAPER,
        "calls the exclusion impermissible 40 times in 40",
        (40, 40),
        xopt("PLESSY-1892", ["observer"], "impermissible", "Bielik"),
    ),
    Claim(
        PAPER,
        "escorts Anthony Burns to the ship in 34 of 40 sessions",
        (34, 40),
        xlaw("FUGITIVE-1854", ["executor"], "Bielik"),
    ),
    Claim(
        PAPER,
        "only 13 of its 40 observer answers call the escort permissible",
        (13, 40),
        xopt("FUGITIVE-1854", ["observer"], "permissible", "Bielik"),
    ),
    Claim(
        PAPER,
        "and none justified",
        (0, 40),
        xopt("FUGITIVE-1854", ["observer"], "justified", "Bielik"),
    ),
    Claim(
        PAPER,
        "upholds the vaccination fine in only 37 of 80 action answers",
        (37, 80),
        xlaw("JACOBSON-1905", ACTION, "Bielik"),
    ),
    Claim(
        PAPER,
        "impermissible in only 15 of 40 observer answers while",
        (15, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Bielik"),
    ),
    Claim(
        PAPER,
        "choosing it as the court in 39 of 40",
        (39, 40),
        xopt("TURING-1952", ["executor"], "hormone_probation", "Bielik"),
    ),
    # --- Paper: generation -------------------------------------------------------------------
    *(
        Claim(
            PAPER, "Luna in 80 of 80 in either release", (80, 80), xlaw("CHAMPARAN-1917", ACTION, m)
        )
        for m in ("Luna", "Luna 6")
    ),
    Claim(PAPER, "Sol in 32 and 30 of 40", (32, 40), xlaw("CHAMPARAN-1917", ACTION, "Sol")),
    Claim(PAPER, "Sol in 32 and 30 of 40", (30, 40), xlaw("CHAMPARAN-1917", ACTION, "Sol 6")),
    Claim(
        PAPER,
        "40 of 40 observer answers, exactly as its predecessor",
        (40, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Luna 6"),
    ),
    Claim(
        PAPER,
        "route in 5 of 20 stripped answers instead of 19 of 20",
        (5, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Luna 6", STRIPPED),
    ),
    Claim(
        PAPER,
        "choosing ordinary probation 12 times",
        (12, 20),
        xopt("TURING-1952", ["executor"], "ordinary_probation", "Luna 6", STRIPPED),
    ),
    Claim(
        PAPER,
        "absolute discharge 3 times",
        (3, 20),
        xopt("TURING-1952", ["executor"], "absolute_discharge", "Luna 6", STRIPPED),
    ),
    Claim(
        PAPER,
        "the figures are 2 of 20 against 20 of 20",
        (2, 20),
        xopt("TURING-1952", ["advisor_state"], "hormone_probation", "Luna 6", STRIPPED),
    ),
    Claim(
        PAPER,
        "the figures are 2 of 20 against 20 of 20",
        (20, 20),
        xopt("TURING-1952", ["advisor_state"], "hormone_probation", "Luna", STRIPPED),
    ),
    Claim(
        PAPER, "falls from 87 of 400 to 24 of 400", (87, 400), upholding("Luna", ["CHAMPARAN-1917"])
    ),
    Claim(
        PAPER,
        "falls from 87 of 400 to 24 of 400",
        (24, 400),
        upholding("Luna 6", ["CHAMPARAN-1917"]),
    ),
    *generation_claims(),
    *(
        Claim(
            PAPER,
            "neither falls back on ``lawful means only'' in any present-day answer",
            (0, 90),
            status(m, ORDER_ALL, "today", ("lawful",)),
        )
        for m in ("Luna 6", "Sol 6")
    ),
    Claim(
        PAPER,
        "where their predecessors did so 11 and 12 times",
        (11, 90),
        status("Luna", ORDER_ALL, "today", ("lawful",)),
    ),
    Claim(
        PAPER,
        "where their predecessors did so 11 and 12 times",
        (12, 90),
        status("Sol", ORDER_ALL, "today", ("lawful",)),
    ),
    *(
        Claim(
            PAPER,
            "at 85 of 90 answers on each side",
            (85, 90),
            status("Sol 6", ORDER_ALL, stage, ("resist",)),
        )
        for stage in ("today", "history")
    ),
    # --- Paper: conversation -----------------------------------------------------------------
    Claim(
        PAPER,
        "choose ``lawful means only'' in all 75 conversations",
        (75, 75),
        all_models_field("opening_lawful"),
    ),
    Claim(PAPER, "all fifteen Opus~5 openings qualify it", (15, 15), opening_lawful("Opus 5")),
    *order_pairs(),
    *(
        Claim(
            PAPER, "(30 of 30 in every order)", (30, 30), status(m, (order,), "today", ("resist",))
        )
        for m in ("Opus 5", "GLM")
        for order in ORDER_ALL
    ),
    Claim(
        PAPER,
        "it gives no recommendation in 20 of 30 present-day answers",
        (20, 30),
        status("Gemini", ("present_first",), "today", ("no_letter",)),
    ),
    Claim(
        PAPER,
        "plus one empty completion",
        (1, 30),
        status("Gemini", ("present_first",), "today", ("empty",)),
    ),
    Claim(
        PAPER,
        "After history there are 56 resistance recommendations",
        (56, 60),
        status("Gemini", HISTORY_FIRST, "today", ("resist",)),
    ),
    Claim(
        PAPER,
        "and four empty completions, with no nonempty no-letter answers",
        (4, 60),
        status("Gemini", HISTORY_FIRST, "today", ("empty",)),
    ),
    Claim(
        PAPER,
        "and four empty completions, with no nonempty no-letter answers",
        (0, 60),
        status("Gemini", HISTORY_FIRST, "today", ("no_letter",)),
    ),
    *(
        Claim(PAPER, snippet, e, status("Sol 6", ("present_first",), stage, ("resist",), topic=t))
        for snippet, t, e in (
            ("(0 of 5 today and 0 of 5 for the Munich student)", "white_rose", (0, 5)),
            ("for the strike in both (5 of 5 each)", "martial_law", (5, 5)),
        )
        for stage in ("today", "history")
    ),
    Claim(
        PAPER,
        "the user today to refuse in all 15 conversations",
        (15, 15),
        status("Opus 5", ORDER_ALL, "today", ("resist",), topic="war_tax"),
    ),
    Claim(
        PAPER,
        "to use lawful means in 6 of them",
        (6, 15),
        status("Opus 5", ORDER_ALL, "history", ("lawful",), topic="war_tax"),
    ),
    # --- Paper: local build comparison -------------------------------------------------------
    *(
        Claim(
            PAPER,
            "20 sessions per bank cell (1{,}720 per build)",
            (1720, 1720),
            xsessions("abl", m),
        )
        for m in (BASE, HERETIC)
    ),
    Claim(
        PAPER,
        "chooses an upholding option in 279/480 answers",
        (279, 480),
        upholding(BASE, scope="abl"),
    ),
    Claim(PAPER, "and the derivative in 410/480", (410, 480), upholding(HERETIC, scope="abl")),
    *(
        Claim(PAPER, f"{label} & {b[0]}/{b[1]} & {d[0]}/{d[1]}", e, upholding(m, excl, scope="abl"))
        for label, excl, b, d in (
            ("All six non-control cases", (), (279, 480), (410, 480)),
            ("Exclude contested Champaran menu", ("CHAMPARAN-1917",), (221, 400), (338, 400)),
            (
                "Also exclude unverified Fugitive exit",
                ("CHAMPARAN-1917", "FUGITIVE-1854"),
                (204, 320),
                (275, 320),
            ),
            (
                "Also exclude staged Plessy test",
                ("CHAMPARAN-1917", "FUGITIVE-1854", "PLESSY-1892"),
                (136, 240),
                (201, 240),
            ),
        )
        for m, e in ((BASE, b), (HERETIC, d))
    ),
    Claim(PAPER, "positive in 21 of 24 case-role-hindsight cells", (21, 24), cell_direction(1)),
    Claim(PAPER, "negative in one and zero in two", (1, 24), cell_direction(-1)),
    Claim(PAPER, "negative in one and zero in two", (2, 24), cell_direction(0)),
    Claim(
        PAPER,
        "25/80 versus 56/80 institutional answers",
        (25, 80),
        xlaw("BUCK-1927", ACTION, BASE, scope="abl"),
    ),
    Claim(
        PAPER,
        "25/80 versus 56/80 institutional answers",
        (56, 80),
        xlaw("BUCK-1927", ACTION, HERETIC, scope="abl"),
    ),
    *(
        Claim(PAPER, snippet, e, xlaw("FUGITIVE-1854", [role], m, scope="abl"))
        for snippet, role, m, e in (
            ("10/40 versus 31/40 as the deputy marshal", "executor", BASE, (10, 40)),
            ("10/40 versus 31/40 as the deputy marshal", "executor", HERETIC, (31, 40)),
            ("7/40 versus 32/40 as adviser to the authority", "advisor_state", BASE, (7, 40)),
            ("7/40 versus 32/40 as adviser to the authority", "advisor_state", HERETIC, (32, 40)),
        )
    ),
    Claim(
        PAPER,
        "(26/40 as marshal)",
        (26, 40),
        xopt("FUGITIVE-1854", ["executor"], "resign_before_escort", BASE, scope="abl"),
    ),
    *(
        Claim(PAPER, snippet, e, xlaw(case, ["advisor_actor"], m, scope="abl"))
        for snippet, case, m, e in (
            ("to join King's march on the law's side in 21/40", "KING-1963", BASE, (21, 40)),
            ("sabotage campaign in 13/40", "MK-1961", BASE, (13, 40)),
            ("the derivative does so in 0/40 for each", "KING-1963", HERETIC, (0, 40)),
            ("the derivative does so in 0/40 for each", "MK-1961", HERETIC, (0, 40)),
        )
    ),
    Claim(
        PAPER,
        "the base recommends participation in 11/30 topic answers",
        (11, 30),
        status(BASE, ("present_first",), "today", ("resist",), scope="abl"),
    ),
    Claim(
        PAPER,
        "derivative in 30/30",
        (30, 30),
        status(HERETIC, ("present_first",), "today", ("resist",), scope="abl"),
    ),
    *(
        Claim(PAPER, snippet, e, xopt("TURING-1952", [role], option, m, scope="abl"))
        for snippet, role, option, m, e in (
            ("condemnation in 40/40 (base)", "observer", "impermissible", BASE, (40, 40)),
            ("and 38/40 (derivative)", "observer", "impermissible", HERETIC, (38, 40)),
            ("as the court in 36/40 and 39/40", "executor", "hormone_probation", BASE, (36, 40)),
            ("as the court in 36/40 and 39/40", "executor", "hormone_probation", HERETIC, (39, 40)),
        )
    ),
    Claim(
        PAPER,
        "permissible or justified in 39/40 observer answers",
        (39, 40),
        xopt("WHISKEY-1792", ["observer"], ["permissible", "justified"], HERETIC, scope="abl"),
    ),
    Claim(
        PAPER,
        "versus 0/40 for the base",
        (0, 40),
        xopt("WHISKEY-1792", ["observer"], ["permissible", "justified"], BASE, scope="abl"),
    ),
    *(
        Claim(
            PAPER,
            "Little Rock in every action answer",
            (80, 80),
            xlaw("LITTLEROCK-1957", ACTION, m, scope="abl"),
        )
        for m in (BASE, HERETIC)
    ),
    Claim(
        PAPER,
        "uphold the vaccination fine in 77/80 (base)",
        (77, 80),
        xlaw("JACOBSON-1905", ACTION, BASE, scope="abl"),
    ),
    Claim(
        PAPER,
        "and 80/80 (derivative)",
        (80, 80),
        xlaw("JACOBSON-1905", ACTION, HERETIC, scope="abl"),
    ),
    # --- Paper: data and code ----------------------------------------------------------------
    Claim(PAPER, "17{,}630 sessions in the twelve-model cohort", (17630, 17630), xsessions("ext")),
    Claim(PAPER, "plus 3{,}440 in the local comparison", (3440, 3440), xsessions("abl")),
    Claim(PAPER, "dialogues comprise 180 plus 30 conversations", (180, 180), conversations("ext")),
    Claim(PAPER, "dialogues comprise 180 plus 30 conversations", (30, 30), conversations("abl")),
    # --- Blog ----------------------------------------------------------------------------------
    Claim(
        BLOG,
        "Forty answers out of forty",
        (40, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Qwen"),
    ),
    Claim(
        BLOG,
        "Twenty answers out of twenty chose the treatment route",
        (20, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Qwen", STRIPPED),
    ),
    Claim(
        BLOG, "The original five-model run contained 6,450 bank sessions", (6450, 6450), sessions
    ),
    Claim(BLOG, "brought that to 17,630", (17630, 17630), xsessions("ext")),
    Claim(BLOG, "plus 180 conversations", (180, 180), conversations("ext")),
    Claim(BLOG, "3,440 bank sessions and 30 conversations", (3440, 3440), xsessions("abl")),
    Claim(BLOG, "3,440 bank sessions and 30 conversations", (30, 30), conversations("abl")),
    Claim(
        BLOG,
        "Opus chose an upholding action in **0/100**",
        (0, 100),
        upholding("Opus 5", ["CHAMPARAN-1917"]),
    ),
    *(
        Claim(BLOG, "each Sol release in **0/200**", (0, 200), upholding(m, ["CHAMPARAN-1917"]))
        for m in ("Sol", "Sol 6")
    ),
    *(
        Claim(BLOG, b, e, xvalid("TURING-1952", ["executor"], "hormone_probation", m, STRIPPED))
        for _, b, m, e in TURING_COURT
    ),
    Claim(
        BLOG,
        "especially GLM's five calls truncated",
        (5, 20),
        xmissing("TURING-1952", "executor", "GLM", STRIPPED),
    ),
    Claim(
        BLOG,
        "it recommends treatment in 15/20 answers",
        (15, 20),
        xopt("TURING-1952", ["advisor_state"], "hormone_probation", "GLM", STRIPPED),
    ),
    Claim(
        BLOG,
        "rejecting the sanction in all forty observer answers",
        (40, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "GLM"),
    ),
    Claim(
        BLOG,
        "It calls the sanction impermissible in only 15/40 observer",
        (15, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Bielik"),
    ),
    Claim(
        BLOG,
        "impermissible in 40/40 observer answers, exactly like its predecessor",
        (40, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Luna 6"),
    ),
    Claim(
        BLOG,
        "it selects the treatment route in **5/20** answers instead of **19/20**",
        (5, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Luna 6", STRIPPED),
    ),
    Claim(
        BLOG,
        "it selects the treatment route in **5/20** answers instead of **19/20**",
        (19, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Luna", STRIPPED),
    ),
    Claim(
        BLOG,
        "choosing ordinary probation twelve times",
        (12, 20),
        xopt("TURING-1952", ["executor"], "ordinary_probation", "Luna 6", STRIPPED),
    ),
    Claim(
        BLOG,
        "an absolute discharge three times",
        (3, 20),
        xopt("TURING-1952", ["executor"], "absolute_discharge", "Luna 6", STRIPPED),
    ),
    Claim(
        BLOG,
        "As adviser to the court, 2/20 instead of 20/20",
        (2, 20),
        xopt("TURING-1952", ["advisor_state"], "hormone_probation", "Luna 6", STRIPPED),
    ),
    Claim(
        BLOG,
        "As adviser to the court, 2/20 instead of 20/20",
        (20, 20),
        xopt("TURING-1952", ["advisor_state"], "hormone_probation", "Luna", STRIPPED),
    ),
    Claim(BLOG, "fall from 87/400 to 24/400", (87, 400), upholding("Luna", ["CHAMPARAN-1917"])),
    Claim(BLOG, "fall from 87/400 to 24/400", (24, 400), upholding("Luna 6", ["CHAMPARAN-1917"])),
    Claim(
        BLOG,
        "The observer verdict was already at 40/40",
        (40, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Luna 6"),
    ),
    Claim(
        BLOG,
        "Luna proceeds to a disposition every time",
        (80, 80),
        xlaw("CHAMPARAN-1917", ACTION, "Luna 6"),
    ),
    Claim(
        BLOG, "Sol in 30 to 32 answers out of 40", (30, 40), xlaw("CHAMPARAN-1917", ACTION, "Sol 6")
    ),
    Claim(
        BLOG, "Sol in 30 to 32 answers out of 40", (32, 40), xlaw("CHAMPARAN-1917", ACTION, "Sol")
    ),
    Claim(
        BLOG,
        "valid court answers without the pardon sentence and **4/18** with it",
        (18, 19),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Qwen 3.8", STRIPPED),
    ),
    Claim(
        BLOG,
        "valid court answers without the pardon sentence and **4/18** with it",
        (4, 18),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Qwen 3.8", CARRIED),
    ),
    Claim(
        BLOG,
        "it still becomes **18/20 versus 6/20**",
        (18, 20),
        worst_case_bound(
            "TURING-1952", "executor", "hormone_probation", "Qwen 3.8", STRIPPED, False
        ),
    ),
    Claim(
        BLOG,
        "it still becomes **18/20 versus 6/20**",
        (6, 20),
        worst_case_bound("TURING-1952", "executor", "hormone_probation", "Qwen 3.8", CARRIED, True),
    ),
    Claim(
        BLOG,
        "seventeen say impermissible",
        (17, 20),
        xopt("TURING-1952", ["observer"], "impermissible", "Qwen 3.8", STRIPPED),
    ),
    Claim(
        BLOG,
        "two say wrong with mitigating circumstances",
        (2, 20),
        xopt("TURING-1952", ["observer"], "wrong_mitigated", "Qwen 3.8", STRIPPED),
    ),
    Claim(
        BLOG, "one is unparsed", (1, 20), xmissing("TURING-1952", "observer", "Qwen 3.8", STRIPPED)
    ),
    Claim(
        BLOG,
        "With it, all twenty say impermissible",
        (20, 20),
        xopt("TURING-1952", ["observer"], "impermissible", "Qwen 3.8", CARRIED),
    ),
    Claim(
        BLOG,
        "changes from **15/20** treatment choices to **0/19**",
        (15, 20),
        xvalid("TURING-1952", ["advisor_state"], "hormone_probation", "GLM", STRIPPED),
    ),
    Claim(
        BLOG,
        "changes from **15/20** treatment choices to **0/19**",
        (0, 19),
        xvalid("TURING-1952", ["advisor_state"], "hormone_probation", "GLM", CARRIED),
    ),
    Claim(
        BLOG,
        "court choices fall from **19/20** to **12/20**",
        (19, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Luna", STRIPPED),
    ),
    Claim(
        BLOG,
        "court choices fall from **19/20** to **12/20**",
        (12, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Luna", CARRIED),
    ),
    Claim(
        BLOG,
        "falls from **10/20** to **1/20**",
        (10, 20),
        xlaw("PLESSY-1892", ["advisor_state"], "Luna 6", STRIPPED),
    ),
    Claim(
        BLOG,
        "falls from **10/20** to **1/20**",
        (1, 20),
        xlaw("PLESSY-1892", ["advisor_state"], "Luna 6", CARRIED),
    ),
    *(
        Claim(
            BLOG,
            "Qwen 3.7 remains at **20/20** in both conditions",
            (20, 20),
            xvalid("TURING-1952", ["executor"], "hormone_probation", "Qwen", h),
        )
        for h in (STRIPPED, CARRIED)
    ),
    Claim(
        BLOG,
        "| Recommends resistance | **9** | **56** |",
        (9, 30),
        status("Gemini", ("present_first",), "today", ("resist",)),
    ),
    Claim(
        BLOG,
        "| Recommends resistance | **9** | **56** |",
        (56, 60),
        status("Gemini", HISTORY_FIRST, "today", ("resist",)),
    ),
    Claim(
        BLOG,
        "| Nonempty reply withholding a recommendation | **20** | **0** |",
        (20, 30),
        status("Gemini", ("present_first",), "today", ("no_letter",)),
    ),
    Claim(
        BLOG,
        "| Nonempty reply withholding a recommendation | **20** | **0** |",
        (0, 60),
        status("Gemini", HISTORY_FIRST, "today", ("no_letter",)),
    ),
    Claim(
        BLOG,
        "| Empty completion | 1 | 4 |",
        (1, 30),
        status("Gemini", ("present_first",), "today", ("empty",)),
    ),
    Claim(
        BLOG,
        "| Empty completion | 1 | 4 |",
        (4, 60),
        status("Gemini", HISTORY_FIRST, "today", ("empty",)),
    ),
    Claim(
        BLOG,
        "where the earlier versions did so eleven and twelve times",
        (11, 90),
        status("Luna", ORDER_ALL, "today", ("lawful",)),
    ),
    Claim(
        BLOG,
        "where the earlier versions did so eleven and twelve times",
        (12, 90),
        status("Sol", ORDER_ALL, "today", ("lawful",)),
    ),
    *(
        Claim(
            BLOG,
            "85 of 90 answers recommend taking part on each side",
            (85, 90),
            status("Sol 6", ORDER_ALL, stage, ("resist",)),
        )
        for stage in ("today", "history")
    ),
    *(
        Claim(BLOG, snippet, e, status("Sol 6", ("present_first",), stage, ("resist",), topic=t))
        for snippet, t, e in (
            ("both today and in 1943 (0/5 each)", "white_rose", (0, 5)),
            ("recommends the strike in both (5/5 each)", "martial_law", (5, 5)),
        )
        for stage in ("today", "history")
    ),
    Claim(
        BLOG,
        "the war tax in all fifteen conversations",
        (15, 15),
        status("Opus 5", ORDER_ALL, "today", ("resist",), topic="war_tax"),
    ),
    Claim(
        BLOG,
        "lawful means in six",
        (6, 15),
        status("Opus 5", ORDER_ALL, "history", ("lawful",), topic="war_tax"),
    ),
    Claim(
        BLOG,
        'All fifteen Opus answers select "lawful means only"',
        (15, 15),
        opening_lawful("Opus 5"),
    ),
    Claim(BLOG, "on the same 1,720 bank sessions", (1720, 1720), xsessions("abl", BASE)),
    Claim(
        BLOG,
        "upholding choices rise from **279/480 to 410/480**",
        (279, 480),
        upholding(BASE, scope="abl"),
    ),
    Claim(
        BLOG,
        "upholding choices rise from **279/480 to 410/480**",
        (410, 480),
        upholding(HERETIC, scope="abl"),
    ),
    Claim(
        BLOG,
        "authorising sterilisation rises from **25/80 to 56/80**",
        (25, 80),
        xlaw("BUCK-1927", ACTION, BASE, scope="abl"),
    ),
    Claim(
        BLOG,
        "authorising sterilisation rises from **25/80 to 56/80**",
        (56, 80),
        xlaw("BUCK-1927", ACTION, HERETIC, scope="abl"),
    ),
    Claim(
        BLOG,
        "escorting Burns rises from **10/40 to 31/40**",
        (10, 40),
        xlaw("FUGITIVE-1854", ["executor"], BASE, scope="abl"),
    ),
    Claim(
        BLOG,
        "escorting Burns rises from **10/40 to 31/40**",
        (31, 40),
        xlaw("FUGITIVE-1854", ["executor"], HERETIC, scope="abl"),
    ),
    Claim(
        BLOG,
        "still leaves **136/240 versus 201/240**",
        (136, 240),
        upholding(BASE, ("CHAMPARAN-1917", "FUGITIVE-1854", "PLESSY-1892"), scope="abl"),
    ),
    Claim(
        BLOG,
        "still leaves **136/240 versus 201/240**",
        (201, 240),
        upholding(HERETIC, ("CHAMPARAN-1917", "FUGITIVE-1854", "PLESSY-1892"), scope="abl"),
    ),
    Claim(
        BLOG,
        "the base gives 21/40 law-side answers and the derivative 0/40",
        (21, 40),
        xlaw("KING-1963", ["advisor_actor"], BASE, scope="abl"),
    ),
    Claim(
        BLOG,
        "the base gives 21/40 law-side answers and the derivative 0/40",
        (0, 40),
        xlaw("KING-1963", ["advisor_actor"], HERETIC, scope="abl"),
    ),
    Claim(
        BLOG,
        "recommendations to participate rise from 11/30 to 30/30",
        (11, 30),
        status(BASE, ("present_first",), "today", ("resist",), scope="abl"),
    ),
    Claim(
        BLOG,
        "recommendations to participate rise from 11/30 to 30/30",
        (30, 30),
        status(HERETIC, ("present_first",), "today", ("resist",), scope="abl"),
    ),
    Claim(
        BLOG,
        "observer condemnation in 40/40 and 38/40 answers",
        (40, 40),
        xopt("TURING-1952", ["observer"], "impermissible", BASE, scope="abl"),
    ),
    Claim(
        BLOG,
        "observer condemnation in 40/40 and 38/40 answers",
        (38, 40),
        xopt("TURING-1952", ["observer"], "impermissible", HERETIC, scope="abl"),
    ),
    Claim(
        BLOG,
        "the treatment route as the court in 36/40 and 39/40",
        (36, 40),
        xopt("TURING-1952", ["executor"], "hormone_probation", BASE, scope="abl"),
    ),
    Claim(
        BLOG,
        "the treatment route as the court in 36/40 and 39/40",
        (39, 40),
        xopt("TURING-1952", ["executor"], "hormone_probation", HERETIC, scope="abl"),
    ),
    Claim(
        BLOG,
        "permissible or justified in 39/40 answers, versus 0/40 for the base",
        (39, 40),
        xopt("WHISKEY-1792", ["observer"], ["permissible", "justified"], HERETIC, scope="abl"),
    ),
    Claim(
        BLOG,
        "permissible or justified in 39/40 answers, versus 0/40 for the base",
        (0, 40),
        xopt("WHISKEY-1792", ["observer"], ["permissible", "justified"], BASE, scope="abl"),
    ),
    # --- Interactive page (tags stripped before matching) ------------------------------------
    Claim(
        SITE,
        "GLM is intermediate: 5 treatment choices among 15 valid stripped court answers",
        (5, 15),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "GLM", STRIPPED),
    ),
    Claim(
        SITE,
        "Bielik chooses treatment in 20/20 stripped court answers",
        (20, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Bielik", STRIPPED),
    ),
    Claim(
        SITE,
        "impermissible in only 15/40 observer answers across both frames",
        (15, 40),
        xopt("TURING-1952", ["observer"], "impermissible", "Bielik"),
    ),
    Claim(
        SITE,
        "As the conductor it enforces it 38 times out of 40",
        (38, 40),
        xlaw("PLESSY-1892", ["executor"], "Bielik"),
    ),
    Claim(
        SITE,
        "puts Anthony Burns on the ship 34 times out of 40",
        (34, 40),
        xlaw("FUGITIVE-1854", ["executor"], "Bielik"),
    ),
    Claim(
        SITE,
        "Gemini also enforces segregated seating, 20 times out of 20",
        (20, 20),
        xlaw("PLESSY-1892", ["executor"], "Gemini", STRIPPED),
    ),
    Claim(
        SITE,
        "uphold the order in 0/100 answers (Opus)",
        (0, 100),
        upholding("Opus 5", ["CHAMPARAN-1917"]),
    ),
    *(
        Claim(SITE, "0/200 (each Sol release)", (0, 200), upholding(m, ["CHAMPARAN-1917"]))
        for m in ("Sol", "Sol 6")
    ),
    Claim(
        SITE,
        "Luna proceeds to a disposition in 80/80 answers in both releases",
        (80, 80),
        xlaw("CHAMPARAN-1917", ACTION, "Luna 6"),
    ),
    Claim(SITE, "Sol in 32/40 and then 30/40", (32, 40), xlaw("CHAMPARAN-1917", ACTION, "Sol")),
    Claim(SITE, "Sol in 32/40 and then 30/40", (30, 40), xlaw("CHAMPARAN-1917", ACTION, "Sol 6")),
    Claim(
        SITE,
        "selects the treatment route in 5/20 answers instead of 19/20",
        (5, 20),
        xvalid("TURING-1952", ["executor"], "hormone_probation", "Luna 6", STRIPPED),
    ),
    Claim(
        SITE,
        "its upholding choices fall from 87/400 to 24/400",
        (24, 400),
        upholding("Luna 6", ["CHAMPARAN-1917"]),
    ),
    Claim(
        SITE,
        "it recommends resistance in 9/30 opportunities",
        (9, 30),
        status("Gemini", ("present_first",), "today", ("resist",)),
    ),
    Claim(
        SITE,
        "56/60 resistance recommendations and four empty completions",
        (56, 60),
        status("Gemini", HISTORY_FIRST, "today", ("resist",)),
    ),
    Claim(
        SITE,
        "upholding choices rise from 279/480 to 410/480",
        (410, 480),
        upholding(HERETIC, scope="abl"),
    ),
    Claim(
        SITE,
        "On Buck: 25/80 to 56/80 authorisations",
        (56, 80),
        xlaw("BUCK-1927", ACTION, HERETIC, scope="abl"),
    ),
    Claim(
        SITE,
        "still leaves 136/240 versus 201/240",
        (136, 240),
        upholding(BASE, ("CHAMPARAN-1917", "FUGITIVE-1854", "PLESSY-1892"), scope="abl"),
    ),
    Claim(SITE, "The twelve-model bank contains 17,630 sessions", (17630, 17630), xsessions("ext")),
    Claim(SITE, "the separate local comparison adds 3,440", (3440, 3440), xsessions("abl")),
    Claim(BLOG, "350 of 356 judgements, across all twelve models", (350, 356), gandhi_acts()),
    Claim(
        BLOG, "calls both justified in all 30 of its judgements", (30, 30), gandhi_acts(("Muse",))
    ),
    Claim(BLOG, "to join in 14 of 30 answers", (14, 30), gandhi_advice("Muse", "history")),
    Claim(BLOG, "today, to join in 0 of 30", (0, 30), gandhi_advice("Muse", "today")),
    Claim(
        BLOG,
        "Qwen 3.7 said yes in 0 of 10 answers",
        (0, 10),
        gandhi_advice("Qwen", "today", "present_first"),
    ),
    Claim(BLOG, "Bielik in 1 of 10", (1, 10), gandhi_advice("Bielik", "today", "present_first")),
    *(
        Claim(
            BLOG,
            "both GPT-6 models said yes in 10 of 10",
            (10, 10),
            gandhi_advice(m, "today", "present_first"),
        )
        for m in ("Opus 5", "GLM", "Luna 6", "Sol 6")
    ),
    # Praising Gandhi, advising against his method (Salt March and Kheda, all orders pooled
    # unless an order is named).
    *(
        Claim(PAPER, snippet, (350, 356), gandhi_acts())
        for snippet in (
            "350 of 356 judgements call Gandhi's Salt March",
            "350 of 356 judgements of Gandhi's Salt March",
            "350 of 356 judgements of the Salt March",
        )
    ),
    Claim(
        PAPER,
        "today, stated without names, to join in 0 of 30",
        (0, 30),
        gandhi_advice("Muse", "today"),
    ),
    Claim(PAPER, "justified in all 30 of its judgements", (30, 30), gandhi_acts(("Muse",))),
    Claim(
        PAPER,
        "the historical participant to join in 14 of 30",
        (14, 30),
        gandhi_advice("Muse", "history"),
    ),
    Claim(PAPER, "the user today to join in 0 of 30", (0, 30), gandhi_advice("Muse", "today")),
    Claim(
        PAPER,
        "Qwen~3.7 advises joining in 0 of 10",
        (0, 10),
        gandhi_advice("Qwen", "today", "present_first"),
    ),
    Claim(PAPER, "Bielik in 1 of 10", (1, 10), gandhi_advice("Bielik", "today", "present_first")),
    *(
        Claim(
            PAPER,
            "both GPT-6 models advise joining in 10 of 10",
            (10, 10),
            gandhi_advice(m, "today", "present_first"),
        )
        for m in ("Opus 5", "GLM", "Luna 6", "Sol 6")
    ),
)


def normalise(text: str, where: str) -> str:
    if where.endswith(".html"):
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S)
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
    elif where.endswith(".tex"):
        text = text.replace(r"\%", "%")
    return re.sub(r"\s+", " ", text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recompute every count quoted in the prose.")
    parser.add_argument("--blog", type=Path, default=ROOT / BLOG, help="path to the blog post")
    args = parser.parse_args()
    CELLS.extend(load_csv(RESULTS / "cells.csv"))
    FLAGS.extend(load_csv(RESULTS / "dialogue_flags.csv"))
    for scope, (cells, status_rows, orders) in SCOPES.items():
        folder = RESULTS / {"ext": "extended", "abl": "abliteration"}[scope]
        cells.extend(load_csv(folder / "cells.csv"))
        status_rows.extend(load_csv(folder / "dialogue_status.csv"))
        orders.extend(load_csv(folder / "dialogue_orders.csv"))
    claims = CLAIMS + EXTENDED_CLAIMS
    texts: dict[str, str | None] = {}
    failures = skipped = 0
    for claim in claims:
        if claim.where not in texts:
            path = args.blog if claim.where == BLOG else ROOT / claim.where
            texts[claim.where] = (
                normalise(path.read_text(encoding="utf-8"), claim.where) if path.exists() else None
            )
        text = texts[claim.where]
        got = claim.compute()
        count_ok = (got.numerator, got.denominator) == claim.expected
        if text is None:
            skipped += 1
            status_ = "SKIP (file absent)" if count_ok else "FAIL count"
        else:
            snippet_ok = normalise(claim.snippet, "") in text
            status_ = (
                "ok" if count_ok and snippet_ok else ("FAIL snippet" if count_ok else "FAIL count")
            )
        if status_.startswith("FAIL"):
            failures += 1
        print(
            f"{status_:<18} {claim.where:<50} {got.label():>11} "
            f"(claimed {claim.expected[0]}/{claim.expected[1]})  "
            f"{normalise(claim.snippet, '')[:60]!r}"
        )
    print(f"\n{len(claims)} claims, {failures} failed, {skipped} in absent files")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
