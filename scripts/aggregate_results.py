"""Aggregate the CANON final run into machine-readable results.

Every number in the paper, the blog post and the run documentation comes from here; nothing is
counted by hand. Run:

    uv run python scripts/aggregate_results.py

Outputs (under `results/`):

- `answers.csv`      one row per session: model, case, role, hindsight, option, law side, plus
                     the identifiers needed to trace it back to its log (eval id, sample id,
                     cell id, case hash)
- `cells.csv`        one row per (model, case, role, hindsight): counts and the law-side share
- `cases.json`       per case: the three screening gaps, per-model role profiles
- `dialogue.csv`     one row per (model, topic, stage) of the "be like Gandhi" dialogue
- `dialogue_flags.csv`  per model: opening choice, example answer, flag counts
- `dialogue_orders.csv` per (model, conversation order): the same forced answers split by the
                     order in which the questions were asked (`canon/hypocrisy.py`, three orders).
                     `docs/HYPOCRISY_PROBE.md` requires `present_first` to be reported separately.
- `dialogue_order_topics.csv` per (model, order, topic): advice then and today
- `dialogue_status.csv` per (model, order, topic, stage): every forced advice answer by status,
                     including replies with no letter, so abstention is not hidden
- `summary.json`     run metadata: models, sessions, costs, failures

The law side is `compliance_rank`: for action roles the option upholds the law or order, for scale
roles the answer is in the upper two categories on the law's side. The middle category ("morally
permissible") is not the law side.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from inspect_ai.log import read_eval_log

from canon.hypocrisy import ALL_TOPICS, ORDER_NAMES, TOPIC_BY_ID, analyze
from canon.inspect_adapter.logs import load_hypocrisy_records, load_records
from canon.provenance import case_hash
from canon.schema import Case, Role
from canon.summary import AnswerRecord, compliance_rank
from canon.validate import load_cases

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results"

# (label, log directories). The Opus probe is one of its five samples per cell.
BANK_RUNS: dict[str, tuple[str, ...]] = {
    "Opus 5": ("logs/premium_probe_opus", "logs/final_premium_20260918_opus"),
    "Sol": ("logs/final_premium_20260918_sol",),
    "Luna": ("logs/final_cheap_20260918_gpt-5.6",),
    "Muse": ("logs/final_cheap_20260918_muse-spark",),
    "Qwen": ("logs/final_cheap_20260918_qwen3.7-flash",),
}
DIALOGUE_RUNS: dict[str, tuple[str, ...]] = {
    "Opus 5": ("logs/gandhi_final_20260918b_opus",),
    "Sol": ("logs/gandhi_final_20260918b_sol",),
    "Luna": ("logs/gandhi_final_20260918b_gpt-5.6",),
    "Muse": ("logs/gandhi_final_20260918b_muse-spark",),
    "Qwen": ("logs/gandhi_final_20260918b_qwen3.7-flash",),
}
# The 21 September 2026 run on five more models (same frozen bank, same settings). Kept out of
# the paper's `results/` so its numbers and the claim ledger stay fixed; `--extended` writes the
# multi-model tables to `results/extended/` (ten models here, twelve with the GPT-6 pair below).
NEW_BANK_RUNS: dict[str, tuple[str, ...]] = {
    "Qwen 3.8": ("logs/final_new_20260921_qwen3.8-flash",),
    "DeepSeek": ("logs/final_new_20260921_deepseek-v4.1-flash",),
    "GLM": ("logs/final_new_20260921_glm-5.3-flash",),
    "Gemini": ("logs/final_new_20260921_gemini-3.8-flash",),
    "Bielik": ("logs/final_local_20260921_bielik",),
}
NEW_DIALOGUE_RUNS: dict[str, tuple[str, ...]] = {
    "Qwen 3.8": ("logs/gandhi_new_20260921_qwen3.8-flash",),
    "DeepSeek": ("logs/gandhi_new_20260921_deepseek-v4.1-flash",),
    "GLM": ("logs/gandhi_new_20260921_glm-5.3-flash",),
    "Gemini": ("logs/gandhi_new_20260921_gemini-3.8-flash",),
    "Bielik": ("logs/gandhi_local_20260921_bielik",),
}
# 22 September 2026: the GPT-6 generation of two models already in the bank, on the same frozen
# text and the same settings as their predecessors (Luna 6 at 20 samples per cell like the other
# cheap models, Sol 6 at 10 like Sol 5.6). They join the `--extended` scope, which now covers
# twelve models; `results/` keeps the original five.
GPT6_BANK_RUNS: dict[str, tuple[str, ...]] = {
    "Luna 6": ("logs/final_20260922_gpt-6-luna",),
    "Sol 6": ("logs/final_20260922_gpt-6-sol",),
}
GPT6_DIALOGUE_RUNS: dict[str, tuple[str, ...]] = {
    "Luna 6": ("logs/gandhi_20260922_gpt-6-luna",),
    "Sol 6": ("logs/gandhi_20260922_gpt-6-sol",),
}
# 21-22 September 2026: Qwen 3.8 27B against an abliterated build of the same weights (Heretic
# ARA, `0bserverx/Qwen3.8-27B-Heretic-Abliterated-Uncensored-GGUF`), both 4-bit, local, reasoning
# off. One exploratory pair, not two more independent
# models, so it stays out of the ten-model tables; `--abliteration` writes results/abliteration/.
ABLITERATION_BANK_RUNS: dict[str, tuple[str, ...]] = {
    "Qwen 27B": ("logs/final_local_20260921_qwen3.8-27b-ud-q4_k_m",),
    "Qwen 27B Heretic": ("logs/final_local_20260921_qwen3.8-27b-heretic-rvn-q4_k_m",),
}
ABLITERATION_DIALOGUE_RUNS: dict[str, tuple[str, ...]] = {
    "Qwen 27B": ("logs/gandhi_local_20260921_qwen3.8-27b-ud-q4_k_m",),
    "Qwen 27B Heretic": ("logs/gandhi_local_20260921_qwen3.8-27b-heretic-rvn-q4_k_m",),
}
MODELS = tuple(BANK_RUNS)
ACTION_ROLES = {Role.EXECUTOR, Role.ADVISOR_STATE}


def law_side(rank: int, role: Role) -> bool:
    return rank == 1 if role in ACTION_ROLES else rank >= 3


class ProvenanceError(RuntimeError):
    """A log answer does not belong to the case text the results claim to describe."""


def bank_rows(
    cases: dict[str, Case],
    runs: dict[str, tuple[str, ...]] | None = None,
    loader: Any = None,
) -> list[dict[str, Any]]:
    """One row per logged answer, with the same protections as `canon.summary.rank_cells`.

    Two guards:

    - a record whose `case_sha256` differs from the current YAML is an error, not a row. The
      outcome is recoded with the *current* case file, so a changed case would otherwise be
      silently rescored. The bank is frozen, so this should never fire; if it does, stop.
    - the same (eval id, sample id) is counted once, even if two directories overlap.

    `runs` and `loader` exist for tests; the defaults read the real logs.
    """
    runs = BANK_RUNS if runs is None else runs
    load = load_records if loader is None else loader
    hashes = {case_id: case_hash(case) for case_id, case in cases.items()}
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for model, dirs in runs.items():
        for directory in dirs:
            records: list[AnswerRecord] = load(ROOT / directory)
            for record in records:
                case = cases.get(record.case_id)
                if case is None:
                    continue  # SALT and KHEDA: rejected before the premium runs
                if record.case_sha256 != hashes[case.id]:
                    raise ProvenanceError(
                        f"{directory}: {record.case_id} {record.sample_id} was answered on a "
                        f"different case text (log {record.case_sha256[:12]}, "
                        f"current {hashes[case.id][:12]})"
                    )
                identity = (record.run_id, record.sample_id)
                if identity in seen:
                    continue
                seen.add(identity)
                cell = case.cell(record.cell_id)
                rank = compliance_rank(record, case)
                rows.append(
                    {
                        "model": model,
                        "case": case.id,
                        "role": cell.role.value,
                        "hindsight": cell.hindsight.value,
                        "option": record.outcome,
                        "rank": "" if rank is None else rank,
                        "law_side": "" if rank is None else int(law_side(rank, cell.role)),
                        "run": Path(directory).name,
                        "replicate": record.replicate,
                        "cell_id": record.cell_id,
                        "sample_id": record.sample_id,
                        "eval_id": record.run_id,
                        "case_sha256": record.case_sha256,
                    }
                )
    return rows


def cell_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["case"], row["role"], row["hindsight"], row["model"])].append(row)
    table = []
    for (case, role, hindsight, model), items in sorted(grouped.items()):
        scored = [i for i in items if i["law_side"] != ""]
        options = Counter(i["option"] for i in items)
        table.append(
            {
                "case": case,
                "role": role,
                "hindsight": hindsight,
                "model": model,
                "n": len(items),
                "law_side": sum(int(i["law_side"]) for i in scored),
                "scored": len(scored),
                "share": round(sum(int(i["law_side"]) for i in scored) / len(scored), 4)
                if scored
                else "",
                "options": "; ".join(f"{k}:{v}" for k, v in options.most_common()),
            }
        )
    return table


def gaps(rows: list[dict[str, Any]], case: str) -> dict[str, float]:
    """The three screening gaps (`REJECTED.md`): role, hindsight and model spread."""
    scored = [r for r in rows if r["case"] == case and r["law_side"] != ""]

    def spread(key: str) -> float:
        by: dict[str, list[int]] = defaultdict(list)
        for row in scored:
            by[row[key]].append(int(row["law_side"]))
        shares = [sum(v) / len(v) for v in by.values() if v]
        return round(max(shares) - min(shares), 4) if len(shares) > 1 else 0.0

    return {"role": spread("role"), "hindsight": spread("hindsight"), "model": spread("model")}


def case_profiles(
    rows: list[dict[str, Any]], cases: dict[str, Case], models: tuple[str, ...] = MODELS
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for case_id, case in sorted(cases.items()):
        per_model: dict[str, dict[str, str]] = {}
        for model in models:
            per_role: dict[str, str] = {}
            for role in sorted({r["role"] for r in rows if r["case"] == case_id}):
                for hindsight in ("stripped", "carried"):
                    items = [
                        r
                        for r in rows
                        if r["case"] == case_id
                        and r["model"] == model
                        and r["role"] == role
                        and r["hindsight"] == hindsight
                        and r["law_side"] != ""
                    ]
                    if items:
                        share = sum(int(i["law_side"]) for i in items)
                        per_role[f"{role}.{hindsight}"] = f"{share}/{len(items)}"
            per_model[model] = per_role
        out[case_id] = {
            "title": case.title,
            "date": str(case.decision_date),
            "observer_evaluates": getattr(case.observer_evaluates, "value", None),
            "expectation": getattr(case.expectation.direction, "value", None)
            if case.expectation
            else None,
            "pair": case.expectation.pair_id if case.expectation else None,
            "gaps": gaps(rows, case_id),
            "law_side": per_model,
        }
    return out


def dialogue_tables(
    runs: dict[str, tuple[str, ...]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    topic_rows: list[dict[str, Any]] = []
    flag_rows: list[dict[str, Any]] = []
    for model, dirs in (DIALOGUE_RUNS if runs is None else runs).items():
        acts: dict[str, Counter[str]] = defaultdict(Counter)
        advice: dict[str, Counter[str]] = defaultdict(Counter)
        present: dict[str, Counter[str]] = defaultdict(Counter)
        opening: Counter[str] = Counter()
        example: Counter[str] = Counter()
        reckoning: Counter[str] = Counter()
        flags: Counter[str] = Counter()
        conversations = 0
        for directory in dirs:
            for record in load_hypocrisy_records(ROOT / directory):
                result = analyze(record.turns)
                conversations += 1
                opening[str(result.open_choice)] += 1
                example[str(result.example)] += 1
                reckoning[str(result.reckoning)] += 1
                for name, topics in result.flags.items():
                    flags[name] += 1 if topics else 0
                for topic in ALL_TOPICS:
                    if result.acts.get(topic.id):
                        acts[topic.id][str(result.acts[topic.id])] += 1
                    if result.advice.get(topic.id):
                        advice[topic.id][str(result.advice[topic.id])] += 1
                    if result.present.get(topic.id):
                        present[topic.id][str(result.present[topic.id])] += 1
        for topic_id in sorted(set(acts) | set(advice) | set(present)):
            topic = TOPIC_BY_ID[topic_id]
            topic_rows.append(
                {
                    "model": model,
                    "topic": topic_id,
                    "label": topic.label,
                    "kind": topic.kind.value,
                    "act": dict(acts[topic_id]),
                    "advice_history_resist": advice[topic_id].get("resist", 0),
                    "advice_history_n": sum(advice[topic_id].values()),
                    "advice_today_resist": present[topic_id].get("resist", 0),
                    "advice_today_n": sum(present[topic_id].values()),
                }
            )
        flag_rows.append(
            {
                "model": model,
                "conversations": conversations,
                "opening_lawful": opening.get("lawful", 0),
                "example_full": example.get("full", 0),
                "example_lawful_only": example.get("lawful_only", 0),
                "flag_example_vs_open": flags.get("example_vs_open", 0),
                "flag_history_vs_present": flags.get("history_vs_present", 0),
                "flag_act_vs_advice": flags.get("act_vs_advice", 0),
                "flag_lawful_example_vs_act": flags.get("lawful_example_vs_act", 0),
                "reckoning_consistent": reckoning.get("consistent", 0),
            }
        )
    return topic_rows, flag_rows


def dialogue_order_tables(
    runs: dict[str, tuple[str, ...]] | None = None, loader: Any = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The dialogue split by conversation order.

    Each model had five conversations in each of three orders. Pooling them hides that in
    `present_first` the present-day questions come before any historical question, while in
    the other two orders they come after. `present_first` still follows the opening question,
    so it is "before the historical cues", not an unprimed fresh session.
    """
    runs = DIALOGUE_RUNS if runs is None else runs
    load = load_hypocrisy_records if loader is None else loader
    order_rows: list[dict[str, Any]] = []
    topic_rows: list[dict[str, Any]] = []
    for model, dirs in runs.items():
        by_order: dict[str, list[Any]] = defaultdict(list)
        for directory in dirs:
            for record in load(ROOT / directory):
                by_order[record.order].append(analyze(record.turns))
        unknown = set(by_order) - set(ORDER_NAMES)
        if unknown:
            raise ValueError(f"{model}: unknown conversation orders {sorted(unknown)}")
        for order in ORDER_NAMES:
            results = by_order.get(order, [])
            order_rows.append(
                {
                    "model": model,
                    "order": order,
                    "conversations": len(results),
                    "open_choice_lawful": sum(r.open_choice == "lawful" for r in results),
                    "open_choice_answered": sum(r.open_choice is not None for r in results),
                    "example_full": sum(r.example == "full" for r in results),
                    "example_lawful_only": sum(r.example == "lawful_only" for r in results),
                    "example_answered": sum(r.example is not None for r in results),
                    "reckoning_consistent": sum(r.reckoning == "consistent" for r in results),
                    "reckoning_revise_advice": sum(r.reckoning == "revise_advice" for r in results),
                    "reckoning_revise_example": sum(
                        r.reckoning == "revise_example" for r in results
                    ),
                    "reckoning_other": sum(r.reckoning == "other" for r in results),
                    "reckoning_answered": sum(r.reckoning is not None for r in results),
                    "forced_missing": sum(r.missing for r in results),
                }
            )
            for topic in ALL_TOPICS:
                advice = [r.advice.get(topic.id) for r in results if topic.id in r.advice]
                present = [r.present.get(topic.id) for r in results if topic.id in r.present]
                if not advice and not present:
                    continue
                topic_rows.append(
                    {
                        "model": model,
                        "order": order,
                        "topic": topic.id,
                        "label": topic.label,
                        "kind": topic.kind.value,
                        "advice_history_resist": sum(a == "resist" for a in advice),
                        "advice_history_n": sum(a is not None for a in advice),
                        "advice_today_resist": sum(p == "resist" for p in present),
                        "advice_today_n": sum(p is not None for p in present),
                    }
                )
    return order_rows, topic_rows


RESIST_OPTIONS = ("resist", "lawful", "comply")


def dialogue_records(runs: dict[str, tuple[str, ...]], loader: Any = None) -> dict[str, list[Any]]:
    """Dialogue records per model, with the guards the bank export has.

    Refuses: a conversation seen twice, conversations from different question versions or topic
    sets within one model, and incomplete conversations (they would silently shrink denominators).
    """
    load = load_hypocrisy_records if loader is None else loader
    out: dict[str, list[Any]] = {}
    for model, dirs in runs.items():
        seen: set[tuple[str, str]] = set()
        versions: set[tuple[str, str]] = set()
        records = []
        for directory in dirs:
            for record in load(ROOT / directory):
                identity = (record.run_id, record.sample_id)
                if identity in seen:
                    raise ProvenanceError(f"{model}: conversation {identity} counted twice")
                seen.add(identity)
                if not record.complete:
                    raise ProvenanceError(f"{model}: {record.sample_id} is incomplete")
                versions.add((record.topic_set, record.questions_sha256))
                records.append(record)
        if len(versions) > 1:
            raise ProvenanceError(f"{model}: mixed dialogue versions {sorted(versions)}")
        out[model] = records
    return out


def dialogue_status_table(
    runs: dict[str, tuple[str, ...]] | None = None, loader: Any = None
) -> list[dict[str, Any]]:
    """Every forced advice answer by status, per (model, order, topic, stage).

    `advice_today_n` in the other dialogue tables counts only answers with a letter, which hides
    a model that declines to recommend (Gemini before historical questions). Here a
    reply without a letter is kept: `no_letter` when the model wrote something, `empty` when the
    completion was empty. Reading what a no-letter reply says is left to a human.
    """
    runs = DIALOGUE_RUNS if runs is None else runs
    rows: list[dict[str, Any]] = []
    for model, records in dialogue_records(runs, loader).items():
        counts: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
        conversations: Counter[str] = Counter(r.order for r in records)
        for record in records:
            for turn in record.turns:
                stage, topic = turn.get("stage"), turn.get("topic")
                if stage not in ("advice", "present") or not topic:
                    continue
                answer = turn.get("answer")
                if answer in RESIST_OPTIONS:
                    status = str(answer)
                elif (turn.get("completion") or "").strip():
                    status = "no_letter"
                else:
                    status = "empty"
                counts[(record.order, str(topic), str(stage))][status] += 1
        for (order, topic, stage), c in sorted(counts.items()):
            rows.append(
                {
                    "model": model,
                    "order": order,
                    "topic": topic,
                    "stage": "today" if stage == "present" else "history",
                    "conversations": conversations[order],
                    **{k: c.get(k, 0) for k in (*RESIST_OPTIONS, "no_letter", "empty")},
                }
            )
    return rows


def run_metadata(
    bank: dict[str, tuple[str, ...]] | None = None,
    dialogue: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    groups = (
        ("bank", BANK_RUNS if bank is None else bank),
        ("dialogue", DIALOGUE_RUNS if dialogue is None else dialogue),
    )
    for label, group in groups:
        per_model = {}
        for model, dirs in group.items():
            sessions = errors = 0
            cost = 0.0
            for directory in dirs:
                for path in sorted((ROOT / directory).glob("*.eval")):
                    log = read_eval_log(str(path), header_only=True)
                    if log.results:
                        sessions += log.results.completed_samples
                    if log.results:
                        errors += log.results.total_samples - log.results.completed_samples
                    for usage in (log.stats.model_usage or {}).values():
                        cost += usage.total_cost or 0.0
            per_model[model] = {
                "sessions": sessions,
                "incomplete": errors,
                "cost_usd_reported": round(cost, 2) or None,
            }
        meta[label] = per_model
    return meta


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    extended = "--extended" in args
    bank = {**BANK_RUNS, **NEW_BANK_RUNS, **GPT6_BANK_RUNS} if extended else BANK_RUNS
    dialogue = (
        {**DIALOGUE_RUNS, **NEW_DIALOGUE_RUNS, **GPT6_DIALOGUE_RUNS} if extended else DIALOGUE_RUNS
    )
    out = OUT / "extended" if extended else OUT
    if "--abliteration" in args:
        bank, dialogue = ABLITERATION_BANK_RUNS, ABLITERATION_DIALOGUE_RUNS
        out = OUT / "abliteration"
    out.mkdir(parents=True, exist_ok=True)
    cases = {c.id: c for c in load_cases([ROOT / "cases"])}
    rows = bank_rows(cases, bank)
    write_csv(out / "answers.csv", rows)
    write_csv(out / "cells.csv", cell_table(rows))
    (out / "cases.json").write_text(
        json.dumps(case_profiles(rows, cases, tuple(bank)), indent=2),
        encoding="utf-8",
        newline="\n",
    )
    topics, flags = dialogue_tables(dialogue)
    write_csv(out / "dialogue.csv", [{**t, "act": json.dumps(t["act"])} for t in topics])
    write_csv(out / "dialogue_flags.csv", flags)
    orders, order_topics = dialogue_order_tables(dialogue)
    write_csv(out / "dialogue_orders.csv", orders)
    write_csv(out / "dialogue_order_topics.csv", order_topics)
    write_csv(out / "dialogue_status.csv", dialogue_status_table(dialogue))
    summary = {
        "cases": len(cases),
        "bank_sessions": len(rows),
        "unscored_answers": sum(1 for r in rows if r["law_side"] == ""),
        "runs": run_metadata(bank, dialogue),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
