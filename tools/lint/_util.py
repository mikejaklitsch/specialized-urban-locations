"""Shared utilities for lint checks."""

import re

QUOTED_RE = re.compile(r'"[^"]*"')


def strip_comment(line: str) -> str:
    """Remove the comment portion of a line, respecting quoted strings.

    A '#' is only a comment start when not inside quotes and preceded by
    whitespace (or at column 0). Inside bare tokens like 'christian#miaphysite'
    the '#' is part of the identifier.
    """
    if "#" not in line:
        return line
    in_quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == '#' and not in_quote:
            if i == 0 or line[i - 1] in (' ', '\t'):
                return line[:i]
    return line
