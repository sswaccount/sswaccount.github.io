#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urlparse


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"}
OBSIDIAN_EMBED_RE = re.compile(r"!\[\[([^\]]+)\]\]")
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


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
    parser = argparse.ArgumentParser(
        description="Load an Obsidian Markdown note into Hugo content with local images."
    )
    parser.add_argument("note", help="Path to the Obsidian Markdown note.")
    parser.add_argument(
        "--vault",
        default="/Users/ssw/data/SELF/obsidian",
        help="Obsidian vault root. Defaults to /Users/ssw/data/SELF/obsidian.",
    )
    parser.add_argument("--section", default="post", help="Hugo content section. Defaults to post.")
    parser.add_argument("--slug", help="Article slug. Defaults to the note file name.")
    parser.add_argument("--title", help="Article title. Defaults to the note file name.")
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="Article category. Can be used multiple times.",
    )
    parser.add_argument("--tag", action="append", dest="tags", help="Article tag. Can be used multiple times.")
    parser.add_argument("--draft", action="store_true", help="Mark imported article as draft.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing target article directory.",
    )
    return parser.parse_args()


def is_external_url(path: str) -> bool:
    parsed = urlparse(path)
    return parsed.scheme in {"http", "https", "data"}


def split_markdown_target(target: str) -> tuple[str, str]:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]

    suffix = ""
    for marker in ("#", "?"):
        index = target.find(marker)
        if index != -1:
            suffix = target[index:]
            target = target[:index]
            break
    return unquote(target), suffix


def candidate_paths(raw_path: str, note_dir: Path, vault: Path) -> list[Path]:
    path_text = raw_path.strip()
    if is_external_url(path_text):
        return []

    path_text, _ = split_markdown_target(path_text)
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return [path]

    return [
        note_dir / path,
        vault / path,
        vault / "assert" / path.name,
        vault / "assets" / path.name,
        vault / "attachments" / path.name,
    ]


def resolve_asset(raw_path: str, note_dir: Path, vault: Path) -> Optional[Path]:
    for candidate in candidate_paths(raw_path, note_dir, vault):
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None


def unique_name(dest_dir: Path, source: Path, used_names: set[str]) -> str:
    stem = slugify(source.stem)
    suffix = source.suffix.lower()
    name = f"{stem}{suffix}"
    counter = 2
    while name in used_names or (dest_dir / name).exists():
        name = f"{stem}-{counter}{suffix}"
        counter += 1
    used_names.add(name)
    return name


def copy_asset(source: Path, dest_dir: Path, used_names: set[str], copied: dict[Path, str]) -> str:
    source = source.resolve()
    if source in copied:
        return copied[source]

    dest_name = unique_name(dest_dir, source, used_names)
    shutil.copy2(source, dest_dir / dest_name)
    copied[source] = dest_name
    return dest_name


def convert_obsidian_embed(
    match: re.Match[str],
    note_dir: Path,
    vault: Path,
    dest_dir: Path,
    used_names: set[str],
    copied: dict[Path, str],
    missing: list[str],
) -> str:
    raw = match.group(1).strip()
    target = raw.split("|", 1)[0].strip()
    alt = raw.split("|", 1)[1].strip() if "|" in raw else Path(target).stem
    source = resolve_asset(target, note_dir, vault)
    if not source or source.suffix.lower() not in IMAGE_EXTENSIONS:
        missing.append(target)
        return match.group(0)

    dest_name = copy_asset(source, dest_dir, used_names, copied)
    return f"![{alt}]({quote(dest_name)})"


def convert_markdown_image(
    match: re.Match[str],
    note_dir: Path,
    vault: Path,
    dest_dir: Path,
    used_names: set[str],
    copied: dict[Path, str],
    missing: list[str],
) -> str:
    alt = match.group(1)
    raw_target = match.group(2).strip()
    target, suffix = split_markdown_target(raw_target)
    if is_external_url(target):
        return match.group(0)

    source = resolve_asset(target, note_dir, vault)
    if not source or source.suffix.lower() not in IMAGE_EXTENSIONS:
        missing.append(target)
        return match.group(0)

    dest_name = copy_asset(source, dest_dir, used_names, copied)
    return f"![{alt}]({quote(dest_name)}{suffix})"


def has_front_matter(markdown: str) -> bool:
    return markdown.startswith("---\n") or markdown.startswith("+++\n")


def normalize_front_matter_date(markdown: str) -> str:
    if not markdown.startswith("---\n"):
        return markdown

    end = markdown.find("\n---", 4)
    if end == -1:
        return markdown

    front_matter = markdown[4:end]
    body = markdown[end:]

    def replace_date(match: re.Match[str]) -> str:
        raw_value = match.group(1).strip().strip('"').strip("'")
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(raw_value, fmt).astimezone()
                return f'date: "{parsed.isoformat(timespec="seconds")}"'
            except ValueError:
                pass
        return match.group(0)

    front_matter = re.sub(r"(?m)^date:\s*(.+?)\s*$", replace_date, front_matter, count=1)
    return f"---\n{front_matter}{body}"


def toml_array(values: list[str]) -> str:
    return "[" + ", ".join(f'"{value.replace(chr(34), chr(92) + chr(34))}"' for value in values) + "]"


def front_matter(title: str, draft: bool, categories: list[str], tags: list[str]) -> str:
    date = datetime.now().astimezone().isoformat(timespec="seconds")
    draft_value = "true" if draft else "false"
    escaped_title = title.replace('"', '\\"')
    return (
        f'+++\ntitle = "{escaped_title}"\ndate = "{date}"\ndraft = {draft_value}\n'
        f"categories = {toml_array(categories)}\n"
        f"tags = {toml_array(tags)}\n"
        "+++\n\n"
    )


def main() -> int:
    args = parse_args()
    note = Path(args.note).expanduser().resolve()
    vault = Path(args.vault).expanduser().resolve()
    if not note.exists() or not note.is_file():
        print(f"Error: note not found: {note}", file=sys.stderr)
        return 1
    if not vault.exists() or not vault.is_dir():
        print(f"Error: vault not found: {vault}", file=sys.stderr)
        return 1

    slug = slugify(args.slug or note.stem)
    title = args.title or note.stem
    dest_dir = Path.cwd() / "content" / args.section / slug
    dest_md = dest_dir / "index.md"

    if dest_dir.exists():
        if not args.overwrite:
            print(f"Error: target exists: {dest_dir}", file=sys.stderr)
            print("Use --overwrite to replace index.md and copy images again.", file=sys.stderr)
            return 1
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    markdown = note.read_text(encoding="utf-8")
    used_names: set[str] = set()
    copied: dict[Path, str] = {}
    missing: list[str] = []

    markdown = MARKDOWN_IMAGE_RE.sub(
        lambda match: convert_markdown_image(
            match, note.parent, vault, dest_dir, used_names, copied, missing
        ),
        markdown,
    )
    markdown = OBSIDIAN_EMBED_RE.sub(
        lambda match: convert_obsidian_embed(
            match, note.parent, vault, dest_dir, used_names, copied, missing
        ),
        markdown,
    )

    if not has_front_matter(markdown):
        categories = args.categories or ["Notes"]
        tags = args.tags or [slug]
        markdown = front_matter(title, args.draft, categories, tags) + markdown
    else:
        markdown = normalize_front_matter_date(markdown)

    dest_md.write_text(markdown, encoding="utf-8")

    print(f"Loaded:   {note}")
    print(f"Article:  {dest_md}")
    if copied:
        print("Images:")
        for source, dest_name in copied.items():
            print(f"  {source} -> {dest_dir / dest_name}")
    if missing:
        print("Missing image references:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
