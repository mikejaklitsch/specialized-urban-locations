"""Shared utilities for lint checks."""

import re

QUOTED_RE = re.compile(r'"[^"]*"')


def strip_comment(line: str) -> str:
    """Remove the comment portion of a line, respecting quoted strings.

    GUI files use #R, #G etc. as color codes inside quotes — those aren't comments.
    """
    if "#" not in line:
        return line
    in_quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == '#' and not in_quote:
            return line[:i]
    return line
