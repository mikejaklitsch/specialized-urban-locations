#!/usr/bin/env python3
"""Pinpoint brace imbalance in PDX script files.

Reports which opening brace has no closer (or which closing brace has no
opener), with surrounding context so you can see the block label.

Usage:
    python tools/brace_check.py <file>           # check one file
    python tools/brace_check.py <dir>             # check all .txt/.gui recursively
    python tools/brace_check.py <file> --context 5  # show 5 lines of context (default 2)
"""

import sys
from pathlib import Path

EXTENSIONS = {".txt", ".gui"}


def strip_comment(line: str) -> str:
    if "#" not in line:
        return line
    in_quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == "#" and not in_quote:
            if i == 0 or line[i - 1] in (" ", "\t"):
                return line[:i]
    return line


def check_file(path: Path, context_lines: int = 2) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except Exception as e:
        return [f"{path}: read error: {e}"]

    lines = text.splitlines()
    stack = []  # (line_number, line_text) for each unmatched '{'
    problems = []

    for lineno, raw_line in enumerate(lines, 1):
        stripped = strip_comment(raw_line)
        for ch in stripped:
            if ch == "{":
                stack.append((lineno, raw_line.strip()))
            elif ch == "}":
                if stack:
                    stack.pop()
                else:
                    problems.append(format_problem(
                        path, lines, lineno, "extra_close", context_lines
                    ))

    for open_lineno, open_text in stack:
        problems.append(format_problem(
            path, lines, open_lineno, "unclosed", context_lines
        ))

    return problems


def format_problem(
    path: Path, lines: list[str], lineno: int, kind: str, ctx: int
) -> str:
    if kind == "extra_close":
        header = f"{path}:{lineno}: extra '}}' with no matching opener"
    else:
        header = f"{path}:{lineno}: block opened here is never closed"

    snippet_lines = []
    start = max(0, lineno - 1 - ctx)
    end = min(len(lines), lineno + ctx)
    for i in range(start, end):
        marker = " >> " if i == lineno - 1 else "    "
        snippet_lines.append(f"  {marker}{i + 1:>5} | {lines[i]}")

    return header + "\n" + "\n".join(snippet_lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    ctx = 2
    args = sys.argv[1:]
    if "--context" in args:
        idx = args.index("--context")
        ctx = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    target = Path(args[0])
    files = []
    if target.is_file():
        files = [target]
    elif target.is_dir():
        for ext in EXTENSIONS:
            files.extend(sorted(target.rglob(f"*{ext}")))
        files = [f for f in files if ".claude" not in f.parts and "__pycache__" not in f.parts]
    else:
        print(f"Not found: {target}", file=sys.stderr)
        sys.exit(1)

    total_problems = 0
    for f in files:
        problems = check_file(f, ctx)
        if problems:
            for p in problems:
                print(p)
                print()
            total_problems += len(problems)

    if total_problems == 0:
        print(f"All balanced ({len(files)} file{'s' if len(files) != 1 else ''} checked)")
    else:
        print(f"Found {total_problems} brace problem{'s' if total_problems != 1 else ''} in {len(files)} file{'s' if len(files) != 1 else ''}")
        sys.exit(1)


if __name__ == "__main__":
    main()
