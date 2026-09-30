---
title: Architecture
summary: The single-file tool, how it is vendored, and how the hooks call it.
order: 20
---

# Architecture

## Overview

`tool/pmdocs.py` is the one source of the tool. `scripts/sync_assets.py` copies it (and
`tool/hooks/pre-commit`) byte-for-byte into `skill/project-docs/assets/` — what the skill
vendors into other projects — and into this repository's own `scripts/`, which the hooks
here run. `scripts/release.py` tags a version and moves the release worktree
(`.release/`) to it; `install.py` links the *released* `skill/project-docs/` into
`~/.claude/skills/`, so other projects never see work in progress.

```
tool/pmdocs.py ──sync──▶ skill/project-docs/assets/pmdocs.py
               └─sync──▶ scripts/pmdocs.py (dogfood)

master ──release.py (tag vX.Y.Z)──▶ .release/ (release branch) ◀──link── ~/.claude/skills/project-docs
                                                                              │ init / adopt / update
                                                                              ▼
                                                                  <project>/scripts/pmdocs.py
```

## Releases

Development happens on `master`; nothing there is visible to other projects until it is
released. `uv run scripts/release.py`:

1. refuses unless it is on `master`, the tree is clean, the vendored copies match `tool/`
   (`sync_assets`), `VERSION` is higher than the last `vX.Y.Z` tag, and the tests pass;
2. tags `v<VERSION>`;
3. fast-forwards the `release` branch, checked out as a worktree at `.release/`
   (gitignored), to that tag, creating it on the first release.

`install.py` links `.release/skill/project-docs` by default; `--dev` links the working
tree for trying skill changes before a release. Because an adopted project's **update**
compares its vendored `VERSION` with the installed skill's, "newer" now means "a newer
release". Bump `VERSION` in `tool/pmdocs.py` once per release, not per change.

## Components

### The tool, by section

| Section | Responsibility |
|---|---|
| core | `norm`, globs, `read_text` (BOM/CRLF), `load_config`, frontmatter |
| parsing | backlog items and decisions (`parse_items`), `next_id`, inbox count |
| model | `load_model`, `validate`, link and anchor checking |
| git, drift, staleness | `changed_files`, `staleness`, `coverage`, `drift_static`, `drift_stale_progress`; staleness and coverage skip the tool's own `VENDORED` files |
| fixes and check | archive closed items, add draft frontmatter, `cmd_check` |
| roadmap | `render_roadmap` (deterministic: static drift only) |
| site | markdown-it rendering, link rewriting, nav (default groups, or `[site] nav` order), collapsible TOC, `[site] extra` pages under `site/extra/` (named groups, each page showing its group's `about` and its source path; the root README by default), `build` |
| hooks | `hook_pre_commit` (exit 10 blocks), `hook_post_edit`, `hook_stop` |
| install-hooks | `core.hooksPath` and `.claude/settings.json` merge/removal |
| cli | argparse; `cmd_*` dispatch; errors exit 2 |

### The pre-commit flow

1. Skip on `PMDOCS_SKIP=1` or mid-merge/rebase.
2. Apply fixes to files the user has fully staged; stage the fixed files.
3. Export the index's `docs/` and `TODO.md` to a temp dir; validate there.
4. Any ERROR → exit 10 (the sh hook turns that into a blocked commit). Validation
   there sees only the export, so any check of a path outside `docs/` must also consult
   `outside_root` (the working tree); `test_check_and_hook_report_the_same_errors`
   guards that `check` and the hook agree.
5. Build in the temp dir; copy the generated files (`.html` and assets) and
   `roadmap.md` back, deleting only generated files that are no longer produced — any
   other file in `docs/site/` is left alone — and stage exactly those paths.

### The installer

`install.py` (standard library only) links the released `skill/project-docs/`
(`.release/…`, or the working tree with `--dev`) into `~/.claude/skills/project-docs`:
a symlink where the OS allows it, a directory junction (created through the Win32 API,
never a shell) on Windows without symlink privilege, or a marked copy with `--copy`. It
refuses to replace or remove a directory it did not create. With no `.release/`, it
links the checkout if this is a user's clone of the published repository — the checkout
*is* a release — and refuses with instructions in a maintainer's clone, so B08's
guarantee holds there. A maintainer's clone is recognised by its local `release` branch,
which only `release.py` creates and which is never pushed; version tags don't count,
because they are published and arrive with every clone.

## Code pointers

| Area | Where |
|---|---|
| Tool | `tool/pmdocs.py` |
| Git hook | `tool/hooks/pre-commit` |
| Asset sync | `scripts/sync_assets.py` |
| Releases | `scripts/release.py`, worktree `.release/` |
| Installer | `install.py` |
| Tests | `tests/` (one module per tool section) |
