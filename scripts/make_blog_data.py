"""Export the twelve-model results as one JSON blob for the interactive page in `site/`.

    uv run python scripts/aggregate_results.py --extended
    uv run python scripts/make_blog_data.py [--out FILE]

Writes `site/data.js`, a single
`window.CANON_DATA = {...}` assignment, so the page opens from disk without a server. Only counts
from `results/extended/` and `results/abliteration/` go in; no case text.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "results" / "extended"
ABL = ROOT / "results" / "abliteration"
DEFAULT_OUT = ROOT / "site" / "data.js"

_MODEL_ROWS = (
    # id, label, vendor, September 21 follow-up cohort (not freeze status), access
    ("Opus 5", "Claude Opus 5", "Anthropic", False, "Claude Code CLI"),
    ("Sol", "GPT-5.6 Sol", "OpenAI", False, "OpenRouter"),
    ("Luna", "GPT-5.6 Luna", "OpenAI", False, "OpenRouter"),
    ("Muse", "Muse Spark 1.3", "Meta", False, "OpenRouter"),
    ("Qwen", "Qwen 3.7 Flash", "Alibaba", False, "OpenRouter"),
    ("Qwen 3.8", "Qwen 3.8 Flash", "Alibaba", True, "OpenRouter"),
    ("DeepSeek", "DeepSeek V4.1 Flash", "DeepSeek", True, "OpenRouter"),
    ("GLM", "GLM 5.3 Flash", "Z.ai", True, "OpenRouter"),
    ("Gemini", "Gemini 3.8 Flash", "Google", True, "OpenRouter"),
    ("Bielik", "Bielik 11B v3", "SpeakLeash", True, "local, llama.cpp"),
    ("Luna 6", "GPT-6 Luna", "OpenAI", True, "OpenRouter"),
    ("Sol 6", "GPT-6 Sol", "OpenAI", True, "OpenRouter"),
)
MODELS: list[dict[str, Any]] = [
    dict(zip(("id", "label", "vendor", "new", "access"), row, strict=True)) for row in _MODEL_ROWS
]


def read(name: str, base: Path = EXT) -> list[dict[str, str]]:
    path = base / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def options(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for part in filter(None, text.split("; ")):
        key, _, value = part.rpartition(":")
        out[key] = int(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    def cell_rows(base: Path) -> list[dict[str, Any]]:
        return [
            {
                "case": c["case"],
                "role": c["role"],
                "hindsight": c["hindsight"],
                "model": c["model"],
                "n": int(c["n"]),
                "law": int(c["law_side"]),
                "scored": int(c["scored"]),
                "options": options(c["options"]),
            }
            for c in read("cells.csv", base)
        ]

    cells = cell_rows(EXT)
    present = {c["model"] for c in cells}
    cases = json.loads((EXT / "cases.json").read_text(encoding="utf-8"))
    data = {
        "models": [m for m in MODELS if m["id"] in present],
        "cells": cells,
        "cases": {
            k: {
                "title": v["title"],
                "date": v["date"],
                "expectation": v["expectation"],
                "pair": v["pair"],
            }
            for k, v in cases.items()
        },
        "dialogue_orders": read("dialogue_orders.csv"),
        "dialogue_topics": read("dialogue_order_topics.csv"),
        "dialogue_status": read("dialogue_status.csv"),
        # Qwen 3.8 27B before and after abliteration (results/abliteration/); a separate pair,
        # never mixed into the ten-model cells above.
        "abliteration": {
            "cells": cell_rows(ABL),
            "dialogue_status": read("dialogue_status.csv", ABL),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "window.CANON_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KB, {len(cells)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
