"""
Parser for Paradox Clausewitz script files (.txt).

Parses PDX script into an ordered list of (key, value) pairs (a "Block").
Duplicate keys are preserved as separate entries (not merged into lists),
matching how the game engine processes them.

Key types produced:
  - "__comment__"  -> str (the comment text including #)
  - Regular key    -> str | number | bool | Block (nested list of pairs)

A "Block" is: list[tuple[str, value]]
  where value is str | int | float | bool | Block

Bare values (no key, e.g. inside `on_actions = { action1 action2 }`)
are stored as ("__bare__", value).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Union

# Type aliases
Value = Union[str, int, float, bool, "Block"]
Block = list[tuple[str, Value]]

# Operators that can appear between key and value
OPERATORS = (">=", "<=", "!=", "?=", ">", "<", "=")

# Regex: tokenizer for PDX script
# Matches: quoted strings, comments, braces, operators, bare words/numbers
_TOKEN_RE = re.compile(
    r"""
    (?P<comment>\#[^\n]*)           |  # comment to end of line
    (?P<quoted>"[^"]*")             |  # quoted string
    (?P<brace>[{}])                 |  # opening/closing brace
    (?P<op>>=|<=|!=|\?=|>|<|=)     |  # operators
    (?P<word>[^\s={}<>!?#"]+)         # bare word/number
    """,
    re.VERBOSE,
)


def _tokenize(text: str) -> list[tuple[str, str]]:
    """Tokenize PDX script text into (type, value) pairs."""
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        val = m.group()
        tokens.append((kind, val))
    return tokens


def _try_number(s: str) -> str | int | float:
    """Try to convert a string to int or float, else return as-is."""
    # Handle yes/no booleans - keep as strings since PDX uses them that way
    if s in ("yes", "no"):
        return s
    # If the string contains a dot, parse as float (preserves 0.0 vs 0)
    if "." in s:
        try:
            return float(s)
        except ValueError:
            pass
        return s
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _parse_block(tokens: list[tuple[str, str]], pos: int) -> tuple[Block, int]:
    """
    Parse tokens starting at pos into a Block.
    Returns (block, new_pos).
    Stops at EOF or closing brace.
    """
    block: Block = []
    length = len(tokens)

    while pos < length:
        kind, val = tokens[pos]

        # Closing brace - end of this block
        if kind == "brace" and val == "}":
            return block, pos + 1

        # Comment
        if kind == "comment":
            block.append(("__comment__", val))
            pos += 1
            continue

        # Opening brace without a key - anonymous nested block (rare)
        if kind == "brace" and val == "{":
            nested, pos = _parse_block(tokens, pos + 1)
            block.append(("__bare__", nested))
            continue

        # Word or quoted string - could be a key or a bare value
        if kind in ("word", "quoted"):
            key = val.strip('"') if kind == "quoted" else val

            # Look ahead for operator
            if pos + 1 < length and tokens[pos + 1][0] == "op":
                op = tokens[pos + 1][1]
                pos += 2  # skip key and operator

                if pos >= length:
                    # Key with operator but no value (shouldn't happen, but be safe)
                    block.append((key, ""))
                    continue

                next_kind, next_val = tokens[pos]

                if next_kind == "brace" and next_val == "{":
                    # key op { ... }
                    nested, pos = _parse_block(tokens, pos + 1)
                    if op != "=":
                        # Store operator in key for non-= operators
                        key = f"{key} {op}"
                    block.append((key, nested))
                elif next_kind == "comment":
                    # key = \n # comment (value on next meaningful token)
                    # Actually this means empty value before comment
                    block.append((key, ""))
                    # Don't consume the comment, let next iteration handle it
                elif next_kind in ("word", "quoted"):
                    value = next_val.strip('"') if next_kind == "quoted" else _try_number(next_val)
                    if op != "=":
                        key = f"{key} {op}"
                    block.append((key, value))
                    pos += 1

                    # Check for inline comment after value
                    if pos < length and tokens[pos][0] == "comment":
                        block.append(("__comment__", tokens[pos][1]))
                        pos += 1
                else:
                    # Unexpected token after operator
                    block.append((key, ""))
            else:
                # No operator follows - this is a bare value
                block.append(("__bare__", _try_number(key)))
                pos += 1
                continue
        else:
            # Skip unexpected tokens
            pos += 1

    return block, pos


def parse_file(filepath: str | Path) -> Block:
    """
    Parse a PDX script file and return its contents as a Block.

    Handles:
    - UTF-8 BOM markers
    - REPLACE:key and INJECT:key prefixes (preserved in key names)
    - All PDX operators (=, >=, <=, >, <, !=, ?=)
    - Nested blocks, bare values, comments
    - Duplicate keys (preserved as separate entries)
    """
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8-sig")  # handles BOM
    return parse_text(text)


def parse_text(text: str) -> Block:
    """Parse PDX script text and return its contents as a Block."""
    tokens = _tokenize(text)
    block, _ = _parse_block(tokens, 0)
    return block


# ── Convenience helpers ──────────────────────────────────────────────

def get_values(block: Block, key: str) -> list[Value]:
    """Get all values for a given key in a block."""
    return [v for k, v in block if k == key]


def get_value(block: Block, key: str, default: Value = None) -> Value:
    """Get the first value for a given key, or default."""
    for k, v in block:
        if k == key:
            return v
    return default


def get_bare_values(block: Block) -> list[Value]:
    """Get all bare (keyless) values in a block."""
    return [v for k, v in block if k == "__bare__"]


def block_keys(block: Block) -> list[str]:
    """Get all non-special keys in a block."""
    return [k for k, _ in block if not k.startswith("__")]


def get_blocks(block: Block, key: str) -> list[Block]:
    """Get all nested blocks for a given key."""
    return [v for k, v in block if k == key and isinstance(v, list)]
