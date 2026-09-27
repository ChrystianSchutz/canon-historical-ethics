"""Generate the paper's appendices from the same files the blog post uses.

    uv run python scripts/make_appendices.py [--source path/to/case_commentary.md]

- `paper/results_appendix.tex` law-side counts for every case, role, hindsight and model, always
  regenerated from `results/`;
- `paper/cases.tex`            the 15-case appendix, regenerated only when `--source` names a
  Markdown case write-up. Without it the committed `paper/cases.tex` is the maintained text;
  its quoted counts are checked by `scripts/check_claims.py`.

The case write-up lives in Markdown because the blog post needs it too. This converter handles the
small Markdown subset that file uses: `##` headings, `**bold**`, `*italic*`, `` `code` ``, pipe
tables, horizontal rules and paragraphs. It is deliberately strict: anything it does not recognise
is escaped and passed through, so a surprise never becomes silent LaTeX.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ["Opus 5", "Sol", "Luna", "Muse", "Qwen"]
ROLE_ORDER = ["observer", "advisor_actor", "advisor_state", "executor", "advisor_subject"]


def escape(text: str) -> str:
    out = text
    for char, replacement in (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ):
        out = out.replace(char, replacement)
    return out.replace("—", "---").replace("–", "--").replace("’", "'").replace("…", r"\ldots{}")


def smart_quotes(text: str) -> str:
    """Straight quotes -> TeX quotes, pairwise. Apostrophes are left alone."""
    out, open_quote = [], True
    for char in text:
        if char == '"':
            out.append("``" if open_quote else "''")
            open_quote = not open_quote
        else:
            out.append(char)
    return "".join(out)


def inline(text: str) -> str:
    """Markdown inline -> LaTeX. Code spans are escaped first so their contents stay literal."""
    code_spans = []

    def protect(match: re.Match[str]) -> str:
        code_spans.append(r"\texttt{" + escape(match.group(1)) + "}")
        return f"\x00{len(code_spans) - 1}\x00"

    # TeX opening quotes contain backticks; do not let them become Markdown code spans.
    text = re.sub(r"`([^`]+)`", protect, text)
    piece = escape(smart_quotes(text))
    piece = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", piece)
    piece = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\\emph{\1}", piece)
    for index, code in enumerate(code_spans):
        piece = piece.replace(f"\x00{index}\x00", code)
    return piece


def convert_table(rows: list[str]) -> list[str]:
    header = [c.strip() for c in rows[0].strip().strip("|").split("|")]
    body = [
        [c.strip() for c in row.strip().strip("|").split("|")] for row in rows[2:] if row.strip()
    ]
    spec = "l" + "r" * (len(header) - 1)
    out = ["\\begin{center}", "\\small", f"\\begin{{tabular}}{{{spec}}}", "\\toprule"]
    out.append(" & ".join(inline(c) for c in header) + r" \\")
    out.append("\\midrule")
    for row in body:
        row = (row + [""] * len(header))[: len(header)]
        out.append(" & ".join(inline(c) for c in row) + r" \\")
    out += ["\\bottomrule", "\\end{tabular}", "\\end{center}", ""]
    return out


def convert_markdown(text: str) -> list[str]:
    lines = text.splitlines()
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("|"):
            table = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table.append(lines[index])
                index += 1
            out += convert_table(table)
            continue
        if stripped.startswith("## "):
            out += ["", "\\subsection*{" + inline(stripped[3:]) + "}"]
        elif stripped.startswith("# "):
            pass  # the document supplies its own section title
        elif stripped in {"---", "***"} or not stripped:
            out.append("")
        elif stripped.startswith("- "):
            items = []
            while index < len(lines) and lines[index].strip().startswith("- "):
                items.append(lines[index].strip()[2:])
                index += 1
            out.append("\\begin{itemize}")
            out += ["  \\item " + inline(item) for item in items]
            out += ["\\end{itemize}", ""]
            continue
        elif re.match(r"^\d+\. ", stripped):
            items = []
            while index < len(lines) and re.match(r"^\d+\. ", lines[index].strip()):
                items.append(re.sub(r"^\d+\. ", "", lines[index].strip()))
                index += 1
            out.append("\\begin{enumerate}")
            out += ["  \\item " + inline(item) for item in items]
            out += ["\\end{enumerate}", ""]
            continue
        else:
            # Join the whole paragraph before converting: Markdown emphasis and quotes routinely
            # straddle a line break, and a per-line converter would leave the markers in the text.
            paragraph = []
            while index < len(lines):
                current = lines[index].strip()
                if (
                    not current
                    or current.startswith(("|", "## ", "# ", "- "))
                    or current
                    in {
                        "---",
                        "***",
                    }
                    or re.match(r"^\d+\. ", current)
                ):
                    break
                paragraph.append(current)
                index += 1
            out += [inline(" ".join(paragraph)), ""]
            continue
        index += 1
    return out


def results_appendix() -> str:
    cases = json.loads((ROOT / "results" / "cases.json").read_text(encoding="utf-8"))
    out = [
        "% Generated by scripts/make_appendices.py. Do not edit by hand.",
        "\\section{Full result tables}",
        "",
        "Law-side answers over answers, per model, role and hindsight condition. Law side",
        "means: as an official, upheld the law or the order; on the moral scale, answered in the",
        "upper two",
        "categories on the law's side.",
        "",
        "\\small",
        "\\begin{longtable}{llrrrrr}",
        "\\toprule",
        "Role & Hindsight & " + " & ".join(MODELS) + r" \\",
        "\\midrule",
        "\\endhead",
    ]
    for case_id, info in cases.items():
        gaps = info["gaps"]
        out.append(
            "\\multicolumn{7}{@{}p{\\dimexpr\\textwidth-2\\tabcolsep\\relax}@{}}{\\textbf{"
            + escape(case_id)
            + "} --- "
            + escape(info["title"])
            + f" (gaps: role {gaps['role']:.2f}, hindsight {gaps['hindsight']:.2f}, "
            + f"models {gaps['model']:.2f})"
            + r"} \\"
        )
        keys = sorted(
            {k for m in MODELS for k in info["law_side"].get(m, {})},
            key=lambda k: (ROLE_ORDER.index(k.split(".")[0]), k.split(".")[1] != "stripped"),
        )
        for key in keys:
            role, hindsight = key.split(".")
            values = " & ".join(escape(info["law_side"].get(m, {}).get(key, "---")) for m in MODELS)
            out.append(f"{escape(role)} & {hindsight} & {values} " + r"\\")
        out.append("\\addlinespace")
    out += ["\\bottomrule", "\\end{longtable}", ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=None)
    source = parser.parse_args().source
    (ROOT / "paper" / "results_appendix.tex").write_text(
        results_appendix(), encoding="utf-8", newline="\n"
    )
    print("wrote paper/results_appendix.tex")
    if source is None:
        return
    if not source.exists():
        sys.exit(f"case commentary not found: {source}")
    body = convert_markdown(source.read_text(encoding="utf-8"))
    cases_tex = [
        "% Case appendix, generated by scripts/make_appendices.py from the case write-up. "
        "Quoted counts are",
        "% checked by scripts/check_claims.py.",
        "\\section{The fifteen cases}",
        "",
        *body,
    ]
    (ROOT / "paper" / "cases.tex").write_text(
        "\n".join(cases_tex) + "\n", encoding="utf-8", newline="\n"
    )
    print("wrote paper/cases.tex")


if __name__ == "__main__":
    main()
