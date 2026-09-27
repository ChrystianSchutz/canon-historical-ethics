"""Structural matching of M12 pairs.

An `expectation.pair_id` only names two cases. These checks decide, per role, whether the two
cases ask a comparable question, so a pair contrast is never reported for a role whose
questions differ in the variables the design treats as confounds. They are mechanical
minimums: whether both cases describe the *same kind of act* remains a human review item.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from canon.schema import ACTION_ROLES, SCALE_ROLES, Case, PersonalConsequence, Role

PAIR_ROLES = SCALE_ROLES | ACTION_ROLES


def refusal_profile(case: Case) -> frozenset[tuple[bool, bool]]:
    """Kinds of non-upholding options: (legally_available, carries a personal consequence)."""
    return frozenset(
        (o.legally_available, o.personal_consequence is not PersonalConsequence.NONE)
        for o in case.options
        if o.upholds_order is False
    )


def _describe(profile: frozenset[tuple[bool, bool]]) -> str:
    labels = {
        (True, False): "lawful costless exit",
        (True, True): "lawful costly exit",
        (False, False): "unlawful costless refusal",
        (False, True): "unlawful costly refusal",
    }
    return ", ".join(sorted(labels[p] for p in profile)) or "none"


@dataclass(frozen=True)
class PairMatch:
    resistance: Case
    compliance: Case
    matched_roles: tuple[Role, ...]
    excluded_roles: dict[Role, str] = field(default_factory=dict)
    wording_variants: tuple[str, ...] = ()


def match_pair(resistance: Case, compliance: Case) -> PairMatch:
    roles_r = {c.role for c in resistance.cells} & PAIR_ROLES
    roles_c = {c.role for c in compliance.cells} & PAIR_ROLES
    excluded: dict[Role, str] = {}
    for role in sorted(roles_r ^ roles_c):
        owner = resistance.id if role in roles_r else compliance.id
        excluded[role] = f"only {owner} has {role} cells"

    matched: list[Role] = []
    for role in sorted(roles_r & roles_c):
        if role is Role.OBSERVER and resistance.observer_evaluates != compliance.observer_evaluates:
            excluded[role] = (
                f"observer questions evaluate different acts ({resistance.observer_evaluates} "
                f"versus {compliance.observer_evaluates})"
            )
            continue
        if role in ACTION_ROLES:
            left, right = refusal_profile(resistance), refusal_profile(compliance)
            if left != right:
                excluded[role] = (
                    f"non-upholding options differ: {resistance.id} offers {_describe(left)}; "
                    f"{compliance.id} offers {_describe(right)}"
                )
                continue
            if not all(
                any(o.upholds_order and o.legally_available for o in case.options)
                for case in (resistance, compliance)
            ):
                excluded[role] = "both cases need a lawful option that upholds the order"
                continue
        matched.append(role)

    variants_r = {c.wording_variant for c in resistance.cells}
    variants_c = {c.wording_variant for c in compliance.cells}
    return PairMatch(
        resistance,
        compliance,
        tuple(matched),
        excluded,
        tuple(sorted(variants_r & variants_c)),
    )
