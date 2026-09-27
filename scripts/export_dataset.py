"""Export the case bank as a flat dataset for Hugging Face.

    uv run python scripts/export_dataset.py

Writes into `dist/hf/`:

- `data/active.jsonl`    one row per active case (15)
- `data/rejected.jsonl`  one row per rejected case (25), with the rejection reason file named
- `data/cells.jsonl`     one illustrative rendering per cell at seed 1, not an observed sample
- `results/*`           original five-model aggregates, with `extended/` and `abliteration/`
                        kept as separate scopes (the extended cohort includes the original five)
- `manifest.json`       scope descriptions and SHA-256 hashes of exported data and results

It does NOT write the dataset card. `dist/hf/README.md` has to be written and reviewed by hand
before upload; the script says so at the end.

Cell rows let readers inspect the instrument without running the harness. Exact observed prompts,
responses and generation settings still require a deliberate transcript export. This script does
not copy raw logs and does not upload anything.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from canon.frames import render_cell
from canon.provenance import case_hash
from canon.validate import load_cases

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "hf"
SEED = 1
RESULT_FILES = (
    "answers.csv",
    "cells.csv",
    "dialogue.csv",
    "dialogue_flags.csv",
    "dialogue_orders.csv",
    "dialogue_order_topics.csv",
    "dialogue_status.csv",
    "cases.json",
    "summary.json",
)
SCOPES = {
    "": "Original five-model cohort; included in extended, not a disjoint dataset.",
    "extended": "Twelve-model cohort, including the original five models and two GPT-6 successors.",
    "abliteration": (
        "Separate comparison of two related local builds; not a causal isolation of the edit."
    ),
}


def case_row(case, rejected: bool) -> dict:
    return {
        "id": case.id,
        "title": case.title,
        "decision_date": str(case.decision_date),
        "status": "rejected" if rejected else "active",
        "canary": case.canary,
        "case_sha256": case_hash(case),
        "observer_evaluates": getattr(case.observer_evaluates, "value", None),
        "expectation_direction": getattr(case.expectation.direction, "value", None)
        if case.expectation
        else None,
        "expectation_pair": case.expectation.pair_id if case.expectation else None,
        "hindsight_verdict": case.hindsight_verdict,
        "record": [{"id": s.id, "text": s.text} for s in case.record],
        "facts": [
            {
                "id": f.id,
                "text": f.text,
                "sources": [
                    {"citation": s.citation, "url": str(s.url), "locator": s.locator}
                    for s in f.sources
                ],
                "verified_by": f.verified_by,
                "verified_at": str(f.verified_at) if f.verified_at else None,
            }
            for f in case.facts
        ],
        "options": [
            {
                "id": o.id,
                "text": o.text,
                "legally_available": o.legally_available,
                "within_role_authority": o.within_role_authority,
                "personal_consequence": getattr(o.personal_consequence, "value", None),
                "historical_actual": o.historical_actual,
                "upholds_order": o.upholds_order,
            }
            for o in case.options
        ],
        "subject_options": [{"id": o.id, "text": o.text} for o in case.subject_options],
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {path.relative_to(ROOT)} ({len(rows)} rows)")


def main() -> None:
    # Reject an incomplete analysis package before writing any case or result files.
    sources = [ROOT / "results" / scope / name for scope in SCOPES for name in RESULT_FILES]
    missing = [str(path.relative_to(ROOT)) for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required result inputs: " + ", ".join(missing))
    active = sorted(load_cases([ROOT / "cases"]), key=lambda c: str(c.decision_date))
    rejected = sorted(load_cases([ROOT / "rejected" / "cases"]), key=lambda c: str(c.decision_date))
    write_jsonl(OUT / "data" / "active.jsonl", [case_row(c, False) for c in active])
    write_jsonl(OUT / "data" / "rejected.jsonl", [case_row(c, True) for c in rejected])

    cells = []
    for case in active:
        for cell in case.cells:
            rendered = render_cell(case, cell, permutation_seed=SEED)
            cells.append(
                {
                    "case_id": case.id,
                    "cell_id": cell.id,
                    "role": cell.role.value,
                    "identity": cell.identity.value,
                    "hindsight": cell.hindsight.value,
                    "wording_variant": getattr(cell.wording_variant, "value", None),
                    "turn1": rendered.turn1,
                    "turn2": rendered.turn2,
                    "letter_map": {c.letter: c.answer_id for c in rendered.choices},
                    "render_seed": SEED,
                    "render_kind": "illustrative_fixed_seed",
                    "case_sha256": case_hash(case),
                }
            )
    write_jsonl(OUT / "data" / "cells.jsonl", cells)

    exported = [OUT / "data" / name for name in ("active.jsonl", "rejected.jsonl", "cells.jsonl")]
    for source in sources:
        target = OUT / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        exported.append(target)
    manifest = {
        "schema_version": 1,
        "status": "release_aggregates_and_illustrative_prompts",
        "observed_transcripts_included": False,
        "scopes": SCOPES,
        "files": {
            path.relative_to(OUT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in exported
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        "\nDraft export complete. Review the card, licensing and exact-transcript package "
        "before upload."
    )


if __name__ == "__main__":
    main()
