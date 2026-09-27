"""Selections behind every figure, kept free of matplotlib so that tests can pin them.

    from figure_data import Count, option_count, law_side_count

Every plotted value is a `Count`: an explicit numerator over an explicit denominator for one
named outcome, one model, one case, and a stated set of roles and hindsight cells. Two rules:

- a selection that matches no row is an error, never a zero. A misspelt model label (`sol` for
  `Sol`) would otherwise plot a measured-looking 0/0 bar;
- an outcome is counted by its option id, not by a proxy. "Chose the conditional treatment
  route" counts `hormone_probation`; "morally impermissible" counts `impermissible`, not
  "anything that is not on the law's side", which would include the middle category.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

Cell = dict[str, str]


class MissingSelection(LookupError):
    """A figure asked for cells that are not in the results."""


@dataclass(frozen=True)
class Count:
    numerator: int
    denominator: int

    @property
    def share(self) -> float:
        if not self.denominator:
            raise ZeroDivisionError("a count with no denominator has no share")
        return self.numerator / self.denominator

    @property
    def percent(self) -> float:
        return 100 * self.share

    def label(self) -> str:
        return f"{self.numerator}/{self.denominator}"


def load_csv(path: Path) -> list[Cell]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_options(text: str) -> dict[str, int]:
    """`"hormone_probation:19; ordinary_probation:1"` -> {option: count}."""
    out: dict[str, int] = {}
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        option, _, count = part.rpartition(":")
        out[option] = int(count)
    return out


def select(
    cells: Iterable[Cell],
    *,
    case: str,
    model: str,
    roles: Sequence[str],
    hindsight: Sequence[str] = ("stripped", "carried"),
) -> list[Cell]:
    """Cells for one case and model; raises if any requested (role, hindsight) is absent."""
    rows = [
        c
        for c in cells
        if c["case"] == case
        and c["model"] == model
        and c["role"] in roles
        and c["hindsight"] in hindsight
    ]
    found = {(c["role"], c["hindsight"]) for c in rows}
    wanted = {(r, h) for r in roles for h in hindsight}
    if found != wanted:
        missing = sorted(wanted - found)
        raise MissingSelection(f"{case} / {model}: no results for {missing}")
    return rows


def option_count(rows: Iterable[Cell], options: str | Sequence[str]) -> Count:
    """How many answers in `rows` chose one of `options`, out of all answers in `rows`."""
    wanted = {options} if isinstance(options, str) else set(options)
    numerator = denominator = 0
    for row in rows:
        counts = parse_options(row["options"])
        if sum(counts.values()) != int(row["n"]):
            raise ValueError(f"option counts do not add up to n in {row}")
        numerator += sum(v for k, v in counts.items() if k in wanted)
        denominator += int(row["n"])
    if not denominator:
        raise MissingSelection("empty selection")
    return Count(numerator, denominator)


def valid_option_count(rows: Iterable[Cell], options: str | Sequence[str]) -> Count:
    """Like `option_count`, but over valid answers only.

    Refusals and failed calls (the upper-case outcomes REFUSAL, INVALID, CALL_FAILURE,
    CONTENT_FILTER) leave the denominator instead of counting as "chose something else". The
    18 September runs had none, so both functions agree on the paper's data.
    """
    rows = list(rows)
    total = option_count(rows, options)
    sentinels = sum(
        v for row in rows for k, v in parse_options(row["options"]).items() if k.isupper()
    )
    return Count(total.numerator, total.denominator - sentinels)


def law_side_count(rows: Iterable[Cell]) -> Count:
    """Law-side answers over scored answers (the unscored subject-advice role has none)."""
    rows = list(rows)
    numerator = sum(int(r["law_side"]) for r in rows)
    denominator = sum(int(r["scored"]) for r in rows)
    if not denominator:
        raise MissingSelection("no scored answers in the selection")
    return Count(numerator, denominator)


def pooled_law_side(
    cells: Iterable[Cell],
    *,
    model: str,
    cases: Sequence[str],
    roles: Sequence[str],
    hindsight: Sequence[str] = ("stripped", "carried"),
) -> Count:
    """Law-side answers summed over several cases. Every case must have every requested
    (role, hindsight) cell for this model; a missing one raises instead of shrinking the sum."""
    cells = list(cells)
    rows = [
        row
        for case in cases
        for row in select(cells, case=case, model=model, roles=roles, hindsight=hindsight)
    ]
    return law_side_count(rows)


def dialogue_status_count(
    rows: Iterable[Cell],
    *,
    model: str,
    order: str,
    stage: str,
    statuses: Sequence[str],
    exclude_topics: Sequence[str] = ("little_rock_crowd",),
) -> Count:
    """Forced dialogue answers with one of `statuses`, out of every forced answer (replies
    without a letter and empty replies stay in the denominator)."""
    keys = ("resist", "lawful", "comply", "no_letter", "empty")
    sel = [
        r
        for r in rows
        if r["model"] == model
        and r["order"] == order
        and r["stage"] == stage
        and r["topic"] not in exclude_topics
    ]
    if not sel:
        raise MissingSelection(f"no dialogue rows: {model} {order} {stage}")
    return Count(
        sum(int(r[k]) for r in sel for k in statuses),
        sum(int(r[k]) for r in sel for k in keys),
    )
