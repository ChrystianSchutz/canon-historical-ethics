"""Pydantic schema for CANON case files.

A case file (``cases/*.yaml``) is the single source of truth for one historical
decision point. The schema is built so that paired frames differ *by construction*
only in the intervened variable:

* prompts are written once per role as templates;
* the ``hindsight`` axis inserts or removes one paragraph (``{hindsight}``);
* the ``identity`` axis substitutes the subject (``{subject}``).

Structured cases also vary record ordering/layout through ``wording_variant``;
every variant retains every record section. See ``canon.frames``.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUBJECT_PLACEHOLDER = "{subject}"
HINDSIGHT_PLACEHOLDER = "{hindsight}"
RECORD_PLACEHOLDER = "{record}"
MAX_OPTIONS = 26

_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")
_MIN_NAME_PART_LENGTH = 3


class Role(StrEnum):
    OBSERVER = "observer"
    ADVISOR_ACTOR = "advisor_actor"
    ADVISOR_STATE = "advisor_state"
    EXECUTOR = "executor"
    ADVISOR_SUBJECT = "advisor_subject"


# Institutional action roles share an answer set. Subject advice has its own choices.
ACTION_ROLES = frozenset({Role.ADVISOR_STATE, Role.EXECUTOR})
CHOICE_ROLES = ACTION_ROLES | {Role.ADVISOR_SUBJECT}
# Roles answering on the moral scale.
SCALE_ROLES = frozenset({Role.OBSERVER, Role.ADVISOR_ACTOR})


class Hindsight(StrEnum):
    CARRIED = "carried"
    STRIPPED = "stripped"


class Identity(StrEnum):
    NAMED = "named"
    ANONYMOUS = "anonymous"


class PersonalConsequence(StrEnum):
    NONE = "none"
    DISCIPLINARY = "disciplinary"
    DISMISSAL = "dismissal"
    CRIMINAL = "criminal"


class EvaluatedAct(StrEnum):
    """What the observer's moral-scale question evaluates.

    ``resistance``: the act of refusing, defying or breaking the law or order in question.
    ``enforcement``: the authority's measure that applies the law or order.
    ``advisor_actor`` questions always evaluate resistance.
    """

    RESISTANCE = "resistance"
    ENFORCEMENT = "enforcement"


class ExpectedDirection(StrEnum):
    """The case author's documented expectation, used only for pair contrasts (M12).

    It is an explicit, contestable research hypothesis with a written rationale, never a
    primary score or an ethics answer key.
    """

    RESISTANCE_BETTER_SUPPORTED = "resistance_better_supported"
    COMPLIANCE_BETTER_SUPPORTED = "compliance_better_supported"
    CONTESTED = "contested"


class MetricId(StrEnum):
    M1 = "M1"  # hindsight_effect
    M2 = "M2"  # role_gap (descriptive)
    M3 = "M3"  # enforcement_incoherence (headline)
    M4 = "M4"  # invented_exit_rate
    M5 = "M5"  # stated_vs_revealed
    M6 = "M6"  # deflection_asymmetry
    M7 = "M7"  # escalation_threshold
    M8 = "M8"  # outcome_bias
    M9 = "M9"  # instability
    M10 = "M10"  # name_effect (named vs anonymous)
    M11 = "M11"  # prompt_sensitivity (within-role answer distributions)
    M12 = "M12"  # pair_contrast (ordinal compliance ranks across matched pairs)


METRIC_NAMES: dict[MetricId, str] = {
    MetricId.M1: "hindsight_effect",
    MetricId.M2: "role_gap",
    MetricId.M3: "enforcement_incoherence",
    MetricId.M4: "invented_exit_rate",
    MetricId.M5: "stated_vs_revealed",
    MetricId.M6: "deflection_asymmetry",
    MetricId.M7: "escalation_threshold",
    MetricId.M8: "outcome_bias",
    MetricId.M9: "instability",
    MetricId.M10: "name_effect",
    MetricId.M11: "prompt_sensitivity",
    MetricId.M12: "pair_contrast",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScalePoint(StrictModel):
    id: str
    text: str


# Frozen ordinal scale for evaluative roles. Never permuted, identical in every frame.
MORAL_SCALE: tuple[ScalePoint, ...] = (
    ScalePoint(id="impermissible", text="Morally impermissible"),
    ScalePoint(
        id="wrong_mitigated",
        text="Wrong in principle, with significant mitigating circumstances",
    ),
    ScalePoint(id="permissible", text="Morally permissible"),
    ScalePoint(id="justified", text="Morally justified"),
    ScalePoint(id="required", text="Morally required"),
)


class Source(StrictModel):
    citation: str = Field(min_length=1)
    url: str | None = None
    locator: str | None = None


class Fact(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    text: str = Field(min_length=1)
    sources: list[Source] = Field(min_length=1)
    verified_by: str | None = None
    verified_at: date | None = None

    @property
    def is_verified(self) -> bool:
        return self.verified_by is not None and self.verified_at is not None


class SubjectOption(StrictModel):
    """A personal course of action, not a ranking of institutional enforcement."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    text: str = Field(min_length=1)
    legally_available: bool
    within_role_authority: bool
    personal_consequence: PersonalConsequence
    historical_actual: bool = False


class Option(SubjectOption):
    """A concrete institutional action; its rank never applies to subject advice."""

    deference_rank: int = Field(ge=1, description="1 = strongest enforcement of the law")
    upholds_order: bool | None = Field(
        default=None,
        description=(
            "True if choosing this option carries out or upholds the contested law, order or "
            "measure; False if it declines, refuses or reverses it. Required in cases with "
            "action-role cells."
        ),
    )


class Subject(StrictModel):
    named: str = Field(min_length=1)
    anonymous: str = Field(min_length=1)


class Expectation(StrictModel):
    direction: ExpectedDirection
    rationale: str = Field(min_length=1)
    pair_id: str | None = Field(default=None, pattern=r"^P-[A-Z0-9-]+$")


class RoleTemplate(StrictModel):
    role: Role
    prompt: str = Field(min_length=1)


class RecordSection(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    text: str = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)


class WordingVariant(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    section_order: list[str] = Field(min_length=1)
    presentation: str = Field(default="paragraphs", pattern=r"^(paragraphs|bullets)$")


class OmittedRole(StrictModel):
    role: Role
    not_applicable_reason: str = Field(min_length=1)


class Cell(StrictModel):
    role: Role
    identity: Identity
    hindsight: Hindsight
    wording_variant: str = Field(default="default", pattern=r"^[a-z][a-z0-9_]*$")

    @property
    def id(self) -> str:
        base = f"{self.role}.{self.identity}.{self.hindsight}"
        return base if self.wording_variant == "default" else f"{base}.{self.wording_variant}"


class ConsistencyRule(StrictModel):
    """Per-case answer contrast. M3 specifies stance/action tensions whose
    interpretation depends on role duties, not automatic findings of hypocrisy."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)
    metric: MetricId
    if_cell: str
    if_answers: list[str] = Field(min_length=1)
    then_cell: str
    then_answers: list[str] = Field(min_length=1)


class Case(StrictModel):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")
    title: str = Field(min_length=1)
    decision_date: date
    canary: str = Field(min_length=1)
    hypothesis_link: list[MetricId] = Field(min_length=1)
    subject: Subject
    hindsight_verdict: str = Field(min_length=1)
    observer_evaluates: EvaluatedAct | None = Field(
        default=None,
        description="What the observer question evaluates; required when observer cells exist.",
    )
    expectation: Expectation | None = None
    recognition_keywords: list[str] = Field(
        default_factory=list,
        description="Case-insensitive terms that count as recognition in a probe answer.",
    )
    facts: list[Fact] = Field(min_length=1)
    options: list[Option] = Field(default_factory=list)
    subject_options: list[SubjectOption] = Field(default_factory=list)
    record: list[RecordSection] = Field(default_factory=list)
    wording_variants: list[WordingVariant] = Field(default_factory=list)
    omitted_roles: list[OmittedRole] = Field(default_factory=list)
    templates: list[RoleTemplate] = Field(min_length=1)
    cells: list[Cell] = Field(min_length=1)
    consistency_rules: list[ConsistencyRule] = Field(default_factory=list)
    lint_allow: list[str] = Field(
        default_factory=list,
        description="Evaluative terms allowed in stripped frames because contemporaries used them.",
    )

    @property
    def is_verified(self) -> bool:
        return all(fact.is_verified for fact in self.facts)

    def template_for(self, role: Role) -> RoleTemplate:
        return next(t for t in self.templates if t.role == role)

    def options_for(self, role: Role) -> list[Option] | list[SubjectOption]:
        return self.subject_options if role is Role.ADVISOR_SUBJECT else self.options

    def cell(self, cell_id: str) -> Cell:
        for cell in self.cells:
            if cell.id == cell_id:
                return cell
        raise KeyError(f"case {self.id} has no cell {cell_id!r}")

    @model_validator(mode="after")
    def _check_integrity(self) -> Self:
        _require_unique("fact id", [f.id for f in self.facts])
        _require_unique("option id", [o.id for o in self.options])
        _require_unique("subject option id", [o.id for o in self.subject_options])
        _require_unique("option deference_rank", [o.deference_rank for o in self.options])
        _require_unique("template role", [t.role for t in self.templates])
        _require_unique("cell", [c.id for c in self.cells])
        _require_unique("consistency rule id", [r.id for r in self.consistency_rules])
        _require_unique("record section", [r.id for r in self.record])
        _require_unique("wording variant", [v.id for v in self.wording_variants])
        _require_unique("omitted role", [o.role for o in self.omitted_roles])

        if max(len(self.options), len(self.subject_options)) > MAX_OPTIONS:
            raise ValueError(f"at most {MAX_OPTIONS} options are supported")

        template_roles = {t.role for t in self.templates}
        for cell in self.cells:
            if cell.role not in template_roles:
                raise ValueError(f"cell {cell.id!r} has no template for role {cell.role!r}")
            if cell.role in CHOICE_ROLES and len(self.options_for(cell.role)) < 2:
                raise ValueError(f"cell {cell.id!r} is an action role and needs at least 2 options")

        cell_roles = {c.role for c in self.cells}
        if Role.OBSERVER in cell_roles and self.observer_evaluates is None:
            raise ValueError(
                "observer_evaluates is required when observer cells exist "
                "(resistance or enforcement), so compliance ranks have a defined direction"
            )
        if cell_roles & ACTION_ROLES:
            if any(o.upholds_order is None for o in self.options):
                raise ValueError("every option needs upholds_order when action-role cells exist")
            if {o.upholds_order for o in self.options} != {True, False}:
                raise ValueError(
                    "action options must include at least one option that upholds the order "
                    "and one that does not"
                )

        if self.record or self.wording_variants:
            self._check_record_design(template_roles)
        elif any(cell.wording_variant != "default" for cell in self.cells):
            raise ValueError("non-default wording cells require record and wording_variants")

        for option in [*self.options, *self.subject_options]:
            _check_text(
                option.text, f"option {option.id}", self.subject.named, require_hindsight=False
            )

        for template in self.templates:
            _check_text(
                template.prompt,
                f"template {template.role!r}",
                self.subject.named,
                require_hindsight=True,
                allow_record=bool(self.record),
            )
            if self.record and template.prompt.count(RECORD_PLACEHOLDER) != 1:
                raise ValueError(f"template {template.role} must contain {{record}} exactly once")
        _check_text(
            self.hindsight_verdict, "hindsight_verdict", self.subject.named, require_hindsight=False
        )

        cells = {c.id: c for c in self.cells}
        scale_ids = {p.id for p in MORAL_SCALE}
        for rule in self.consistency_rules:
            for cell_id, answers in (
                (rule.if_cell, rule.if_answers),
                (rule.then_cell, rule.then_answers),
            ):
                rule_cell = cells.get(cell_id)
                if rule_cell is None:
                    raise ValueError(
                        f"consistency rule {rule.id!r} references unknown cell {cell_id!r}"
                    )
                if rule.metric is MetricId.M3 and rule_cell.role is Role.ADVISOR_SUBJECT:
                    raise ValueError("M3 cannot equate subject harm-minimization with enforcement")
                valid = (
                    {o.id for o in self.options_for(rule_cell.role)}
                    if rule_cell.role in CHOICE_ROLES
                    else scale_ids
                )
                unknown = sorted(set(answers) - valid)
                if unknown:
                    raise ValueError(
                        f"consistency rule {rule.id!r} uses answers {unknown} "
                        f"not valid for {cell_id!r}"
                    )

        self._check_hypothesis_link()
        return self

    def _check_record_design(self, template_roles: set[Role]) -> None:
        if not self.record or not self.wording_variants:
            raise ValueError("record and wording_variants must be supplied together")
        section_ids = {r.id for r in self.record}
        fact_ids = {f.id for f in self.facts}
        for section in self.record:
            if set(section.fact_ids) - fact_ids:
                raise ValueError(f"record section {section.id} references unknown facts")
            _check_text(
                section.text, f"record {section.id}", self.subject.named, require_hindsight=False
            )
        for variant in self.wording_variants:
            if (
                len(variant.section_order) != len(section_ids)
                or set(variant.section_order) != section_ids
            ):
                raise ValueError(
                    f"wording variant {variant.id} must include every record section once"
                )
        variant_ids = {v.id for v in self.wording_variants}
        used_roles = {c.role for c in self.cells}
        omitted = {o.role for o in self.omitted_roles}
        if used_roles & omitted or used_roles | omitted != set(Role):
            raise ValueError(
                "every role must be present or have a not_applicable_reason, never both"
            )
        if template_roles != used_roles:
            raise ValueError("each template must have cells")
        for cell in self.cells:
            if cell.wording_variant not in variant_ids:
                raise ValueError(f"cell {cell.id} references unknown wording variant")
        # A selected role must have the complete identity x hindsight x wording matrix.
        expected = {
            Cell(role=r, identity=i, hindsight=h, wording_variant=v).id
            for r in used_roles
            for i in Identity
            for h in Hindsight
            for v in variant_ids
        }
        if {c.id for c in self.cells} != expected:
            raise ValueError("each included role needs the full identity/hindsight/wording matrix")

    def _check_hypothesis_link(self) -> None:
        """Each linked metric must be computable from this case."""
        cell_ids = {c.id for c in self.cells}
        roles = {c.role for c in self.cells}

        def has_pair(axis: str) -> bool:
            for cell in self.cells:
                if axis == "hindsight" and cell.hindsight is Hindsight.STRIPPED:
                    twin = cell.model_copy(update={"hindsight": Hindsight.CARRIED})
                elif axis == "identity" and cell.identity is Identity.NAMED:
                    twin = cell.model_copy(update={"identity": Identity.ANONYMOUS})
                else:
                    continue
                if twin.id in cell_ids:
                    return True
            return False

        requirements: dict[MetricId, tuple[bool, str]] = {
            MetricId.M1: (
                has_pair("hindsight"),
                "needs a carried/stripped pair with the same role and identity",
            ),
            MetricId.M2: (
                bool(roles & ACTION_ROLES) and bool(roles - CHOICE_ROLES),
                "needs both an evaluative role and an action role",
            ),
            MetricId.M3: (
                any(r.metric is MetricId.M3 for r in self.consistency_rules),
                "needs a consistency rule with metric M3",
            ),
            MetricId.M4: (
                any(not o.legally_available or not o.within_role_authority for o in self.options),
                "needs an option that is not legally available or not within role authority",
            ),
            MetricId.M7: (False, "the escalation ladder is not modelled in the v0.1 schema"),
            MetricId.M8: (False, "outcome-matched pairs are not modelled in the v0.1 schema"),
            MetricId.M10: (
                has_pair("identity"),
                "needs a named/anonymous pair with the same role and hindsight",
            ),
            MetricId.M11: (
                len({c.wording_variant for c in self.cells}) > 1,
                "needs multiple wording variants for the same role, identity and hindsight",
            ),
            MetricId.M12: (
                self.expectation is not None
                and self.expectation.pair_id is not None
                and self.expectation.direction is not ExpectedDirection.CONTESTED,
                "needs an expectation with a pair_id and a non-contested direction",
            ),
        }
        for metric in self.hypothesis_link:
            satisfied, reason = requirements.get(metric, (True, ""))
            if not satisfied:
                raise ValueError(f"hypothesis_link {metric}: {reason}")


def case_json_schema() -> dict[str, Any]:
    """JSON Schema for case files, for editor autocompletion (``canon schema``)."""
    schema = Case.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "CANON case",
        **{k: v for k, v in schema.items() if k != "title"},
    }


def _require_unique(label: str, values: list[object]) -> None:
    duplicates = sorted(str(v) for v, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate {label}: {duplicates}")


def _check_text(
    text: str,
    label: str,
    named_subject: str,
    *,
    require_hindsight: bool,
    allow_record: bool = False,
) -> None:
    placeholders = _PLACEHOLDER_RE.findall(text)
    allowed = {SUBJECT_PLACEHOLDER, HINDSIGHT_PLACEHOLDER}
    if allow_record:
        allowed.add(RECORD_PLACEHOLDER)
    unknown = sorted(set(placeholders) - allowed)
    if unknown:
        raise ValueError(f"{label} contains unknown placeholders {unknown}")

    hindsight_count = placeholders.count(HINDSIGHT_PLACEHOLDER)
    if require_hindsight:
        if hindsight_count != 1:
            raise ValueError(f"{label} must contain {HINDSIGHT_PLACEHOLDER} exactly once")
        line = next(ln for ln in text.splitlines() if HINDSIGHT_PLACEHOLDER in ln)
        if line.strip() != HINDSIGHT_PLACEHOLDER:
            raise ValueError(
                f"{label}: {HINDSIGHT_PLACEHOLDER} must stand alone on its own line (one paragraph)"
            )
    elif hindsight_count:
        raise ValueError(f"{label} must not contain {HINDSIGHT_PLACEHOLDER}")

    text_without_placeholders = _PLACEHOLDER_RE.sub(" ", text)
    for part in _name_parts(named_subject):
        if re.search(rf"\b{re.escape(part)}\b", text_without_placeholders):
            raise ValueError(
                f"{label} contains the named subject {part!r} literally; "
                f"use {SUBJECT_PLACEHOLDER} so the identity axis stays clean"
            )


def _name_parts(name: str) -> list[str]:
    parts = [name, *name.split()]
    return [p for p in dict.fromkeys(parts) if len(p) >= _MIN_NAME_PART_LENGTH]
