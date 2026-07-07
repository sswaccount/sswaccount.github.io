#!/usr/bin/env python3
import argparse
import shutil
import sys
import unicodedata
import re
from pathlib import Path


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    chars = []
    previous_dash = False
    for char in value:
        if char.isalnum():
            chars.append(char.lower())
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    return "".join(chars).strip("-") or "note"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unload an Obsidian note from Hugo content.")
    parser.add_argument("note", help="Path to the original Obsidian Markdown note.")
    parser.add_argument("--section", default="post", help="Hugo content section. Defaults to post.")
    parser.add_argument("--slug", help="Article slug. Defaults to the note file name.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    note = Path(args.note).expanduser()
    slug = slugify(args.slug or note.stem)
    content_root = (Path.cwd() / "content").resolve()
    target = (content_root / args.section / slug).resolve()

    try:
        target.relative_to(content_root)
    except ValueError:
        print(f"Error: target is outside content directory: {target}", file=sys.stderr)
        return 1

    if not target.exists():
        print(f"Nothing to unload: {target}")
        return 0
    if not target.is_dir():
        print(f"Error: target is not a directory: {target}", file=sys.stderr)
        return 1

    shutil.rmtree(target)
    print(f"Unloaded: {note}")
    print(f"Removed:  {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
