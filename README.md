# SswSpace Blog

Hugo blog powered by `hugo-theme-stack`.

## Local Preview

```bash
./build
```

or:

```bash
./build --show
```

Open `http://localhost:1313/`.

## Obsidian Notes

Load a note into the blog:

```bash
./build --load /path/to/note.md
```

Reload a changed note:

```bash
./build --reload /path/to/note.md
```

Remove a loaded note from the blog:

```bash
./build --unload /path/to/note.md
```

The script copies local Obsidian images into the article folder and rewrites image links.

## Publish

Build, commit, and push:

```bash
./build --upload
```

Load/reload/remove and publish in one command:

```bash
./build --load /path/to/note.md --upload
./build --reload /path/to/note.md --upload
./build --unload /path/to/note.md --upload
```

## Front Matter

Recommended Obsidian template:

```yaml
---
title: "{{title}}"
date: "{{date}} {{time}}"
categories:
  - Notes
tags:
  - todo
draft: false
---
```
