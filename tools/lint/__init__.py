#!/usr/bin/env python3
"""Pre-deploy lint runner. Auto-discovers check modules in this directory."""

import importlib
import inspect
import json
import pkgutil
import sys
from pathlib import Path

MANIFEST = ".claude/lint_manifest.json"


def discover_checks():
    """Import all sibling modules that have a run(mod_root) function."""
    checks = []
    pkg_path = Path(__file__).parent
    for info in pkgutil.iter_modules([str(pkg_path)]):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f".{info.name}", package=__name__)
        if hasattr(mod, "run"):
            checks.append((info.name, mod.run))
    return checks


def load_manifest(mod_root: Path) -> dict[str, float]:
    """Load {relative_path: mtime} for files that passed all checks."""
    p = mod_root / MANIFEST
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


def save_manifest(mod_root: Path, manifest: dict[str, float]):
    p = mod_root / MANIFEST
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2) + "\n")


def changed_files(mod_root: Path, manifest: dict[str, float],
                  exts: tuple[str, ...] = (".txt", ".gui", ".yml")) -> set[Path]:
    """Return files that need checking: modified since last pass, or never passed."""
    changed = set()
    for f in mod_root.rglob("*"):
        if f.suffix not in exts:
            continue
        if ".claude" in f.parts or "__pycache__" in f.parts:
            continue
        rel = str(f.relative_to(mod_root))
        mtime = f.stat().st_mtime
        if rel not in manifest or manifest[rel] != mtime:
            changed.add(f)
    return changed


def run_all(mod_root: Path, skip: set[str] | None = None, full: bool = False) -> dict[str, list[str]]:
    """Run all lint checks and return {check_name: [errors]}.

    Passes the set of changed files to each check. Checks that accept a
    `changed` parameter will only scan those files; others scan everything.
    After a clean run, updates the manifest with passing files' mtimes.
    """
    skip = skip or set()
    manifest = load_manifest(mod_root)

    if full:
        changed = None
    else:
        changed = changed_files(mod_root, manifest)
        if not changed:
            return {}

    results = {}
    for name, fn in discover_checks():
        if name in skip:
            continue
        try:
            sig = inspect.signature(fn)
            if "changed" in sig.parameters:
                errors = fn(mod_root, changed=changed)
            else:
                errors = fn(mod_root)
        except Exception as e:
            errors = [f"check crashed: {e}"]
        if errors:
            results[name] = errors

    if not results and changed is not None:
        for f in changed:
            rel = str(f.relative_to(mod_root))
            manifest[rel] = f.stat().st_mtime
        save_manifest(mod_root, manifest)

    return results


def main():
    """CLI entry point: python -m tools.lint [mod_root] [--full]"""
    args = sys.argv[1:]
    full = "--full" in args
    args = [a for a in args if a != "--full"]

    if args:
        mod_root = Path(args[0])
    else:
        mod_root = Path(__file__).resolve().parent.parent.parent

    label = "Linting (full)" if full else "Linting"
    print(f"{label}: {mod_root.name}")
    results = run_all(mod_root, full=full)

    if not results:
        print("  All checks passed.")
        return 0

    total = 0
    for name, errors in sorted(results.items()):
        print(f"\n  [{name}] ({len(errors)} issue{'s' if len(errors) != 1 else ''})")
        for err in errors:
            print(f"    {err}")
        total += len(errors)
    print(f"\n  {total} issue{'s' if total != 1 else ''} found.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
