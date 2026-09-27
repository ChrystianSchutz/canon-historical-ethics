"""Read CANON answers back out of Inspect eval logs."""

from __future__ import annotations

from pathlib import Path

from inspect_ai.log import read_eval_log

from canon.framing import FramingRecord
from canon.hypocrisy import HypocrisyRecord, orders_for
from canon.summary import AnswerRecord, ProbeRecord

CHOICE_SCORER = "choice_scorer"
JUDGE_SCORER = "turn1_judge"
PROBE_SCORER = "probe_scorer"
TASK_NAME = "canon_eval"
PROBE_TASK_NAME = "canon_probe"
HYPOCRISY_TASK_NAME = "canon_gandhi"
FRAMING_TASK_NAME = "canon_openers"
LOG_SUFFIXES = frozenset({".eval", ".json"})


def find_log_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*") if p.suffix in LOG_SUFFIXES)


def load_records(path: Path) -> list[AnswerRecord]:
    records: list[AnswerRecord] = []
    for file in find_log_files(path):
        log = read_eval_log(str(file))
        if not log.eval.task.endswith(TASK_NAME):
            continue
        for sample in log.samples or []:
            scores = sample.scores or {}
            choice = scores.get(CHOICE_SCORER)
            if choice is None:
                continue
            judge = scores.get(JUDGE_SCORER)
            metadata = sample.metadata
            records.append(
                AnswerRecord(
                    model=log.eval.model,
                    case_id=metadata["case_id"],
                    case_sha256=metadata["case_sha256"],
                    cell_id=metadata["cell_id"],
                    replicate=int(metadata["replicate"]),
                    outcome=str(choice.value),
                    sample_id=str(sample.id),
                    turn1=metadata.get("turn1_completion"),
                    response_class=str(judge.value) if judge is not None else None,
                    stance=(judge.metadata or {}).get("stance_answer_id") if judge else None,
                    run_id=log.eval.eval_id or str(file.resolve()),
                    turn1_named=tuple((choice.metadata or {}).get("turn1_named") or ()),
                )
            )
    return records


def load_hypocrisy_records(path: Path) -> list[HypocrisyRecord]:
    records: list[HypocrisyRecord] = []
    for file in find_log_files(path):
        log = read_eval_log(str(file))
        if not log.eval.task.endswith(HYPOCRISY_TASK_NAME):
            continue
        for sample in log.samples or []:
            metadata = sample.metadata or {}
            turns = metadata.get("turns")
            if not turns:
                continue
            order = str(metadata.get("order"))
            topic_set = str(metadata.get("topic_set") or "core")
            try:
                expected = len(orders_for(order, topic_set))
            except ValueError:
                expected = 0
            records.append(
                HypocrisyRecord(
                    model=log.eval.model,
                    sample_id=str(sample.id),
                    order=order,
                    replicate=int(metadata.get("replicate", 0)),
                    turns=tuple(turns),
                    run_id=log.eval.eval_id or str(file.resolve()),
                    topic_set=topic_set,
                    questions_sha256=str(metadata.get("questions_sha256") or ""),
                    turns_expected=expected,
                    error=str(sample.error) if sample.error else None,
                )
            )
    return records


def load_framing_records(path: Path) -> list[FramingRecord]:
    records: list[FramingRecord] = []
    for file in find_log_files(path):
        log = read_eval_log(str(file))
        if not log.eval.task.endswith(FRAMING_TASK_NAME):
            continue
        for sample in log.samples or []:
            metadata = sample.metadata or {}
            if "opening" not in metadata:
                continue
            answer = metadata.get("answer")
            records.append(
                FramingRecord(
                    model=log.eval.model,
                    variant=str(metadata.get("variant")),
                    sample_id=str(sample.id),
                    opening=str(metadata.get("opening") or ""),
                    follow_up=str(metadata.get("follow_up") or ""),
                    answer=None if answer is None else str(answer),
                    run_id=log.eval.eval_id or str(file.resolve()),
                )
            )
    return records


def load_probe_records(path: Path) -> list[ProbeRecord]:
    records: list[ProbeRecord] = []
    for file in find_log_files(path):
        log = read_eval_log(str(file))
        if not log.eval.task.endswith(PROBE_TASK_NAME):
            continue
        for sample in log.samples or []:
            score = (sample.scores or {}).get(PROBE_SCORER)
            if score is None:
                continue
            records.append(
                ProbeRecord(
                    model=log.eval.model,
                    case_id=sample.metadata["case_id"],
                    outcome=str(score.value),
                    answer=str(score.answer or ""),
                    run_id=log.eval.eval_id or str(file.resolve()),
                )
            )
    return records
