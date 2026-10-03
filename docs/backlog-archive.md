---
title: Backlog archive
summary: Closed backlog items, oldest first.
order: 91
---

# Backlog archive

## B01. Pilot adopt on an existing project
Status: done · Spec: superpowers/specs/2026-09-30-project-docs-design.md · Added: 2026-09-30 · Closed: 2026-09-30

Run the adopt workflow on an existing project on a branch: retire its HTML builder and
sibling `.html` files, exclude its lesson pages, convert backlog and spec status lines.
Done when `check` passes there, a commit goes through the hook, and what the pilot
taught is folded back into `references/adopt.md`.

## B07. Vendored files must not trip their own doc-map
Status: done · Added: 2026-09-30 · Closed: 2026-09-30

Resolved by D07: the tool exempts its own vendored files (pmdocs 0.1.2).

A doc-map entry like `scripts/** -> code-layout.md` also matches the vendored
`scripts/pmdocs.py`, so every `update` commit warns about stale docs (seen in the
pilot project).

- The adopt playbook and the `pmdocs.toml` template tell projects to exclude
  `scripts/pmdocs.py` and `scripts/hooks/**` from broad maps. Alternatively, the
  tool ignores its own vendored files in staleness; decide which when designing.
- The pilot project's map is fixed, and an `update` there commits without a staleness warning.

## B05. Input-hardening fixes from the final review
Status: done · Added: 2026-09-30 · Source: TODO.md · Closed: 2026-09-30

Shipped in pmdocs 0.1.3. Three user-visible edge cases, each fixed test-first.

- An empty frontmatter block (`---` then `---`) parses as frontmatter with no title
  (error "frontmatter has no title"), and `check --fix` never adds a second header.
- `install.py` creates its Windows junction without going through a shell (or with
  explicit quoting), so paths containing `&`, `^`, `%` or spaces work.
- Roadmap link text and table cells escape `*`, `_` and backticks; the status badge's
  CSS class uses only a slug of known status values.

## B08. Release gating: consumers only see tagged releases
Status: done · Added: 2026-09-30 · Closed: 2026-09-30

Done (D08): first release v0.1.5; the installed skill links `.release/`.

Before this, the installed skill is a link to this repository's working tree, so uncommitted
edits to `SKILL.md`, references and templates are live in every session, and
`sync_assets.py` puts an unreleased `pmdocs.py` into the assets during development.
`VERSION` is bumped as work happens, so "newer" means "changed", not "released".

- A `release` branch with its own worktree (settled on `.release/` inside the repo,
  gitignored); `install.py` links the skill to that worktree.
- `scripts/release.py`: refuses a dirty tree, a red suite, stale assets or an
  un-bumped `VERSION`; tags `vX.Y.Z`; fast-forwards `release` to the tag.
- The skill's **update** workflow compares against the released version; the adopt and
  init workflows vendor from the release worktree.
- Documented in `architecture.md` and recorded as a decision.
- Until this lands: don't run init/adopt/update in other projects while pm-framework
  has uncommitted work.

## B06. Test and cleanup debt from the final review
Status: done · Added: 2026-09-30 · Source: TODO.md · Closed: 2026-09-30

Done: `inbox_count()` is shared by the model and the Stop hook (a helper rather than
`load_model`, which would parse every page on every turn); the autocrlf end-to-end test
was confirmed by mutation (it fails with CRLF normalisation removed). No behavior change.

- `hook stop` reuses the shared inbox count instead of re-reading `TODO.md` itself.
- An end-to-end pre-commit test in a repo with `core.autocrlf=true`, with CRLF and
  BOM Markdown, proves that commits pass and `build --check` is clean afterwards.

## B09. Doc roots: project-docs in subfolders and monorepos
Status: done · Spec: superpowers/specs/2026-10-02-doc-roots-design.md · Added: 2026-10-02 · Closed: 2026-10-03

Today a project in a subfolder of a larger repo fails silently: staleness never fires
(git paths are repo-top-relative), the git hook is installed where git never looks, and
Claude Code hooks assume Claude was launched in the project folder. The spec defines doc
roots (any folder with `docs/pmdocs.toml`, nesting allowed, paths confined to the
territory), a repo-wide dispatching pre-commit hook, git-located Claude hook commands,
and per-root inbox/backlog/gates.

Done when the spec's test matrix passes (single subfolder, siblings, nested) including
real commits through the dispatcher, and a repo-top doc root behaves exactly as before.
Until then, the skill should refuse to set up a doc root outside the repo top rather
than fail silently — consider shipping that guard first.
