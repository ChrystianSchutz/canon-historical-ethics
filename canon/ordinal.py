"""Ordinal statistics for matched-pair contrasts.

Answer letters are ordered categories, never interval values: nothing here averages them.
The functions compare category ranks (probability of superiority), shifts between cell
medians (Wilcoxon signed-rank), and adjust p-values across a family (Holm).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from math import comb, erf, sqrt
from statistics import median_low

# Exact enumeration of sign assignments up to this many non-zero differences.
EXACT_LIMIT = 25


def superiority(left: Sequence[int], right: Sequence[int]) -> float | None:
    """P(X > Y) + 0.5 P(X = Y) for X from ``left`` and Y from ``right``; 0.5 means no shift."""
    if not left or not right:
        return None
    wins = sum((x > y) + 0.5 * (x == y) for x in left for y in right)
    return wins / (len(left) * len(right))


def median_category(values: Sequence[int]) -> int | None:
    """The lower median, so the result is always an observed category."""
    return median_low(values) if values else None


@dataclass(frozen=True)
class SignedRank:
    n: int  # non-zero differences used
    zeros: int
    w_plus: float
    p_value: float | None  # two-sided; None when every difference is zero
    exact: bool


def _average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def sign_test(differences: Sequence[float]) -> SignedRank:
    """Two-sided exact sign test, using only the direction of each difference.

    Reported beside `wilcoxon_signed_rank` as a robustness check, because the signed-rank test
    is not purely ordinal in the way the design assumes. It ranks the *magnitudes* of differences
    between encoded categories, so its p-value can move with the spacing chosen for the moral
    scale even when the order of the categories is untouched: for shifts of (0->2) five times
    and (4->3) once, coding the scale [0,1,2,3,4] gives p=0.0625, while the equally
    order-preserving [0,1,2,3,100] gives p=0.531. The sign test cannot move that way, so a
    disagreement between the two is a signal that the spacing assumption is doing the work.

    `w_plus` carries the number of positive differences rather than a rank sum.
    """
    nonzero = [d for d in differences if d != 0]
    zeros = len(differences) - len(nonzero)
    n = len(nonzero)
    if n == 0:
        return SignedRank(0, zeros, 0.0, None, True)
    positive = sum(1 for d in nonzero if d > 0)
    tail = min(positive, n - positive)
    p = min(1.0, 2 * sum(comb(n, k) for k in range(tail + 1)) / 2**n)
    return SignedRank(n, zeros, float(positive), p, True)


def wilcoxon_signed_rank(differences: Sequence[float]) -> SignedRank:
    """Two-sided Wilcoxon signed-rank test; zeros dropped, tied ranks averaged.

    Exact over all sign assignments of the observed ranks for small n, otherwise the normal
    approximation with a tie correction.

    **Assumption to declare when reporting:** the differences are computed from integer codes
    assigned to ordered moral categories, and this test ranks their magnitudes. It therefore
    depends on the spacing between those categories, not only on their order. Report
    `sign_test` and `superiority` alongside it; both use order alone.
    """
    nonzero = [d for d in differences if d != 0]
    zeros = len(differences) - len(nonzero)
    n = len(nonzero)
    if n == 0:
        return SignedRank(0, zeros, 0.0, None, True)
    ranks = _average_ranks([abs(d) for d in nonzero])
    w_plus = sum(r for r, d in zip(ranks, nonzero, strict=True) if d > 0)

    if n <= EXACT_LIMIT:
        # Ranks are multiples of 0.5, so count subset sums on doubled integer ranks.
        doubled = [round(2 * r) for r in ranks]
        counts: Counter[int] = Counter({0: 1})
        for r in doubled:
            step: Counter[int] = Counter()
            for total, ways in counts.items():
                step[total] += ways
                step[total + r] += ways
            counts = step
        observed = round(2 * w_plus)
        total_ways = 2**n
        lower = sum(w for s, w in counts.items() if s <= observed) / total_ways
        upper = sum(w for s, w in counts.items() if s >= observed) / total_ways
        return SignedRank(n, zeros, w_plus, min(1.0, 2 * min(lower, upper)), True)

    mean_w = n * (n + 1) / 4
    tie_term = sum(t**3 - t for t in Counter(ranks).values()) / 48
    variance = n * (n + 1) * (2 * n + 1) / 24 - tie_term
    if variance <= 0:
        return SignedRank(n, zeros, w_plus, None, False)
    z = (abs(w_plus - mean_w) - 0.5) / sqrt(variance)
    p = 2 * (1 - 0.5 * (1 + erf(max(z, 0.0) / sqrt(2))))
    return SignedRank(n, zeros, w_plus, min(1.0, p), False)


def holm[K: Hashable](p_values: Mapping[K, float]) -> dict[K, float]:
    """Holm-Bonferroni adjusted p-values for one family of tests."""
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    m = len(ordered)
    adjusted: dict[K, float] = {}
    running = 0.0
    for i, (key, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[key] = running
    return adjusted
