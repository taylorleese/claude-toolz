#!/usr/bin/env python3
"""Validate that every plugin listed in the marketplace manifest actually resolves.

Catches the most common way this repo breaks: a plugin renamed, moved, or
removed on disk while `.claude-plugin/marketplace.json` still advertises it.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".claude-plugin" / "marketplace.json"


def main() -> int:
    """Check each listed plugin has a directory and a readable manifest."""
    manifest = json.loads(MANIFEST.read_text())
    errors: list[str] = []
    listed = manifest.get("plugins", [])

    if not listed:
        print(f"{MANIFEST.relative_to(ROOT)} lists no plugins", file=sys.stderr)
        return 1

    for entry in listed:
        name = entry.get("name", "<unnamed>")
        source = entry.get("source")

        if not source:
            errors.append(f"{name}: no source")
            continue

        plugin_dir = (ROOT / source).resolve()
        if not plugin_dir.is_dir():
            errors.append(f"{name}: source directory missing ({source})")
            continue

        plugin_json = plugin_dir / ".claude-plugin" / "plugin.json"
        if not plugin_json.is_file():
            errors.append(f"{name}: missing .claude-plugin/plugin.json")
            continue

        try:
            declared = json.loads(plugin_json.read_text()).get("name")
        except json.JSONDecodeError as exc:
            errors.append(f"{name}: plugin.json is not valid JSON ({exc})")
            continue

        if declared != name:
            errors.append(f"{name}: plugin.json declares name '{declared}'")

    # Flag directories on disk that nobody listed — an easy thing to forget
    # after adding a plugin.
    sources = {entry.get("source", "").removeprefix("./") for entry in listed}
    for path in sorted((ROOT / "plugins").iterdir()):
        if path.is_dir() and f"plugins/{path.name}" not in sources:
            errors.append(f"{path.name}: on disk but not listed in marketplace.json")

    if errors:
        print("Plugin manifest problems:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"All {len(listed)} plugins resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
