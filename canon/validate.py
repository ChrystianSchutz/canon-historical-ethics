"""Load and validate case files."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from canon.lint import lint_case
from canon.pairs import match_pair
from canon.schema import Case, ExpectedDirection
from canon.skeleton import find_todo_markers

CASE_SUFFIXES = frozenset({".yaml", ".yml"})


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class CaseValidationError(Exception):
    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("\n".join(str(i) for i in issues))
        self.issues = issues


def discover_case_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.suffix in CASE_SUFFIXES))
        elif path.is_file():
            files.append(path)
    return files


def load_case(path: Path) -> Case:
    with path.open(encoding="utf-8") as fh:
        return Case.model_validate(yaml.safe_load(fh))


def validate_paths(
    paths: Iterable[Path], *, require_verified: bool = False, check_pairs: bool = True
) -> tuple[list[Case], list[Issue]]:
    """Validate case files. Cases that parse are returned even if they have issues."""
    paths = list(paths)
    issues = [Issue(p, "path does not exist") for p in paths if not p.exists()]
    cases: list[Case] = []
    seen: dict[str, Path] = {}

    for file in discover_case_files(p for p in paths if p.exists()):
        try:
            case = load_case(file)
        except yaml.YAMLError as exc:
            issues.append(Issue(file, f"invalid YAML: {exc}"))
            continue
        except ValidationError as exc:
            for err in exc.errors():
                location = ".".join(str(part) for part in err["loc"]) or "<case>"
                issues.append(Issue(file, f"{location}: {err['msg']}"))
            continue

        if case.id in seen:
            issues.append(Issue(file, f"duplicate case id {case.id!r} (also in {seen[case.id]})"))
            continue
        seen[case.id] = file

        issues.extend(Issue(file, message) for message in find_todo_markers(case))
        issues.extend(Issue(file, message) for message in lint_case(case))
        if require_verified:
            issues.extend(
                Issue(file, f"fact {fact.id!r} is not verified by a human")
                for fact in case.facts
                if not fact.is_verified
            )
        cases.append(case)

    if check_pairs:
        issues.extend(_pair_issues(cases, seen))
    return cases, issues


def _pair_issues(cases: list[Case], files: dict[str, Path]) -> list[Issue]:
    """A matched pair (M12) needs exactly one case expected to favor resistance and one
    expected to favor compliance, so the bank can falsify a one-directional profile."""
    pairs: dict[str, list[Case]] = defaultdict(list)
    for case in cases:
        if case.expectation is not None and case.expectation.pair_id is not None:
            pairs[case.expectation.pair_id].append(case)
    wanted = {
        ExpectedDirection.RESISTANCE_BETTER_SUPPORTED,
        ExpectedDirection.COMPLIANCE_BETTER_SUPPORTED,
    }
    issues: list[Issue] = []
    for pair_id, members in sorted(pairs.items()):
        directions = [c.expectation.direction for c in members if c.expectation is not None]
        if len(members) != 2 or set(directions) != wanted:
            ids = ", ".join(c.id for c in members)
            issues.append(
                Issue(
                    files[members[0].id],
                    f"pair {pair_id} needs exactly one resistance-expected and one "
                    f"compliance-expected case; found [{ids}]",
                )
            )
            continue
        by_direction = {c.expectation.direction: c for c in members if c.expectation is not None}
        match = match_pair(
            by_direction[ExpectedDirection.RESISTANCE_BETTER_SUPPORTED],
            by_direction[ExpectedDirection.COMPLIANCE_BETTER_SUPPORTED],
        )
        if not match.matched_roles or not match.wording_variants:
            reasons = "; ".join(f"{r}: {why}" for r, why in match.excluded_roles.items())
            issues.append(
                Issue(
                    files[members[0].id],
                    f"pair {pair_id} has no structurally matched role with a shared wording "
                    f"variant ({reasons or 'no shared scale or action roles'})",
                )
            )
    return issues


def load_cases(paths: Iterable[Path], *, check_pairs: bool = True) -> list[Case]:
    cases, issues = validate_paths(paths, check_pairs=check_pairs)
    if issues:
        raise CaseValidationError(issues)
    return cases
