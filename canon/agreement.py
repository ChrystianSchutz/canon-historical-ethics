"""Human validation of the LLM judge: sample, code by hand, compute Cohen's kappa."""

from __future__ import annotations

import csv
import random
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from canon.judge import KAPPA_THRESHOLD, NO_STANCE
from canon.summary import AnswerRecord

SHEET_COLUMNS = (
    "sample_id",
    "model",
    "case_id",
    "cell_id",
    "turn1_response",
    "judge_response_class",
    "judge_stance",
    "human_response_class",
    "human_stance",
)


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two non-empty label sequences of equal length")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    counts_a, counts_b = Counter(a), Counter(b)
    expected = sum(counts_a[k] * counts_b[k] for k in counts_a) / (n * n)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def select_for_validation(
    records: Iterable[AnswerRecord], fraction: float = 0.2, seed: int = 0
) -> list[AnswerRecord]:
    judged = sorted(
        (r for r in records if r.response_class is not None), key=lambda r: (r.model, r.sample_id)
    )
    if not judged:
        return []
    k = max(1, round(fraction * len(judged)))
    return random.Random(seed).sample(judged, k)


def write_validation_sheet(records: Iterable[AnswerRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        for r in records:
            writer.writerow(
                {
                    "sample_id": r.sample_id,
                    "model": r.model,
                    "case_id": r.case_id,
                    "cell_id": r.cell_id,
                    "turn1_response": r.turn1 or "",
                    "judge_response_class": r.response_class or "",
                    "judge_stance": r.stance or NO_STANCE,
                    "human_response_class": "",
                    "human_stance": "",
                }
            )


@dataclass(frozen=True)
class AgreementReport:
    n: int
    class_kappa: float | None
    stance_n: int
    stance_kappa: float | None
    # Distinct human labels in each coded column. Kappa is undefined-to-meaningless when the
    # human coded only one class: agreement is then guaranteed and carries no information.
    class_labels: int = 0
    stance_labels: int = 0

    @property
    def degenerate(self) -> bool:
        return self.class_labels < 2 or self.stance_labels < 2

    @property
    def passed(self) -> bool:
        """Both columns must be coded, non-degenerate and at or above the kappa threshold.

        A single-class sheet must not pass: `cohen_kappa(['R0'], ['R0'])` is 1.0, and an
        unfilled stance column must not be ignored, or one row could validate the judge.
        """
        kappas = [self.class_kappa, self.stance_kappa]
        if any(k is None for k in kappas) or self.degenerate:
            return False
        return all(k >= KAPPA_THRESHOLD for k in kappas if k is not None)


def read_agreement(path: Path) -> AgreementReport:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    classes = [
        (r["judge_response_class"], r["human_response_class"].strip().upper())
        for r in rows
        if r["human_response_class"].strip()
    ]
    stances = [
        (r["judge_stance"] or NO_STANCE, r["human_stance"].strip() or NO_STANCE)
        for r in rows
        if r["human_stance"].strip()
    ]
    return AgreementReport(
        n=len(classes),
        class_kappa=cohen_kappa(*zip(*classes, strict=True)) if classes else None,
        stance_n=len(stances),
        stance_kappa=cohen_kappa(*zip(*stances, strict=True)) if stances else None,
        class_labels=len({human for _, human in classes}),
        stance_labels=len({human for _, human in stances}),
    )
