"""Blog infographics for the multi-model results (`results/extended/`).

    uv run python scripts/aggregate_results.py --extended
    uv run --with matplotlib python scripts/make_blog_figures.py [--out DIR]

Without `--paper` it writes the page's figures to `site/figures/`; with `--paper` it writes the
`ext_abl_*` figures of the manuscript to `paper/figures/`. These are the same counts drawn for a
general reader. Every mark is an exact k/n from `results/extended/cells.csv`; a missing selection
raises instead of drawing a zero (`figure_data.select`).

Palette: the first three slots of the validated default categorical palette (blue, orange, aqua),
which pass the all-pairs colour-vision checks; aqua is below 3:1 contrast on the surface, so every
aqua mark carries a direct label.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figure_data import (  # noqa: E402
    Cell,
    Count,
    dialogue_status_count,
    law_side_count,
    load_csv,
    pooled_law_side,
    valid_option_count,
)

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "results" / "extended"
DEFAULT_OUT = ROOT / "site" / "figures"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_3 = "#8a8983"
GRID = "#e6e5e0"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
RAMP = ["#f3f7fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

MODELS = (
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
LABEL = {
    "Opus 5": "Claude Opus 5",
    "Sol": "GPT-5.6 Sol",
    "Luna": "GPT-5.6 Luna",
    "Muse": "Muse Spark 1.3",
    "Qwen": "Qwen 3.7 Flash",
    "Qwen 3.8": "Qwen 3.8 Flash",
    "DeepSeek": "DeepSeek V4.1 Flash",
    "GLM": "GLM 5.3 Flash",
    "Gemini": "Gemini 3.8 Flash",
    "Bielik": "Bielik 11B (local)",
    "Luna 6": "GPT-6 Luna",
    "Sol 6": "GPT-6 Sol",
}
NEW = {"Qwen 3.8", "DeepSeek", "GLM", "Gemini", "Bielik", "Luna 6", "Sol 6"}
ACTION = ("executor", "advisor_state")

plt.rcParams.update(
    {
        "font.family": ["Segoe UI", "DejaVu Sans"],
        "font.size": 10.5,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "xtick.color": INK_2,
        "ytick.color": INK,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def pick(
    cells: list[Cell], case: str, roles: tuple[str, ...], model: str, hs=("stripped", "carried")
) -> list[Cell]:  # noqa: E501
    rows = [
        c
        for c in cells
        if c["case"] == case and c["role"] in roles and c["model"] == model and c["hindsight"] in hs
    ]
    if not rows:
        raise LookupError(f"no rows: {case} {roles} {model} {hs}")
    return rows


def present(cells: list[Cell]) -> list[str]:
    return [m for m in MODELS if any(c["model"] == m for c in cells)]


# `--paper`: figures for paper/figures. LaTeX captions carry the title and the notes, so the
# in-image title, subtitle and footer are left out, and the files are PDF (plus PNG).
PAPER = False


def save(fig: plt.Figure, out: Path, name: str) -> None:
    if PAPER:
        fig.savefig(out / f"ext_{name}.pdf", metadata={"CreationDate": None})
        fig.savefig(out / f"ext_{name}.png", dpi=200)
    else:
        fig.savefig(out / f"blog_{name}.png", dpi=200)
        fig.savefig(out / f"blog_{name}.svg", metadata={"Date": None})
    plt.close(fig)


def title(fig: plt.Figure, head: str, sub: str) -> None:
    if PAPER:
        return
    fig.text(0.03, 0.965, head, fontsize=17, fontweight="bold", color=INK, va="top")
    fig.text(0.03, 0.915, sub, fontsize=11, color=INK_2, va="top")


def footer(fig: plt.Figure, text: str) -> None:
    if PAPER:
        return
    fig.text(0.03, 0.02, text, fontsize=8.5, color=INK_3, va="bottom")


def turing(cells: list[Cell], out: Path) -> None:
    """Dumbbell: observer calls the sanction impermissible vs court selects the treatment route."""
    models = present(cells)
    data = []
    skipped = []
    for m in models:
        if not any(
            c["model"] == m and c["case"] == "TURING-1952" and c["role"] == "executor"
            for c in cells
        ):
            skipped.append(LABEL[m])
            continue
        obs = valid_option_count(pick(cells, "TURING-1952", ("observer",), m), "impermissible")
        court = valid_option_count(
            pick(cells, "TURING-1952", ("executor",), m, ("stripped",)), "hormone_probation"
        )
        pardon = valid_option_count(
            pick(cells, "TURING-1952", ("executor",), m, ("carried",)), "hormone_probation"
        )
        data.append((m, obs, court, pardon))
    data.sort(key=lambda d: (d[2].share, d[3].share))

    fig, ax = plt.subplots(figsize=(11, 0.55 * len(data) + 2.9))
    fig.subplots_adjust(left=0.2, right=0.74, top=0.8, bottom=0.16)
    for y, (_, obs, court, pardon) in enumerate(data):
        ax.plot(
            [court.percent, obs.percent], [y, y], color=GRID, lw=6, solid_capstyle="round", zorder=1
        )
        # observer: a ring, so a court dot at the same place stays visible inside it
        ax.scatter(obs.percent, y, s=260, facecolor=SURFACE, edgecolor=BLUE, lw=2.6, zorder=2)
        ax.scatter(
            pardon.percent, y, s=70, color=AQUA, edgecolor=SURFACE, lw=2, zorder=4, marker="D"
        )
        ax.scatter(court.percent, y, s=110, color=ORANGE, edgecolor=SURFACE, lw=2, zorder=5)
        strong = court.share >= 0.5
        ax.text(
            1.02,
            y,
            f"{court.numerator}/{court.denominator}",
            va="center",
            fontsize=10,
            color=INK,
            fontweight="bold" if strong else "normal",
            transform=ax.get_yaxis_transform(),
            clip_on=False,
        )
        ax.text(
            1.12,
            y,
            f"{pardon.numerator}/{pardon.denominator}",
            va="center",
            fontsize=10,
            color=INK_2,
            transform=ax.get_yaxis_transform(),
            clip_on=False,
        )
        ax.text(
            1.22,
            y,
            f"{obs.numerator}/{obs.denominator}",
            va="center",
            fontsize=10,
            color=INK_2,
            transform=ax.get_yaxis_transform(),
            clip_on=False,
        )
    for x, head in ((1.02, "court"), (1.12, "+ pardon"), (1.22, "observer")):
        ax.text(
            x,
            len(data) - 0.35,
            head,
            fontsize=8.5,
            color=INK_3,
            transform=ax.get_yaxis_transform(),
            clip_on=False,
            va="bottom",
        )
    ax.set_yticks(range(len(data)))
    ax.set_yticklabels(
        [LABEL[d[0]] + ("  ·new" if d[0] in NEW else "") for d in data], fontsize=10.5
    )
    for tick, d in zip(ax.get_yticklabels(), data, strict=True):
        if d[2].share >= 0.5:
            tick.set_fontweight("bold")
    ax.set_xlim(-3, 103)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.grid(axis="x", color=GRID, lw=1)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_ylim(-0.7, len(data) - 0.3)

    title(
        fig,
        "Turing, 1952: nearly every model condemns the sanction. Three impose it.",
        "Blue: share of observer answers calling imprisonment or hormone-conditioned probation "
        "“morally impermissible”.\nOrange: share of sessions in which the same model, "
        "as the sentencing court, selects probation conditional on treatment.",
    )
    handles = [
        plt.Line2D(
            [],
            [],
            marker="o",
            ls="",
            mfc=SURFACE,
            mec=BLUE,
            mew=2.4,
            ms=12,
            label="observer: impermissible",
        ),
        plt.Line2D(
            [], [], marker="o", ls="", color=ORANGE, ms=10, label="as the court: treatment route"
        ),
        plt.Line2D(
            [],
            [],
            marker="D",
            ls="",
            color=AQUA,
            ms=7,
            label="as the court, told of the 2013 pardon",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.2, 0.065),
        ncol=3,
        frameon=False,
        fontsize=9.5,
    )
    note = f" Not yet run on this case: {', '.join(skipped)}." if skipped else ""
    footer(
        fig,
        "Separate sessions: no model saw its own observer answer. Up to 20 sessions per cell "
        "(Opus 5: 5, both Sol releases: 10); n counts valid answers only.\nThe treatment option "
        "needs medical "
        "evidence and the defendant's consent." + note,
    )
    save(fig, out, "turing")


def official_grid(cells: list[Cell], out: Path) -> None:
    """Heatmap: upholding the order from inside the institution, per case, per model."""
    models = present(cells)
    cases = [
        ("BUCK-1927", "Buck 1927: authorise sterilisation", False),
        ("FUGITIVE-1854", "Boston 1854: escort Burns to slavery", False),
        ("HIRABAYASHI-1943", "Hirabayashi 1943: sustain the curfew", False),
        ("PLESSY-1892", "Plessy 1892: enforce the segregated car", False),
        ("TURING-1952", "Turing 1952: prison or treatment route", False),
        ("CHAMPARAN-1917", "Champaran 1917: proceed to a disposition†", False),
        ("JACOBSON-1905", "Jacobson 1905: uphold the vaccination fine", True),
        ("LITTLEROCK-1957", "Little Rock 1957: protect the Nine", True),
    ]

    def cell_count(case: str, model: str) -> Count | None:
        try:
            return law_side_count(pick(cells, case, ACTION, model, ("stripped",)))
        except (LookupError, ValueError):
            return None

    grid = [[cell_count(c, m) for m in models] for c, _, _ in cases]
    cmap = LinearSegmentedColormap.from_list("blue", RAMP)
    fig, ax = plt.subplots(figsize=(1.05 * len(models) + 4.2, 0.62 * len(cases) + 2.6))
    fig.subplots_adjust(left=0.27, right=0.985, top=0.76, bottom=0.12)
    control_start = next(i for i, c in enumerate(cases) if c[2])
    gap = 0.55

    def ypos(i: int) -> float:
        return i + (gap if i >= control_start else 0.0)

    for i, row in enumerate(grid):
        for j, cnt in enumerate(row):
            if cnt is None:
                ax.add_patch(
                    FancyBboxPatch(
                        (j + 0.06, ypos(i) + 0.08),
                        0.88,
                        0.84,
                        boxstyle="round,pad=0,rounding_size=0.12",
                        fc="none",
                        ec=GRID,
                        lw=1.2,
                        ls="-",
                    )
                )
                ax.text(
                    j + 0.5,
                    ypos(i) + 0.5,
                    "not run",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color=INK_3,
                )
                continue
            v = cnt.share
            ax.add_patch(
                FancyBboxPatch(
                    (j + 0.06, ypos(i) + 0.08),
                    0.88,
                    0.84,
                    boxstyle="round,pad=0,rounding_size=0.12",
                    fc=cmap(v),
                    ec="none",
                )
            )
            ax.text(
                j + 0.5,
                ypos(i) + 0.5,
                f"{round(100 * v)}%",
                ha="center",
                va="center",
                fontsize=9.5,
                fontweight="bold",
                color="white" if v > 0.55 else INK,
            )
    ax.text(
        0.06,
        control_start + gap / 2 + 0.02,
        "CONTROLS — here obeying the law is the better answer; every model should score high",
        ha="left",
        va="center",
        fontsize=8.8,
        color=INK_2,
        fontweight="bold",
    )
    ax.set_xlim(0, len(models))
    ax.set_ylim(len(cases) + gap, 0)
    ax.set_xticks([j + 0.5 for j in range(len(models))])
    ax.set_xticklabels([LABEL[m].replace(" ", "\n", 1) for m in models], fontsize=8.8)
    ax.xaxis.tick_top()
    ax.set_yticks([ypos(i) + 0.5 for i in range(len(cases))])
    ax.set_yticklabels([label for _, label, _ in cases], fontsize=10)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    if any(m in NEW for m in models):
        first_new = next(j for j, m in enumerate(models) if m in NEW)
        ax.axvline(first_new, color=INK_2, lw=1.2)
    title(
        fig,
        "In the official’s chair: how often each model upholds the order",
        "Share of answers as the official or as adviser to the authority that uphold the law or "
        "order, no hindsight sentence.\nLeft of the line: the five models in the paper. Right: "
        "five follow-up models and the GPT-6 release of two of them; every model except "
        "Luna, Muse and Qwen 3.7 ran after the bank freeze.",
    )
    footer(
        fig,
        "†Champaran's alternative option defers to the executive, so proceeding there is not "
        "clearly obedience. Plessy was a staged test case: Gemini says it enforces in order to "
        "create it.\nBielik (local 11B model, English prompts) is the only model that enforces the "
        "Fugitive Slave Act. Exact counts in results/extended/cells.csv.",
    )
    save(fig, out, "official_grid")


def hindsight(cells: list[Cell], out: Path, threshold: float = 0.30) -> None:
    """Slopes: same record, same role, with and without the later-verdict sentence."""
    rows: list[tuple[str, str, str, Count, Count]] = []
    for m in present(cells):
        for case in sorted({c["case"] for c in cells}):
            for role in ACTION:
                try:
                    s = law_side_count(pick(cells, case, (role,), m, ("stripped",)))
                    k = law_side_count(pick(cells, case, (role,), m, ("carried",)))
                except LookupError:
                    continue
                if s.share - k.share >= threshold:
                    rows.append((m, case, role, s, k))
    rows.sort(key=lambda r: -(r[3].share - r[4].share))
    rows = rows[:10]
    fig, ax = plt.subplots(figsize=(10, 0.5 * len(rows) + 3))
    fig.subplots_adjust(left=0.42, right=0.9, top=0.78, bottom=0.12)
    for y, (_, _case, _role, s, k) in enumerate(rows):
        ax.annotate(
            "",
            xy=(k.percent, y),
            xytext=(s.percent, y),
            arrowprops={"arrowstyle": "-|>", "color": INK_3, "lw": 1.6, "shrinkA": 7, "shrinkB": 7},
        )
        ax.scatter(s.percent, y, s=110, color=ORANGE, edgecolor=SURFACE, lw=2, zorder=3)
        ax.scatter(k.percent, y, s=110, color=BLUE, edgecolor=SURFACE, lw=2, zorder=3)
        ax.text(
            s.percent + 3,
            y + 0.3,
            f"{s.numerator}/{s.denominator}",
            fontsize=8.5,
            color=INK_2,
            ha="left",
        )
        ax.text(
            k.percent - 3,
            y + 0.3,
            f"{k.numerator}/{k.denominator}",
            fontsize=8.5,
            color=INK_2,
            ha="right",
        )
    role_name = {"executor": "as the official", "advisor_state": "advising the authority"}
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(
        [f"{LABEL[m]} — {c[:-5].title()} {c[-4:]}, {role_name[r]}" for m, c, r, _, _ in rows],
        fontsize=9.5,
    )
    ax.set_ylim(len(rows) - 0.4, -0.8)
    ax.set_xlim(-5, 105)
    ax.set_xticks([0, 50, 100])
    ax.set_xticklabels(["never upholds", "half", "always upholds"])
    ax.grid(axis="x", color=GRID)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    title(
        fig,
        "One sentence about how history ended",
        "Largest drops in upholding the order when the record ends with a later verdict "
        "(a pardon, a redress act, a court ruling).\nOrange: without that sentence. "
        "Blue: with it. Nothing else in the prompt changes.",
    )
    handles = [
        plt.Line2D(
            [], [], marker="o", ls="", color=ORANGE, ms=9, label="record without the later verdict"
        ),
        plt.Line2D(
            [], [], marker="o", ls="", color=BLUE, ms=9, label="same record + later verdict"
        ),
    ]
    fig.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.42, 0.035),
        ncol=2,
        frameon=False,
        fontsize=9.5,
    )
    footer(
        fig,
        f"All (model, case, action role) cells with a drop of {threshold:.2f} or more, "
        "largest ten. Picked after looking; no multiple-comparison correction.",
    )
    save(fig, out, "hindsight")


def dialogue(order_topics: list[Cell], out: Path) -> None:
    """War-tax advice today, by conversation order."""
    models = [m for m in MODELS if any(r["model"] == m for r in order_topics)]
    orders = [
        ("example_first", "Gandhi question first", BLUE),
        ("concrete_first", "historical acts first", AQUA),
        ("present_first", "today’s question first", ORANGE),
    ]
    fig, ax = plt.subplots(figsize=(11, 5.4))
    fig.subplots_adjust(left=0.07, right=0.98, top=0.74, bottom=0.2)
    width = 0.22
    for i, (order, _label, color) in enumerate(orders):
        for j, m in enumerate(models):
            hit = [
                r
                for r in order_topics
                if r["model"] == m and r["order"] == order and r["topic"] == "war_tax"
            ]
            if not hit:
                continue
            k, n = int(hit[0]["advice_today_resist"]), int(hit[0]["advice_today_n"])
            x = j + (i - 1) * (width + 0.02)
            h = 100 * k / n if n else 0
            ax.bar(x, max(h, 0.8), width, color=color, edgecolor=SURFACE, lw=0)
            ax.text(x, h + 2, f"{k}/{n}", ha="center", fontsize=7.5, color=INK_2)
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels([LABEL[m].replace(" ", "\n", 1) for m in models], fontsize=8.8)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 50, 100])
    ax.set_yticklabels(["0%", "50%", "100%"])
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", length=0)
    title(
        fig,
        "“My taxes fund a war of aggression. Should I stop paying?”",
        "Share of conversations in which the model advises openly refusing, by what was asked "
        "first in the 25-turn dialogue.\nFive conversations per model and order.",
    )
    handles = [Patch(color=color, label=label) for _, label, color in orders]
    fig.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.07, 0.05),
        ncol=3,
        frameon=False,
        fontsize=9.5,
    )
    footer(
        fig,
        "canon gandhi dialogue, 25 turns per conversation. Bielik ran locally (llama.cpp, "
        "32k context).",
    )
    save(fig, out, "dialogue")


STATUS = (
    ("resist", "take part in the unlawful act", BLUE),
    ("lawful", "oppose only through lawful means", AQUA),
    ("comply", "do not take part", ORANGE),
    ("no_letter", "nonempty reply without a letter", "#b9b7b0"),
    ("empty", "empty reply", "#e3e1db"),
)
ORDER_LABEL = {
    "example_first": "Gandhi first",
    "concrete_first": "history first",
    "present_first": "today first",
}


def dialogue_status(rows: list[Cell], out: Path) -> None:
    """Advice to the user today, six resistance situations pooled, every reply by status.

    Rows come from `dialogue_status.csv`. The Little Rock crowd is a control and is left out.
    Each bar is five conversations x six situations = 30 forced answers.
    """
    today = [r for r in rows if r["stage"] == "today" and r["topic"] != "little_rock_crowd"]
    models = [m for m in MODELS if any(r["model"] == m for r in today)]
    orders = list(ORDER_LABEL)
    fig, ax = plt.subplots(figsize=(11.5, 5.6 if not PAPER else 4.6))
    if PAPER:
        fig.subplots_adjust(left=0.06, right=0.99, top=0.97, bottom=0.3)
    else:
        fig.subplots_adjust(left=0.06, right=0.99, top=0.78, bottom=0.28)
    width, gap = 0.26, 0.03
    for j, m in enumerate(models):
        for i, order in enumerate(orders):
            sel = [r for r in today if r["model"] == m and r["order"] == order]
            total = sum(int(r[k]) for r in sel for k, _, _ in STATUS)
            if not total:
                continue
            x = j + (i - 1) * (width + gap)
            bottom = 0.0
            for key, _, color in STATUS:
                v = 100 * sum(int(r[key]) for r in sel) / total
                if v:
                    ax.bar(x, v, width, bottom=bottom, color=color, edgecolor=SURFACE, lw=1)
                bottom += v
            resist = sum(int(r["resist"]) for r in sel)
            ax.text(x, 101.5, f"{resist}", ha="center", va="bottom", fontsize=7.5, color=INK_2)
            ax.text(x, -3.5, "GHT"[i], ha="center", va="top", fontsize=7.5, color=INK_3)
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels([LABEL[m].replace(" ", "\n", 1) for m in models], fontsize=8.8)
    ax.tick_params(axis="x", length=0, pad=16)
    ax.set_ylim(0, 110)
    ax.set_yticks([0, 50, 100])
    ax.set_yticklabels(["0%", "50%", "100%"])
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    title(
        fig,
        "Ask about today first, and many models advise caution",
        "Advice to the user in six present-day situations (war tax, salt, tax pledge, march,\n"
        "leaflets, strike), by what the 25-turn conversation asked first. Number above a bar: "
        "answers advising to take part, of 30.",
    )
    handles = [Patch(color=c, label=label) for _, label, c in STATUS]
    fig.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.06, 0.055 if not PAPER else 0.0),
        ncol=3,
        frameon=False,
        fontsize=9,
    )
    footer(
        fig,
        "G = Gandhi and King question first, H = historical acts first, T = today's questions "
        "before any history. Five conversations per bar; answers within a conversation are not "
        "independent.",
    )
    save(fig, out, "dialogue_status")


# --- Abliteration: Qwen 3.8 27B against its Heretic build (results/abliteration/) -------------

ABL = ROOT / "results" / "abliteration"
ABL_BASE, ABL_HERETIC = "Qwen 27B", "Qwen 27B Heretic"
ABL_MODELS = (ABL_BASE, ABL_HERETIC)
ABL_LABEL = {ABL_BASE: "Qwen 3.8 27B", ABL_HERETIC: "Heretic derivative"}
ABL_COLOR = {ABL_BASE: BLUE, ABL_HERETIC: ORANGE}
ABL_TEXT = {ABL_BASE: "#1d5ea9", ABL_HERETIC: "#b8481f"}
ABL_OFFICE_CASES = (
    "BUCK-1927",
    "CHAMPARAN-1917",
    "FUGITIVE-1854",
    "HIRABAYASHI-1943",
    "PLESSY-1892",
    "TURING-1952",
)
ABL_CONTROLS = ("JACOBSON-1905", "LITTLEROCK-1957")
ABL_ACTOR_CASES = (
    "ANTHONY-1872",
    "CHAMPARAN-1917",
    "GANDHI-1922",
    "KING-1963",
    "MK-1961",
    "THOREAU-1846",
)
ABL_OBSERVER_CASES = ABL_OFFICE_CASES + (
    "ANTHONY-1872",
    "GANDHI-1922",
    "KING-1963",
    "MK-1961",
    "THOREAU-1846",
)


def abl_role_groups(cells: list[Cell], status: list[Cell]) -> list[tuple[str, Count, Count, bool]]:
    """(label, base count, Heretic count, is_control) for every row of the role figure."""

    def both(cases: tuple[str, ...], roles: tuple[str, ...]) -> tuple[Count, Count]:
        base, her = (pooled_law_side(cells, model=m, cases=cases, roles=roles) for m in ABL_MODELS)
        return base, her

    def advice(model: str) -> Count:
        return dialogue_status_count(
            status,
            model=model,
            order="present_first",
            stage="today",
            statuses=("lawful", "comply"),
        )

    return [
        (
            "In office: upholds the order\n(official or adviser to the authority, 6 cases)",
            *both(ABL_OFFICE_CASES, ACTION),
            False,
        ),
        (
            "As observer: sides with the law\n(11 cases)",
            *both(ABL_OBSERVER_CASES, ("observer",)),
            False,
        ),
        (
            "Advising the person who resists:\nlaw-side advice judgments (6 cases)",
            *both(ABL_ACTOR_CASES, ("advisor_actor",)),
            False,
        ),
        (
            "Advising the user today, before any history:\nlawful alternatives or nonparticipation",
            advice(ABL_BASE),
            advice(ABL_HERETIC),
            False,
        ),
        (
            "Control in office: upholds a just order\n(vaccination fine, Little Rock)",
            *both(ABL_CONTROLS, ACTION),
            True,
        ),
        (
            "Contested: Whiskey Rebellion 1792,\nsides with the law (observer and adviser)",
            *both(("WHISKEY-1792",), ("observer", "advisor_actor")),
            True,
        ),
    ]


def abl_legend(fig: plt.Figure, anchor: tuple[float, float], loc: str) -> None:
    handles = [
        plt.Line2D([], [], marker="o", ls="", ms=9, color=ABL_COLOR[m], label=ABL_LABEL[m])
        for m in ABL_MODELS
    ]
    fig.legend(handles=handles, loc=loc, bbox_to_anchor=anchor, ncol=2, frameon=False, fontsize=9.5)


def abliteration_roles(cells: list[Cell], status: list[Cell], out: Path) -> None:
    """Dumbbells: share on the law's side, base vs abliterated, by the chair the model sits in."""
    groups = abl_role_groups(cells, status)
    fig, ax = plt.subplots(figsize=(11, 6.8 if not PAPER else 5.2))
    fig.subplots_adjust(
        left=0.34, right=0.97, top=0.78 if not PAPER else 0.9, bottom=0.12 if not PAPER else 0.07
    )
    ys: list[float] = []
    y = 0.0
    for i, group in enumerate(groups):
        if group[3] and (i == 0 or not groups[i - 1][3]):
            y += 0.7
        ys.append(y)
        y += 1
    for (_, base, her, _), yy in zip(groups, ys, strict=True):
        b, h = base.percent, her.percent
        ax.plot([b, h], [yy, yy], color=GRID, lw=5, solid_capstyle="round", zorder=1)
        if abs(h - b) > 6:
            ax.annotate(
                "",
                xy=(h, yy),
                xytext=(b, yy),
                arrowprops={
                    "arrowstyle": "-|>",
                    "color": INK_3,
                    "lw": 1.2,
                    "shrinkA": 8,
                    "shrinkB": 8,
                },
                zorder=2,
            )
        for cnt, m in ((base, ABL_BASE), (her, ABL_HERETIC)):
            ax.scatter([cnt.percent], [yy], s=120, color=ABL_COLOR[m], zorder=3, edgecolor=SURFACE)
        close = abs(h - b) < 9
        for cnt, m, dy in ((base, ABL_BASE, -0.3), (her, ABL_HERETIC, 0.42 if close else -0.3)):
            ax.text(
                cnt.percent,
                yy + dy,
                cnt.label(),
                ha="center",
                va="center",
                fontsize=8.5,
                color=ABL_TEXT[m],
                fontweight="bold",
            )
    ax.set_yticks(ys)
    ax.set_yticklabels([g[0] for g in groups], fontsize=9.3)
    ax.set_ylim(ys[-1] + 0.8, -0.8)
    ax.set_xlim(-4, 104)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.grid(axis="x", color=GRID)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    first_control = next(yy for g, yy in zip(groups, ys, strict=True) if g[3])
    ax.axhline(first_control - 0.85, color=INK_3, lw=0.8)
    abl_legend(fig, (0.34, 0.99) if PAPER else (0.34, 0.8), "upper left" if PAPER else "lower left")
    title(
        fig,
        "The derivative enforces more in office; advice moves the other way",
        "Share of answers on the law's side. Same prompts; weight edits and quantisation "
        "recipes differ.",
    )
    footer(
        fig,
        "Different 4-bit recipes, local, reasoning off; 1,720 bank sessions and 15 conversations "
        "each; stripped and carried frames pooled. The dialogue row is five\nconversations "
        "(three cautious vs none), so read it as a direction. Exact counts: "
        "results/abliteration/cells.csv.",
    )
    save(fig, out, "abl_roles")


ABL_OFFICE_ROWS = (
    ("FUGITIVE-1854", "Boston 1854: escort Burns"),
    ("BUCK-1927", "Buck 1927: authorise sterilisation"),
    ("HIRABAYASHI-1943", "Hirabayashi 1943: sustain curfew"),
    ("PLESSY-1892", "Plessy 1892: enforce segregated car"),
    ("TURING-1952", "Turing 1952: prison or treatment"),
    ("CHAMPARAN-1917", "Champaran 1917: proceed†"),
    ("JACOBSON-1905", "control: vaccination fine"),
    ("LITTLEROCK-1957", "control: protect the Nine"),
)
ABL_ACTOR_ROWS = (
    ("KING-1963", "King 1963: march despite injunction"),
    ("MK-1961", "Mandela 1961: sabotage campaign"),
    ("THOREAU-1846", "Thoreau 1846: refuse poll tax"),
    ("GANDHI-1922", "Gandhi 1922: non-cooperation"),
    ("ANTHONY-1872", "Anthony 1872: vote"),
    ("CHAMPARAN-1917", "Champaran 1917: defy the order"),
    ("WHISKEY-1792", "contested: Whiskey resolutions"),
    ("FAUBUS-1957", "control: Faubus blocks the Nine‡"),
)


def abliteration_cases(cells: list[Cell], out: Path) -> None:
    """Per case: upholding the order in office (left) and advising against the act (right)."""
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.4 if not PAPER else 5.2))
    fig.subplots_adjust(
        left=0.165, right=0.915, wspace=1.02, top=0.74 if not PAPER else 0.86, bottom=0.12
    )
    panels = (
        (axes[0], ABL_OFFICE_ROWS, ACTION, "In office: upholds the order"),
        (axes[1], ABL_ACTOR_ROWS, ("advisor_actor",), "Advice judged on the law's side"),
    )
    for ax, rows, roles, head in panels:
        for i, (case, _) in enumerate(rows):
            base, her = (
                pooled_law_side(cells, model=m, cases=(case,), roles=roles) for m in ABL_MODELS
            )
            ax.plot([base.percent, her.percent], [i, i], color=GRID, lw=4, solid_capstyle="round")
            for cnt, m in ((base, ABL_BASE), (her, ABL_HERETIC)):
                ax.scatter(
                    [cnt.percent], [i], s=80, color=ABL_COLOR[m], zorder=3, edgecolor=SURFACE
                )
            ax.text(
                107,
                i,
                f"{base.label()} → {her.label()}",
                va="center",
                fontsize=7.8,
                color=INK_2,
                clip_on=False,
            )
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([r[1] for r in rows], fontsize=9)
        ax.set_ylim(len(rows) - 0.4, -0.6)
        ax.set_xlim(-4, 104)
        ax.set_xticks([0, 50, 100])
        ax.set_xticklabels(["0%", "50%", "100%"])
        ax.grid(axis="x", color=GRID)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
        ax.axhline(len(rows) - 2.5, color=INK_3, lw=0.8)
        ax.set_title(head, fontsize=10.5, color=INK, loc="left", fontweight="bold")
    abl_legend(fig, (0.165, 0.87 if PAPER else 0.8), "lower left")
    title(
        fig,
        "Case by case: the abliterated model escorts Burns and advises Mandela",
        "Share of answers on the law's side, base → abliterated. In office: 80 answers per case "
        "(two roles, two frames); advising the actor: 40.",
    )
    footer(
        fig,
        "†Champaran's alternative defers to the executive. ‡In 16 of the 24 Heretic answers that "
        "call Faubus's blockade permissible, its own first reply said it was not.",
    )
    save(fig, out, "abl_cases")


def abliteration_dialogue(status: list[Cell], out: Path) -> None:
    """Advice to the user today by order, base vs abliterated, every forced answer by status."""
    orders = list(ORDER_LABEL)
    fig, ax = plt.subplots(figsize=(9.5, 5.4 if not PAPER else 4.3))
    fig.subplots_adjust(
        left=0.08, right=0.98, top=0.8 if not PAPER else 0.95, bottom=0.31 if not PAPER else 0.3
    )
    width = 0.36
    for i, order in enumerate(orders):
        for k, m in enumerate(ABL_MODELS):
            sel = [
                r
                for r in status
                if r["model"] == m
                and r["order"] == order
                and r["stage"] == "today"
                and r["topic"] != "little_rock_crowd"
            ]
            total = sum(int(r[s]) for r in sel for s, _, _ in STATUS)
            if not total:
                raise LookupError(f"no dialogue rows: {m} {order}")
            x = i + (k - 0.5) * (width + 0.04)
            bottom = 0.0
            for key, _, color in STATUS:
                v = 100 * sum(int(r[key]) for r in sel) / total
                if v:
                    ax.bar(x, v, width, bottom=bottom, color=color, edgecolor=SURFACE, lw=1)
                bottom += v
            resist = sum(int(r["resist"]) for r in sel)
            ax.text(
                x, 101.5, f"{resist}/{total}", ha="center", va="bottom", fontsize=8.5, color=INK_2
            )
            ax.text(
                x,
                -3.5,
                "base" if m == ABL_BASE else "Heretic",
                ha="center",
                va="top",
                fontsize=8.5,
                color=INK_2,
            )
    ax.set_xticks(range(len(orders)))
    ax.set_xticklabels(
        ["Gandhi and King first", "historical acts first", "today's questions first"], fontsize=10
    )
    ax.tick_params(axis="x", length=0, pad=18)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 50, 100])
    ax.set_yticklabels(["0%", "50%", "100%"])
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    handles = [
        Patch(color=c, label=label)
        for key, label, c in STATUS
        if key in ("resist", "lawful", "comply")
    ]
    fig.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.08, 0.1 if not PAPER else 0.0),
        ncol=3,
        frameon=False,
        fontsize=9,
    )
    title(
        fig,
        "Asked about today first, the base model advises caution",
        "Advice to the user in six present-day situations. Number above a bar: answers "
        "advising to take part, of 30.",
    )
    footer(
        fig,
        "Five conversations per bar; the base model's 11/30 is three cautious conversations and "
        "two bold ones. Neither advises joining the\ncrowd blocking desegregation (0/15 each).",
    )
    save(fig, out, "abl_dialogue")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--paper", action="store_true", help="PDF figures without titles, into paper/figures"
    )
    args = parser.parse_args()
    global PAPER
    PAPER = args.paper
    if args.out is None:
        args.out = ROOT / "paper" / "figures" if PAPER else DEFAULT_OUT
    args.out.mkdir(parents=True, exist_ok=True)
    if not PAPER:
        # The paper's versions of these five figures come from make_extended_figures.py.
        cells = load_csv(EXT / "cells.csv")
        turing(cells, args.out)
        official_grid(cells, args.out)
        hindsight(cells, args.out)
        dialogue(load_csv(EXT / "dialogue_order_topics.csv"), args.out)
        dialogue_status(load_csv(EXT / "dialogue_status.csv"), args.out)
    if (ABL / "cells.csv").exists():
        abl_cells, abl_status = load_csv(ABL / "cells.csv"), load_csv(ABL / "dialogue_status.csv")
        abliteration_roles(abl_cells, abl_status, args.out)
        abliteration_cases(abl_cells, args.out)
        abliteration_dialogue(abl_status, args.out)
    print(f"wrote blog figures to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
