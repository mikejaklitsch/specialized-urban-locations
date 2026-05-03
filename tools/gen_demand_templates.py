#!/usr/bin/env python3
"""Generate per-pop demand breakdown tooltip templates.

Reads the nobles template from aaa_sul_location_tooltips.gui as a base,
creates 7 copies (one per pop type) with baked-in script value names,
and replaces the old template(s) in place.

The base template uses `block "tier_X" { ... }` wrappers (for blockoverride).
Since each per-pop template has the correct values baked in, these wrappers
are unwrapped (content kept, block/closing-brace removed).
"""
import os, re

GUI_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "in_game", "gui", "shared", "aaa_sul_location_tooltips.gui")

POPS = [
    ("nobles",    "Nobles",    "sul_nobles_"),
    ("clergy",    "Clergy",    "sul_clergy_"),
    ("burghers",  "Burghers",  "sul_burghers_"),
    ("soldiers",  "Soldiers",  "sul_soldiers_"),
    ("laborers",  "Laborers",  "sul_laborers_"),
    ("peasants",  "Peasants",  "sul_peasants_"),
    ("tribesmen", "Tribesmen", "sul_tribesmen_"),
]

TIERS = ["necessity", "basic", "common", "upper", "luxury", "exotic"]


def find_brace_end(text, start):
    """Find the position after the closing brace matching the first { at/after start."""
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("Unmatched brace")


def unwrap_block(lines):
    """Remove `block "tier_X" {` lines and their matching `}`, keeping inner content.

    Works on a list of lines. For each block wrapper found, removes the opening
    line and the matching closing-brace line, dedenting the content by one tab.
    """
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        is_block = False
        for tier in TIERS:
            if stripped == f'block "tier_{tier}" ' + '{':
                is_block = True
                break
        if is_block:
            # Find matching close by counting braces
            depth = 1
            inner_start = i + 1
            j = inner_start
            while j < len(lines):
                depth += lines[j].count("{") - lines[j].count("}")
                if depth <= 0:
                    # j is the closing brace line — skip it
                    # Dedent inner lines by one tab
                    for k in range(inner_start, j):
                        l = lines[k]
                        if l.startswith("\t"):
                            l = l[1:]
                        result.append(l)
                    i = j + 1
                    break
                j += 1
            else:
                # Should not happen — fallback: keep line as-is
                result.append(line)
                i += 1
        else:
            result.append(line)
            i += 1
    return result


def main():
    with open(GUI_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the first template (may be the old single or first of previous run)
    # Look for any template matching the pattern
    marker_re = re.compile(r"template sul_(?:\w+_)?demand_breakdown_tooltip \{")
    m = marker_re.search(content)
    if not m:
        print("ERROR: No demand breakdown template found")
        return

    # Find all consecutive templates (from previous runs there may be 7)
    start = m.start()
    end = find_brace_end(content, start)

    # Check for more templates immediately following
    while True:
        rest = content[end:].lstrip("\n")
        m2 = marker_re.match(rest)
        if m2:
            offset = content.index(rest[:20], end)
            end = find_brace_end(content, offset)
        else:
            break

    # Extract the FIRST template as the base (it should use sul_nobles_ values)
    first_end = find_brace_end(content, start)
    base = content[start:first_end]

    # Verify it's the nobles base
    if "sul_nobles_" not in base and "sul_demand_breakdown_tooltip" not in base:
        print("ERROR: First template doesn't look like the nobles base")
        return

    # Normalize: ensure the base uses sul_nobles_ and the generic name
    if "template sul_nobles_demand_breakdown_tooltip" in base:
        base = base.replace("template sul_nobles_demand_breakdown_tooltip",
                            "template sul_demand_breakdown_tooltip")
    # If base already has per-pop substitutions from a prior run, reset to nobles
    for pop_key, _, prefix in POPS:
        if pop_key == "nobles":
            continue
        if prefix in base:
            base = base.replace(prefix, "sul_nobles_")
            base = base.replace(f"template sul_{pop_key}_demand_breakdown_tooltip",
                                "template sul_demand_breakdown_tooltip")

    base_lines = base.split("\n")

    templates = []
    for pop_key, pop_name, prefix in POPS:
        t = base
        t = t.replace("template sul_demand_breakdown_tooltip",
                       f"template sul_{pop_key}_demand_breakdown_tooltip")
        t = t.replace("sul_nobles_", prefix)
        t = t.replace(
            'block "header_text" { raw_text = "#T Demand Breakdown#!" }',
            f'raw_text = "#T {pop_name} — Demand Breakdown#!"'
        )
        # Unwrap block "tier_*" wrappers
        t_lines = unwrap_block(t.split("\n"))
        templates.append("\n".join(t_lines))

    new_templates = "\n\n".join(templates)
    content = content[:start] + new_templates + content[end:]

    with open(GUI_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Replaced templates with {len(POPS)} per-pop templates")


if __name__ == "__main__":
    main()
