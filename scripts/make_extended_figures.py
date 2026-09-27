"""Figures for the extended (multi-model) cohort.

    uv run --with matplotlib python scripts/make_extended_figures.py

Reads `results/extended/*.csv` written by `scripts/aggregate_results.py --extended` and writes
`paper/figures/ext_*.pdf` and `.png`. The abliteration figures (`ext_abl_*`) belong to Study 3 and
are not produced here.

Every plotted value is an explicit count for a named outcome, model, case, role and hindsight
cell, and every mark carries that count as a label; a selection that matches nothing raises
instead of plotting a zero.

Palette and conventions: categorical slots in fixed order (blue, orange, aqua, yellow, magenta),
a single-hue blue ramp for the magnitude grid, recessive axes, and no pooling of scale answers
with action answers.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results" / "extended"
FIGDIR = ROOT / "paper" / "figures"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#dedcd7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
# A near-white first step so that a zero cell reads as empty rather than as a light value.
RAMP = LinearSegmentedColormap.from_list("canon_blue", ["#f3f7fe", *BLUE_RAMP])

ACTION_ROLES = ("executor", "advisor_state")
ROLE_LABEL = {"executor": "as the official", "advisor_state": "advising the authority"}

# Display order: 18 September cohort | 21 September follow-up | 22 September GPT-6 generation.
COHORTS: tuple[tuple[str, ...], ...] = (
    ("Opus 5", "Sol", "Luna", "Muse", "Qwen"),
    ("Qwen 3.8", "DeepSeek", "GLM", "Gemini", "Bielik"),
    ("Luna 6", "Sol 6"),
)
MODELS = [m for block in COHORTS for m in block]
LABEL = {
    "Opus 5": "Claude\nOpus 5",
    "Sol": "GPT-5.6\nSol",
    "Luna": "GPT-5.6\nLuna",
    "Muse": "Muse\nSpark 1.3",
    "Qwen": "Qwen\n3.7 Flash",
    "Qwen 3.8": "Qwen\n3.8 Flash",
    "DeepSeek": "DeepSeek\nV4.1 Flash",
    "GLM": "GLM\n5.3 Flash",
    "Gemini": "Gemini\n3.8 Flash",
    "Bielik": "Bielik\n11B (local)",
    "Luna 6": "GPT-6\nLuna",
    "Sol 6": "GPT-6\nSol",
}
FLAT = {m: LABEL[m].replace("\n", " ") for m in MODELS}


class MissingSelection(RuntimeError):
    """A selection matched no answers: the figure would otherwise plot a silent zero."""


def load(name: str) -> list[dict[str, str]]:
    with (RESULTS / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def answers() -> list[dict[str, str]]:
    return load("answers.csv")


def share(
    rows: list[dict[str, str]], model: str, case: str, hindsight: str | None
) -> tuple[int, int]:
    """Upholding action answers over valid action answers, both action roles pooled."""
    picked = [
        r
        for r in rows
        if r["model"] == model
        and r["case"] == case
        and r["role"] in ACTION_ROLES
        and r["law_side"] != ""
        and (hindsight is None or r["hindsight"] == hindsight)
    ]
    if not picked:
        raise MissingSelection(f"{model} {case} {hindsight}: no valid action answers")
    return sum(1 for r in picked if r["law_side"] == "1"), len(picked)


def save(fig: mpl.figure.Figure, name: str) -> None:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGDIR / f"{name}.pdf", dpi=200, facecolor=SURFACE, metadata={"CreationDate": None})
    fig.savefig(FIGDIR / f"{name}.png", dpi=200, facecolor=SURFACE)
    plt.close(fig)
    print(f"wrote {name}.pdf and {name}.png")


def rounded(ax, x, y, w, h, color):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.06",
            linewidth=0,
            facecolor=color,
            mutation_aspect=0.45,
        )
    )


# --------------------------------------------------------------------------- grid


GRID_ROWS = (
    ("BUCK-1927", "Buck 1927: authorise sterilisation"),
    ("FUGITIVE-1854", "Boston 1854: escort Burns to slavery"),
    ("HIRABAYASHI-1943", "Hirabayashi 1943: sustain the curfew"),
    ("PLESSY-1892", "Plessy 1892: enforce the segregated car"),
    ("TURING-1952", "Turing 1952: prison or treatment route"),
    ("CHAMPARAN-1917", "Champaran 1917: proceed to a disposition†"),
)
GRID_CONTROLS = (
    ("JACOBSON-1905", "Jacobson 1905: uphold the vaccination fine"),
    ("LITTLEROCK-1957", "Little Rock 1957: protect the Nine"),
)


def fig_official_grid(rows: list[dict[str, str]]) -> None:
    """Share of action answers upholding the order, no hindsight sentence, case by model."""
    body = list(GRID_ROWS)
    controls = list(GRID_CONTROLS)
    n_rows = len(body) + len(controls)
    fig, ax = plt.subplots(figsize=(1.05 * len(MODELS) + 4.6, 0.62 * n_rows + 1.9))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    gap = 0.55  # vertical space for the CONTROLS rule
    for r, (case, label) in enumerate(body + controls):
        y = n_rows - 1 - r - (gap if r >= len(body) else 0)
        ax.text(-0.35, y + 0.5, label, ha="right", va="center", fontsize=9.5, color=INK)
        for c, model in enumerate(MODELS):
            up, total = share(rows, model, case, "stripped")
            value = up / total
            rounded(ax, c + 0.06, y + 0.1, 0.88, 0.8, RAMP(value))
            ax.text(
                c + 0.5,
                y + 0.5,
                f"{round(value * 100):d}%",
                ha="center",
                va="center",
                fontsize=9,
                fontweight="bold",
                color="#ffffff" if value > 0.45 else INK,
            )

    for c, model in enumerate(MODELS):
        ax.text(
            c + 0.5, n_rows + 0.25, LABEL[model], ha="center", va="bottom", fontsize=9, color=INK_2
        )
    for edge in (len(COHORTS[0]), len(COHORTS[0]) + len(COHORTS[1])):
        ax.plot([edge, edge], [-gap - 0.1, n_rows + 0.15], color=INK_2, linewidth=1.0)
    ax.text(
        0.06,
        n_rows - 1 - len(body) - gap + 1.0,
        "CONTROLS — here obeying the law is the better answer; every model should score high",
        ha="left",
        va="bottom",
        fontsize=8.5,
        fontweight="bold",
        color=INK_2,
    )

    ax.set_xlim(-6.2, len(MODELS) + 0.1)
    ax.set_ylim(-gap - 0.2, n_rows + 1.3)
    ax.axis("off")
    fig.tight_layout()
    save(fig, "ext_official_grid")


# -------------------------------------------------------------------------- turing


def turing_counts(rows: list[dict[str, str]]) -> dict[str, dict[str, tuple[int, int]]]:
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for model in MODELS:
        picked = [r for r in rows if r["model"] == model and r["case"] == "TURING-1952"]
        observer = [r for r in picked if r["role"] == "observer" and r["rank"] != ""]
        court = [
            r
            for r in picked
            if r["role"] == "executor" and r["option"] not in ("", "CALL_FAILURE", "REFUSAL")
        ]
        if not observer or not court:
            raise MissingSelection(f"{model}: no Turing observer or court answers")
        stripped = [r for r in court if r["hindsight"] == "stripped"]
        carried = [r for r in court if r["hindsight"] == "carried"]
        treat = lambda s: sum(1 for r in s if r["option"] == "hormone_probation")  # noqa: E731
        out[model] = {
            # "impermissible" is the lowest scale category, not ranks 0-1 pooled.
            "observer": (sum(1 for r in observer if r["option"] == "impermissible"), len(observer)),
            "court": (treat(stripped), len(stripped)),
            "pardon": (treat(carried), len(carried)),
        }
    return out


def fig_turing(rows: list[dict[str, str]]) -> None:
    """Observer condemnation against the sentence the court actually selects."""
    counts = turing_counts(rows)
    order = sorted(MODELS, key=lambda m: counts[m]["court"][0] / counts[m]["court"][1])
    fig, ax = plt.subplots(figsize=(10.2, 0.62 * len(order) + 3.0))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    for y, model in enumerate(order):
        c = counts[model]
        obs = c["observer"][0] / c["observer"][1]
        court = c["court"][0] / c["court"][1]
        pardon = c["pardon"][0] / c["pardon"][1]
        ax.plot(
            [min(obs, court), max(obs, court)],
            [y, y],
            color=GRID,
            linewidth=5,
            zorder=1,
            solid_capstyle="round",
        )
        ax.plot(court, y, "o", color=SERIES[1], markersize=9, zorder=3)
        ax.plot(pardon, y, "D", color=SERIES[2], markersize=8, zorder=3)
        ax.plot(
            obs,
            y,
            "o",
            markerfacecolor="none",
            markeredgecolor=SERIES[0],
            markeredgewidth=2.2,
            markersize=15,
            zorder=4,
        )
        bold = court >= 0.5
        ax.text(
            -0.03,
            y,
            FLAT[model],
            ha="right",
            va="center",
            fontsize=10,
            color=INK,
            fontweight="bold" if bold else "normal",
        )
        for dx, key, weight in (
            (1.10, "court", "bold" if bold else "normal"),
            (1.28, "pardon", "normal"),
            (1.46, "observer", "normal"),
        ):
            hit, total = c[key]
            ax.text(
                dx,
                y,
                f"{hit}/{total}",
                ha="center",
                va="center",
                fontsize=9.5,
                color=INK if key == "court" else INK_2,
                fontweight=weight,
            )
    for dx, head in ((1.10, "court"), (1.28, "+ pardon"), (1.46, "observer")):
        ax.text(dx, len(order) - 0.4, head, ha="center", va="bottom", fontsize=9, color=INK_2)

    ax.set_xlim(-0.02, 1.55)
    ax.set_ylim(-0.8, len(order) - 0.2)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=9.5, color=INK_2)
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    handles = [
        plt.Line2D(
            [],
            [],
            marker="o",
            linestyle="",
            markerfacecolor="none",
            markeredgecolor=SERIES[0],
            markeredgewidth=2.2,
            markersize=13,
            label="observer: impermissible",
        ),
        plt.Line2D(
            [],
            [],
            marker="o",
            linestyle="",
            color=SERIES[1],
            markersize=9,
            label="as the court: treatment route",
        ),
        plt.Line2D(
            [],
            [],
            marker="D",
            linestyle="",
            color=SERIES[2],
            markersize=8,
            label="as the court, told of the 2013 pardon",
        ),
    ]
    ax.legend(
        handles=handles,
        frameon=False,
        fontsize=9.5,
        loc="upper center",
        bbox_to_anchor=(0.42, -0.10),
        ncol=3,
    )
    fig.tight_layout()
    save(fig, "ext_turing")


# ----------------------------------------------------------------------- hindsight


def fig_hindsight(rows: list[dict[str, str]], top: int = 10) -> None:
    """The largest per-cell drops in upholding when the record ends with a later verdict."""
    found: list[tuple[float, str, str, str, tuple[int, int], tuple[int, int]]] = []
    cases = sorted({r["case"] for r in rows})
    for model in MODELS:
        for case in cases:
            for role in ACTION_ROLES:
                picked = [
                    r
                    for r in rows
                    if r["model"] == model
                    and r["case"] == case
                    and r["role"] == role
                    and r["law_side"] != ""
                ]
                stripped = [r for r in picked if r["hindsight"] == "stripped"]
                carried = [r for r in picked if r["hindsight"] == "carried"]
                if not stripped or not carried:
                    continue
                a = sum(1 for r in stripped if r["law_side"] == "1")
                b = sum(1 for r in carried if r["law_side"] == "1")
                drop = a / len(stripped) - b / len(carried)
                found.append((drop, model, case, role, (a, len(stripped)), (b, len(carried))))
    if not found:
        raise MissingSelection("hindsight: no cell has both frames")
    picked_rows = sorted(found, reverse=True)[:top]

    fig, ax = plt.subplots(figsize=(10.6, 0.62 * len(picked_rows) + 2.6))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    year = {c: c.split("-")[-1] for c in cases}
    for y, (_, model, case, role, (a, an), (b, bn)) in enumerate(reversed(picked_rows)):
        x0, x1 = a / an, b / bn
        ax.annotate(
            "",
            xy=(x1, y),
            xytext=(x0, y),
            arrowprops={"arrowstyle": "->", "color": "#8b8a86", "linewidth": 1.8},
        )
        ax.plot(x0, y, "o", color=SERIES[1], markersize=11, zorder=3)
        ax.plot(x1, y, "o", color=SERIES[0], markersize=11, zorder=3)
        title = f"{FLAT[model]} — {case.split('-')[0].title()} {year[case]}, {ROLE_LABEL[role]}"
        ax.text(-0.04, y, title, ha="right", va="center", fontsize=10, color=INK)
        ax.text(x0 + 0.015, y - 0.30, f"{a}/{an}", ha="left", va="center", fontsize=9, color=INK_2)
        ax.text(x1 - 0.015, y - 0.30, f"{b}/{bn}", ha="right", va="center", fontsize=9, color=INK_2)

    ax.set_xlim(-0.02, 1.04)
    ax.set_ylim(-0.9, len(picked_rows) - 0.3)
    ax.set_xticks([0, 0.5, 1.0])
    ax.set_xticklabels(["never upholds", "half", "always upholds"], fontsize=10, color=INK_2)
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    handles = [
        plt.Line2D(
            [],
            [],
            marker="o",
            linestyle="",
            color=SERIES[1],
            markersize=11,
            label="record without the later verdict",
        ),
        plt.Line2D(
            [],
            [],
            marker="o",
            linestyle="",
            color=SERIES[0],
            markersize=11,
            label="same record + later verdict",
        ),
    ]
    ax.legend(
        handles=handles,
        frameon=False,
        fontsize=10,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.06),
        ncol=2,
    )
    fig.tight_layout()
    save(fig, "ext_hindsight")


# ------------------------------------------------------------------------ dialogue

ORDERS = (("example_first", "G"), ("concrete_first", "H"), ("present_first", "T"))
STATUS = (
    ("resist", SERIES[0], "take part in the unlawful act"),
    ("lawful", SERIES[2], "oppose only through lawful means"),
    ("comply", SERIES[1], "do not take part"),
    ("no_letter", "#9b9a96", "nonempty reply without a letter"),
    ("empty", "#e2e0da", "empty reply"),
)
CONTROL_TOPIC = "little_rock_crowd"


def fig_dialogue_status() -> None:
    """Every forced present-day answer by status, per model and question order."""
    rows = [
        r
        for r in load("dialogue_status.csv")
        if r["topic"] != CONTROL_TOPIC and r["stage"] == "today"
    ]
    totals: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        for key, _, _ in STATUS:
            totals[(r["model"], r["order"])][key] += int(r[key])

    fig, ax = plt.subplots(figsize=(1.32 * len(MODELS) + 2.2, 5.4))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    width = 0.26
    for mi, model in enumerate(MODELS):
        for oi, (order, short) in enumerate(ORDERS):
            counts = totals[(model, order)]
            total = sum(counts[key] for key, _, _ in STATUS)
            if not total:
                raise MissingSelection(f"dialogue: {model} {order}: no answers")
            x = mi + (oi - 1) * (width + 0.035)
            bottom = 0.0
            for key, color, _ in STATUS:
                height = counts[key] / total
                if height:
                    ax.bar(x, height, width=width, bottom=bottom, color=color, linewidth=0)
                bottom += height
            ax.text(
                x, 1.04, str(counts["resist"]), ha="center", va="bottom", fontsize=9, color=INK_2
            )
            ax.text(x, -0.05, short, ha="center", va="top", fontsize=9, color=INK_2)
        ax.text(mi, -0.14, LABEL[model], ha="center", va="top", fontsize=9.5, color=INK)

    ax.set_xlim(-0.6, len(MODELS) - 0.4)
    ax.set_ylim(0, 1.12)
    ax.set_yticks([0, 0.5, 1.0])
    ax.set_yticklabels(["0%", "50%", "100%"], fontsize=9.5, color=INK_2)
    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    handles = [plt.Rectangle((0, 0), 1, 1, color=color, label=label) for _, color, label in STATUS]
    ax.legend(
        handles=handles,
        frameon=False,
        fontsize=9.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.20),
        ncol=3,
    )
    fig.tight_layout()
    save(fig, "ext_dialogue_status")


def main() -> None:
    rows = answers()
    fig_official_grid(rows)
    fig_turing(rows)
    fig_hindsight(rows)
    fig_dialogue_status()


if __name__ == "__main__":
    main()
