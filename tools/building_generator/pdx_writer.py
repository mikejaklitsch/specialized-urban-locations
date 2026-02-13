"""
Writer for Paradox Clausewitz script format.

Takes a Block (list of key-value pairs from pdx_parser) and writes it
back to properly formatted PDX script text.

Output uses tab indentation and is compatible with pdx-format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

# Re-use types from parser
Value = Union[str, int, float, bool, "Block"]
Block = list[tuple[str, Value]]


def _format_value(value: Value) -> str:
    """Format a single value for output."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        # Use :g to strip unnecessary trailing zeros, but ensure
        # at least one decimal so PDX sees it as a float (e.g. 1.0 not 1)
        s = f"{value:g}"
        if "." not in s and "e" not in s.lower():
            s += ".0"
        return s
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        # Quote strings that contain spaces
        if " " in value or "\t" in value:
            return f'"{value}"'
        return value
    # Block values handled separately
    return str(value)


def _is_simple_block(block: Block) -> bool:
    """Check if a block contains only bare values (for compact output)."""
    return all(k == "__bare__" and not isinstance(v, list) for k, v in block)


def _write_block(
    block: Block,
    indent: int = 0,
    lines: list[str] | None = None,
) -> list[str]:
    """
    Write a Block to a list of indented lines.

    Args:
        block: The parsed block to write.
        indent: Current indentation level (number of tabs).
        lines: Accumulator list; created if None.

    Returns:
        List of formatted lines.
    """
    if lines is None:
        lines = []

    tab = "\t" * indent

    for key, value in block:
        # Comments
        if key == "__comment__":
            lines.append(f"{tab}{value}")
            continue

        # Bare values (no key)
        if key == "__bare__":
            if isinstance(value, list):
                # Anonymous nested block
                lines.append(f"{tab}{{")
                _write_block(value, indent + 1, lines)
                lines.append(f"{tab}}}")
            else:
                lines.append(f"{tab}{_format_value(value)}")
            continue

        # Extract operator from key if present (e.g. "key >=" -> key, >=)
        op = "="
        actual_key = key
        for suffix in (" >=", " <=", " !=", " ?=", " >", " <"):
            if key.endswith(suffix):
                actual_key = key[: -len(suffix)]
                op = suffix.strip()
                break

        if isinstance(value, list):
            # Nested block
            if _is_simple_block(value) and len(value) <= 6:
                # Compact single-line for small bare-value lists
                bare_vals = " ".join(_format_value(v) for _, v in value)
                lines.append(f"{tab}{actual_key} {op} {{ {bare_vals} }}")
            else:
                lines.append(f"{tab}{actual_key} {op} {{")
                _write_block(value, indent + 1, lines)
                lines.append(f"{tab}}}")
        else:
            # Simple key = value
            lines.append(f"{tab}{actual_key} {op} {_format_value(value)}")

    return lines


def write_block(block: Block, indent: int = 0) -> str:
    """
    Convert a Block to PDX script text.

    Args:
        block: The parsed block structure.
        indent: Starting indentation level.

    Returns:
        Formatted PDX script string.
    """
    lines = _write_block(block, indent)
    return "\n".join(lines) + "\n"


def write_file(filepath: str | Path, block: Block, bom: bool = False) -> None:
    """
    Write a Block to a PDX script file.

    Args:
        filepath: Output file path.
        block: The block structure to write.
        bom: Whether to include UTF-8 BOM (vanilla files use it).
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    text = write_block(block)
    prefix = "\ufeff" if bom else ""
    filepath.write_text(prefix + text, encoding="utf-8")


def make_building(
    name: str,
    props: Block,
    prefix: str = "",
) -> tuple[str, Block]:
    """
    Convenience: create a building entry as a (key, block) pair.

    Args:
        name: Building name (e.g. "glass_guild").
        props: Block of building properties.
        prefix: Optional prefix like "REPLACE:" or "INJECT:".

    Returns:
        A (key, value) pair ready to append to a file-level Block.
    """
    key = f"{prefix}{name}" if prefix else name
    return (key, props)
