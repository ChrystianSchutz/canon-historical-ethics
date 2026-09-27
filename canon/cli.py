"""``canon`` command line interface."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import ValidationError

from canon import __version__
from canon.agreement import read_agreement, select_for_validation, write_validation_sheet
from canon.env import OPENROUTER_ENV, load_env, openrouter_key_present
from canon.frames import render_cell
from canon.judge import KAPPA_THRESHOLD
from canon.review import render_review
from canon.schema import case_json_schema
from canon.skeleton import case_filename, render_skeleton
from canon.summary import format_summary
from canon.validate import load_case, validate_paths

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schema" / "case.schema.json"
# Relative to REPO_ROOT: Inspect rejects absolute task paths on Windows.
TASK_FILE = "canon/inspect_adapter/task.py"
HYPOCRISY_TASK_FILE = "canon/inspect_adapter/hypocrisy_task.py"
FRAMING_TASK_FILE = "canon/inspect_adapter/framing_task.py"
FRAMING_TASK = "canon_openers"
EVAL_TASK = "canon_eval"
PROBE_TASK = "canon_probe"
HYPOCRISY_TASK = "canon_gandhi"


DEFAULT_TIMEOUT_SECONDS = "300"


def with_default_timeout(inspect_args: Sequence[str]) -> list[str]:
    """Inspect sets no request timeout by default, so one hung connection can stall a run
    indefinitely (seen with Mercury on 2026-09-15). Add one unless the caller chose their own."""
    args = list(inspect_args)
    if not any(a == "--timeout" or a.startswith("--timeout=") for a in args):
        args += ["--timeout", DEFAULT_TIMEOUT_SECONDS]
    return args


def build_eval_command(
    inspect_args: Sequence[str], task_name: str = EVAL_TASK, task_file: str = TASK_FILE
) -> list[str]:
    # The task file defines several tasks; name one so Inspect does not run them all.
    return [sys.executable, "-m", "inspect_ai", "eval", f"{task_file}@{task_name}", *inspect_args]


def run_eval(
    inspect_args: Sequence[str], task_name: str = EVAL_TASK, task_file: str = TASK_FILE
) -> int:
    """``canon eval ...`` = ``inspect eval canon/inspect_adapter/task.py ...`` with ``.env`` loaded.

    Inspect creates the model client before it imports the task file, so the OpenRouter key
    must be in the environment before Inspect starts.
    """
    load_env()
    if any("openrouter/" in arg for arg in inspect_args) and not openrouter_key_present():
        print(f"ERROR {OPENROUTER_ENV} is not set (put OPEN_ROUTER_KEY in .env)")
        return 1
    # Run from the repo root so the task path, `cases` and the default `logs/` resolve there.
    command = build_eval_command(with_default_timeout(inspect_args), task_name, task_file)
    return subprocess.call(command, cwd=REPO_ROOT)


def _cmd_new(args: argparse.Namespace) -> int:
    target: Path = args.dir / case_filename(args.case_id)
    if target.exists() and not args.force:
        print(f"ERROR {target} already exists (use --force to overwrite)")
        return 1
    try:
        schema_ref = Path(os.path.relpath(SCHEMA_PATH, args.dir.resolve())).as_posix()
    except ValueError:  # different drive on Windows
        schema_ref = SCHEMA_PATH.as_uri()
    try:
        text = render_skeleton(args.case_id, args.date, title=args.title, schema_ref=schema_ref)
    except ValueError as exc:
        print(f"ERROR {exc}")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"created {target}")
    print("next: fill in every TODO (docs/CASE_AUTHORING.md), then run")
    print(f"  uv run canon validate {target}")
    print(f"  uv run canon review {target}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    cases, issues = validate_paths(args.paths, require_verified=args.require_verified)
    for issue in issues:
        print(f"ERROR {issue}")
    if issues:
        print(f"{len(issues)} issue(s) found")
        return 1
    if not cases:
        print("no case files found")
        return 0
    unverified = sum(not c.is_verified for c in cases)
    print(f"OK {len(cases)} case(s), {unverified} with unverified facts")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    try:
        case = load_case(args.case)
        cell = case.cell(args.cell)
    except (ValidationError, KeyError) as exc:
        print(f"ERROR {exc}")
        return 1
    rendered = render_cell(case, cell, permutation_seed=args.seed)
    print(f"=== {case.id} / {cell.id} / seed={args.seed} ===")
    print("\n--- TURN 1 ---")
    print(rendered.turn1)
    print("\n--- TURN 2 ---")
    print(rendered.turn2)
    print("\n--- LETTER MAP ---")
    for choice in rendered.choices:
        print(f"{choice.letter} -> {choice.answer_id}")
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    try:
        case = load_case(args.case)
    except ValidationError as exc:
        print(f"ERROR {exc}")
        return 1
    out: Path = args.out or Path("review") / f"{case.id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_review(case), encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(case_json_schema(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    # Imports Inspect; keep CLI start fast.
    from canon.inspect_adapter.logs import load_probe_records, load_records

    records = load_records(args.logs)
    probes = load_probe_records(args.logs)
    if not records and not probes:
        print(f"no CANON samples found in {args.logs}")
        return 1
    cases, issues = validate_paths(args.cases)
    for issue in issues:
        print(f"WARNING {issue}")
    print(format_summary(records, cases, probes))
    return 0


def _cmd_gandhi_summary(args: argparse.Namespace) -> int:
    from canon.hypocrisy import format_report
    from canon.inspect_adapter.logs import load_hypocrisy_records

    records = load_hypocrisy_records(args.logs)
    if not records:
        print(f"no canon_gandhi conversations found in {args.logs}")
        return 1
    report = format_report(records)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        print(report)
    return 0


def _cmd_openers_summary(args: argparse.Namespace) -> int:
    from canon.framing import format_framing_report
    from canon.inspect_adapter.logs import load_framing_records

    records = load_framing_records(args.logs)
    if not records:
        print(f"no canon_openers samples found in {args.logs}")
        return 1
    report = format_framing_report(records)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        print(report)
    return 0


def _cmd_judge_sheet(args: argparse.Namespace) -> int:
    from canon.inspect_adapter.logs import load_records

    selected = select_for_validation(load_records(args.logs), args.fraction, args.seed)
    if not selected:
        print(f"no judged samples found in {args.logs} (run with -T judge_model=...)")
        return 1
    write_validation_sheet(selected, args.out)
    print(f"wrote {len(selected)} sample(s) to {args.out}")
    print("fill in human_response_class and human_stance blind to the judge columns, then run")
    print(f"  uv run canon judge-agreement {args.out}")
    return 0


def _fmt_kappa(kappa: float | None) -> str:
    return "n/a" if kappa is None else f"{kappa:.3f}"


def _cmd_judge_agreement(args: argparse.Namespace) -> int:
    report = read_agreement(args.sheet)
    if report.n == 0 and report.stance_n == 0:
        print("no human codes filled in yet")
        return 1
    print(f"response class: kappa {_fmt_kappa(report.class_kappa)} on {report.n} sample(s)")
    print(f"stance:         kappa {_fmt_kappa(report.stance_kappa)} on {report.stance_n} sample(s)")
    print(f"threshold {KAPPA_THRESHOLD}: {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


def _cmd_doctor(_: argparse.Namespace) -> int:
    load_env()
    try:
        inspect_version = version("inspect-ai")
    except PackageNotFoundError:
        inspect_version = "NOT INSTALLED"
    key_ok = openrouter_key_present()
    print(f"canon       {__version__}")
    print(f"python      {platform.python_version()}")
    print(f"inspect-ai  {inspect_version}")
    print(f"{OPENROUTER_ENV}  {'set' if key_ok else 'MISSING'}")
    return 0 if key_ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canon", description="CANON: Consistency of Applied Normative Standards"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Handled in main() before argparse, so every argument passes through to `inspect eval`.
    sub.add_parser(
        "eval",
        help="Run the CANON Inspect task with .env loaded; arguments go to `inspect eval`.",
    )
    sub.add_parser(
        "probe",
        help="Run the recognizability probe task; arguments go to `inspect eval`.",
    )
    sub.add_parser(
        "gandhi",
        help="Run the 'be like Gandhi' hypocrisy dialogue; arguments go to `inspect eval`.",
    )
    gandhi_summary = sub.add_parser(
        "gandhi-summary", help="Summarise 'be like Gandhi' hypocrisy dialogues from Inspect logs."
    )
    gandhi_summary.add_argument("logs", type=Path)
    gandhi_summary.add_argument("--out", type=Path, default=None, help="write Markdown here")
    gandhi_summary.set_defaults(handler=_cmd_gandhi_summary)
    sub.add_parser(
        "openers",
        help="Run the opening-framing probe (when is Gandhi volunteered?); args go to inspect.",
    )
    openers_summary = sub.add_parser(
        "openers-summary", help="Summarise opening-framing probe samples from Inspect logs."
    )
    openers_summary.add_argument("logs", type=Path)
    openers_summary.add_argument("--out", type=Path, default=None, help="write Markdown here")
    openers_summary.set_defaults(handler=_cmd_openers_summary)

    new = sub.add_parser("new", help="Create a case skeleton with TODO markers.")
    new.add_argument("case_id", help="e.g. TURING-1952")
    new.add_argument("--date", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    new.add_argument("--title", default=None)
    new.add_argument("--dir", type=Path, default=Path("cases"))
    new.add_argument("--force", action="store_true")
    new.set_defaults(handler=_cmd_new)

    validate = sub.add_parser("validate", help="Validate case files (schema, invariants, lint).")
    validate.add_argument("paths", nargs="*", type=Path, default=[Path("cases")])
    validate.add_argument(
        "--require-verified", action="store_true", help="fail on facts not verified by a human"
    )
    validate.set_defaults(handler=_cmd_validate)

    render = sub.add_parser("render", help="Print the prompts of one cell.")
    render.add_argument("case", type=Path)
    render.add_argument("--cell", required=True, help="e.g. executor.named.stripped")
    render.add_argument("--seed", type=int, default=None, help="option permutation seed")
    render.set_defaults(handler=_cmd_render)

    review = sub.add_parser("review", help="Write a human review sheet (Markdown) for a case.")
    review.add_argument("case", type=Path)
    review.add_argument("--out", type=Path, default=None, help="default: review/<CASE-ID>.md")
    review.set_defaults(handler=_cmd_review)

    schema = sub.add_parser("schema", help="Write the JSON Schema for case files.")
    schema.add_argument("--out", type=Path, default=SCHEMA_PATH)
    schema.set_defaults(handler=_cmd_schema)

    summary = sub.add_parser("summary", help="Summarise answers from Inspect logs.")
    summary.add_argument("logs", type=Path, help="log file or directory (e.g. logs/)")
    summary.add_argument("--cases", nargs="*", type=Path, default=[Path("cases")])
    summary.set_defaults(handler=_cmd_summary)

    judge_sheet = sub.add_parser(
        "judge-sheet", help="Sample judged answers into a CSV for blind human coding."
    )
    judge_sheet.add_argument("logs", type=Path)
    judge_sheet.add_argument("--fraction", type=float, default=0.2)
    judge_sheet.add_argument("--seed", type=int, default=0)
    judge_sheet.add_argument("--out", type=Path, default=Path("review/judge_validation.csv"))
    judge_sheet.set_defaults(handler=_cmd_judge_sheet)

    judge_agreement = sub.add_parser(
        "judge-agreement", help="Cohen's kappa between the LLM judge and human codes."
    )
    judge_agreement.add_argument("sheet", type=Path)
    judge_agreement.set_defaults(handler=_cmd_judge_agreement)

    doctor = sub.add_parser("doctor", help="Check the local environment (never prints secrets).")
    doctor.set_defaults(handler=_cmd_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["eval"]:
        return run_eval(argv[1:])
    if argv[:1] == ["probe"]:
        return run_eval(argv[1:], PROBE_TASK)
    if argv[:1] == ["gandhi"]:
        return run_eval(argv[1:], HYPOCRISY_TASK, HYPOCRISY_TASK_FILE)
    if argv[:1] == ["openers"]:
        return run_eval(argv[1:], FRAMING_TASK, FRAMING_TASK_FILE)
    args = build_parser().parse_args(argv)
    result: int = args.handler(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
