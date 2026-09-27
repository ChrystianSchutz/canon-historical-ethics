"""Export selected publication evidence without Inspect's private execution traces.

Run after export_dataset.py. Writes JSONL gzip files and a manifest under dist/hf/transcripts/.
Only explicit evidence fields are copied; original .eval files are never changed. Visible
messages, completions and prompt hashes remain intact. Provider payloads, reasoning blocks,
retry tracebacks, repository metadata and local paths are omitted. A privacy scan fails before
each output file is written.
No model calls or uploads are made.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from aggregate_results import (
    ABLITERATION_BANK_RUNS,
    ABLITERATION_DIALOGUE_RUNS,
    BANK_RUNS,
    DIALOGUE_RUNS,
    GPT6_BANK_RUNS,
    GPT6_DIALOGUE_RUNS,
    NEW_BANK_RUNS,
    NEW_DIALOGUE_RUNS,
)
from inspect_ai.log import read_eval_log

from canon.validate import load_cases

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "hf"
METADATA_FIELDS = (
    "case_id",
    "case_sha256",
    "canary",
    "cell_id",
    "role",
    "identity",
    "hindsight",
    "wording_variant",
    "replicate",
    "permutation_seed",
    "generation_seed",
    "choices",
    "turn1_sha256",
    "turn2",
    "turn2_sha256",
    "turn1_completion",
    "turn1_stop_reason",
    "turn2_stop_reason",
    "order",
    "topic_set",
    "questions_sha256",
    "turns",
)
TASK_FIELDS = (
    "samples",
    "samples_per_cell",
    "seed",
    "temperature",
    "max_tokens",
    "cell_filter",
    "per_sample_seed",
    "allow_unverified",
    "order",
    "topic_set",
)
PRIVACY_PATTERNS = {
    "credential": r"sk-(?:or-|ant-)?[A-Za-z0-9_-]{16,}",
    "account identifier": r'^user_id$|"user_id"\s*:|user_[A-Za-z0-9]{12,}',
    "Windows path": r"\b[A-Za-z]:\\|\b[A-Za-z]:/(?!/)",
    "home path": r"/(?:home|Users)/[^\s/]+/",
}


def privacy_check(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            privacy_check(key)
            privacy_check(value)
        return
    if isinstance(payload, list):
        for value in payload:
            privacy_check(value)
        return
    if not isinstance(payload, str):
        return
    for label, pattern in PRIVACY_PATTERNS.items():
        if re.search(pattern, payload, re.IGNORECASE):
            # Report the category, never the matching sensitive value.
            raise ValueError(f"Transcript export contains a possible {label}; review locally")


def message_record(message: Any) -> dict[str, Any]:
    data = message.model_dump(mode="json", exclude_none=True)
    record = {key: data[key] for key in ("role", "content", "model") if key in data}
    if isinstance(record["content"], list):
        blocks = []
        for block in record["content"]:
            if block["type"] == "text":
                blocks.append({"type": "text", "text": block["text"]})
            elif block["type"] == "reasoning":
                # These logs contain encrypted provider blobs even in summary fields.
                # Release the visible replies used in the study, not opaque replay payloads.
                blocks.append({"type": "reasoning", "omitted_from_release": True})
            else:
                raise ValueError(f"Unexpected message content type: {block['type']}")
        record["content"] = blocks
    return record


def output_record(output: Any) -> dict[str, Any]:
    return {
        "model": output.model,
        "completion": output.completion,
        "choices": [
            {"message": message_record(choice.message), "stop_reason": choice.stop_reason}
            for choice in output.choices
        ],
        "usage": output.usage.model_dump(mode="json", exclude_none=True) if output.usage else None,
    }


def sample_record(sample: Any, eval_id: str) -> dict[str, Any]:
    return {
        "eval_id": eval_id,
        "sample_id": str(sample.id),
        "epoch": sample.epoch,
        "metadata": {
            key: sample.metadata[key] for key in METADATA_FIELDS if key in sample.metadata
        },
        "messages": [message_record(message) for message in sample.messages],
        "output": output_record(sample.output),
        "scores": {
            name: {"value": score.value, "answer": score.answer}
            for name, score in (sample.scores or {}).items()
        },
        "sample_error": sample.error is not None,
        "calls": [
            {
                "model": event.model,
                "config": event.config.model_dump(mode="json", exclude_none=True),
                "output": output_record(event.output),
                "retries": event.retries,
                "error": event.error is not None,
            }
            for event in sample.events
            if event.event == "model"
        ],
    }


def main() -> None:
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    active = {case.id for case in load_cases([ROOT / "cases"])}
    groups = (
        ("bank", "extended", {**BANK_RUNS, **NEW_BANK_RUNS, **GPT6_BANK_RUNS}),
        ("dialogue", "extended", {**DIALOGUE_RUNS, **NEW_DIALOGUE_RUNS, **GPT6_DIALOGUE_RUNS}),
        ("bank", "abliteration", ABLITERATION_BANK_RUNS),
        ("dialogue", "abliteration", ABLITERATION_DIALOGUE_RUNS),
    )
    entries = []
    totals: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for kind, scope, runs in groups:
        for label, directories in runs.items():
            for directory in directories:
                paths = sorted((ROOT / directory).glob("*.eval"))
                if not paths:
                    raise FileNotFoundError(f"No selected logs for {label} {kind}")
                for path in paths:
                    log = read_eval_log(str(path))
                    eval_id = log.eval.eval_id
                    if not eval_id:
                        raise ValueError("Selected log lacks an eval identifier")
                    records = []
                    excluded = 0
                    for sample in log.samples or []:
                        if kind == "bank" and sample.metadata.get("case_id") not in active:
                            excluded += 1
                            continue
                        identity = (eval_id, str(sample.id))
                        if identity in seen:
                            raise ValueError(f"Duplicate selected sample: {identity}")
                        seen.add(identity)
                        records.append(sample_record(sample, eval_id))
                    privacy_check(records)
                    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)
                    model_slug = log.eval.model.rsplit("/", 1)[-1].lower()
                    name = f"{model_slug}__{eval_id}.jsonl.gz"
                    target = OUT / "transcripts" / scope / kind / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
                    relative = target.relative_to(OUT).as_posix()
                    digest = hashlib.sha256(target.read_bytes()).hexdigest()
                    entry = {
                        "path": relative,
                        "sha256": digest,
                        "scope": scope,
                        "kind": kind,
                        "label": label,
                        "model": log.eval.model,
                        "eval_id": eval_id,
                        "created": log.eval.created,
                        "status": log.status,
                        "source_log": path.name,
                        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "samples": len(records),
                        "excluded_inactive_samples": excluded,
                        "task_args": {
                            key: value
                            for key, value in log.eval.task_args.items()
                            if key in TASK_FIELDS
                        },
                        "eval_generation_config": log.eval.model_generate_config.model_dump(
                            mode="json", exclude_none=True
                        ),
                    }
                    privacy_check(entry)
                    entries.append(entry)
                    manifest["files"][relative] = digest
                    key = scope + "/" + kind
                    totals[key] = totals.get(key, 0) + len(records)
                    print(kind, label, len(records), flush=True)
    expected = {
        "extended/bank": 17630,
        "extended/dialogue": 180,
        "abliteration/bank": 3440,
        "abliteration/dialogue": 30,
    }
    if totals != expected:
        raise ValueError(f"Publication sample counts differ: {totals}")
    transcript_manifest = {
        "schema_version": 1,
        "format": "One JSON object per observed sample, gzip compressed; not Inspect .eval files.",
        "selection": (
            "All active-case samples and dialogues from the selected analysis logs. The original "
            "five-model scope is a subset of extended and is not duplicated here."
        ),
        "privacy": (
            "Allowlisted evidence fields only. Omits repository/machine metadata, provider "
            "payloads, reasoning blocks/signatures, retry/error tracebacks and exception messages. "
            "Error presence and retry counts remain. Visible message text, completions, letter "
            "maps, hashes and call configurations are preserved; original logs are unchanged."
        ),
        "configuration": (
            "calls[].config records effective per-call settings; these override task defaults. "
            "CLI-internal context not exposed by the adapter is not present in the source logs."
        ),
        "totals": totals,
        "logs": entries,
    }
    relative_manifest = "transcripts/manifest.json"
    target_manifest = OUT / relative_manifest
    target_manifest.write_text(
        json.dumps(transcript_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest["files"][relative_manifest] = hashlib.sha256(target_manifest.read_bytes()).hexdigest()
    manifest["observed_transcripts_included"] = True
    manifest["status"] = "release_with_selected_transcripts"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Transcript export complete:", totals)


if __name__ == "__main__":
    main()
