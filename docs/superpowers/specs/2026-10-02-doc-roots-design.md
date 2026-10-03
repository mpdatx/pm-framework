---
title: Doc roots — project-docs in subfolders and monorepos
status: approved
created: 2026-10-02
backlog: [B09]
---

# Doc roots: project-docs in subfolders and monorepos

## Problem

project-docs assumes the documented project is the git repository's top level. Placed in
a subfolder (`apps/foo/` of a larger repo), it **fails silently**. A probe on 0.3.2 showed:

- **Staleness never fires.** `git diff --name-only` reports paths relative to the repo
  top (`apps/foo/src/a.py`); the doc-map is relative to the project (`src/**`), so
  nothing matches. `git ls-files` *is* cwd-relative, so coverage happens to work.
- **The git hook never runs.** `install-hooks` sets `core.hooksPath=scripts/hooks`,
  which git resolves from the repo top, where no hook exists. It reports success; a
  commit with a broken page went through.
- **Claude Code hooks point nowhere** unless Claude is launched in the subfolder: their
  command is `"$CLAUDE_PROJECT_DIR/scripts/pmdocs.py"`.
- **init** requires the project root to be `git rev-parse --show-toplevel`.

## Definitions

- **Repo top**: `git rev-parse --show-toplevel`.
- **Doc root**: a directory containing `docs/pmdocs.toml`. It may be the repo top or any
  subfolder. A repo may contain several.
- **Nested doc root**: a doc root inside another doc root's tree (an umbrella `docs/` at
  the repo top plus `packages/*/docs/`).
- **Territory** of a doc root: its directory tree, minus the trees of doc roots nested
  inside it.

## Rules

1. **Everything a doc root owns is relative to it.** `[[map]]` paths and pages,
   `[coverage]`, `[[site.extra]]` paths, `TODO.md`, `README.md` (the default extra
   page), `docs/site/`, gates, backlog and archives all resolve against the doc root.
2. **Paths stay inside the territory.** A `[[map]]`, `[coverage]` or `[[site.extra]]`
   path that leaves the doc root (`../…`) is an ERROR. Shared code is documented by the
   doc root that contains it.
3. **Nested doc roots own their subtree.** The outer doc root ignores everything inside
   a nested one: its pages are not the outer site's pages, its files are not in the
   outer coverage or staleness, and the outer `[paths] exclude` need not mention it.
   Discovery: every tracked `**/docs/pmdocs.toml`.
4. **Git output is converted to doc-root paths.** Changed-file sets use
   `git diff --relative` (paths relative to the doc root, changes outside it dropped) and
   are then filtered to the territory. Index export and `checkout-index` operate on
   territory files only.
5. **The vendored tool knows its doc root.** `scripts/pmdocs.py` resolves its doc root
   from its own location (`<root>/scripts/pmdocs.py` → `<root>`, confirmed by
   `docs/pmdocs.toml`), not from the current directory. Walking up from the cwd remains
   the fallback for a tool run from elsewhere. Every hook therefore works whatever
   directory git or Claude Code was started in.
6. **One git hook per repository, dispatching to every doc root.** git has one
   `core.hooksPath` per repo, so the vendored `scripts/hooks/pre-commit` becomes a
   dispatcher:
   - It lists every tracked `**/docs/pmdocs.toml`.
   - For each doc root with staged changes in its territory, it runs that root's own
     `scripts/pmdocs.py hook pre-commit`, with the doc root as cwd.
   - It blocks (exit 1) if any returns 10. As now, a crash or missing `uv` lets the
     commit through with a message.

   `install-hooks` sets `core.hooksPath` to the installing doc root's `scripts/hooks`,
   **as a repo-top-relative path**, if none is set. If one is already set to another
   doc root's pmdocs hook, it leaves it (that dispatcher already covers this root) and
   says so. `--status` reports which doc roots the dispatcher will cover, and warns if
   the hooks path points at a missing hook.
7. **Claude Code hooks live in the repo top's `.claude/settings.json`, one set per doc
   root.** Each entry calls its own doc root's tool through git rather than the launch
   directory:

   ```sh
   uv run --quiet "$(git rev-parse --show-toplevel)/apps/foo/scripts/pmdocs.py" hook stop
   ```

   For a doc root at the repo top the path is just `scripts/pmdocs.py`, as today.
   - **post-edit** stays silent for files outside its territory.
   - **stop** and **session-start** report only their own doc root, prefixed with the
     project's `[site] title` when the repo has more than one doc root, so several
     projects' notes stay distinguishable.
   - Existing entries using `$CLAUDE_PROJECT_DIR/scripts/pmdocs.py` are rewritten to
     the new form by `install-hooks`.
8. **Inbox, backlog and gates are per doc root.** Each project has its own `TODO.md`,
   backlog, gates and roadmap. Session-start lists every doc root's open gates, each
   under its project name.
9. **`.gitattributes` lines go in the doc root's own `.gitattributes`.** Git applies
   nested `.gitattributes` relative to their directory, so the existing lines work
   unchanged.

## Skill changes

- **init** and **adopt** ask where the doc root is, defaulting to the repo top. If the
  repo already has doc roots, they list them, and state whether the new one nests in
  one (allowed) or contains one (allowed, and then the outer one's territory shrinks).
- init step 1's "project root is the repo top" check becomes "the doc root is inside
  this repo".
- **update** runs per doc root. In a repo with several, it updates each one in turn and
  re-runs `install-hooks` once.

## Compatibility

A doc root at the repo top behaves exactly as before. That covers every existing
adoption, so no migration is needed. `install-hooks` upgrades the Claude hook commands
in place.

## Testing

Throwaway repos for:

- a single subfolder doc root;
- two sibling doc roots;
- an umbrella doc root with a nested one.

Each case asserts:

- **Staleness:** fires per territory, and nested files don't trigger the outer root.
- **Coverage, pages and site:** exclude nested trees.
- **Path guard:** `../` map paths are an ERROR.
- **Real `git commit` through the dispatcher:** a broken page in either project
  blocks; a clean commit touching both builds both sites; a commit touching only one
  runs only that one.
- **Hooks:** post-edit, stop and session-start invoked from the repo top and from
  inside a doc root resolve the right project.
- **install-hooks:** run from a second doc root keeps the existing hooks path, rewrites
  old commands, and `--status` lists the covered roots.

## Out of scope

- Docs that span several doc roots (a cross-project roadmap or index). Each doc root
  stays self-contained.
- Doc roots outside a git repository.
