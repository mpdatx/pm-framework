---
title: project-docs — a portable documentation and work-status convention
status: shipped
created: 2026-09-30
backlog: [B01]
---

# project-docs: design

## Purpose

Projects built mostly by agents drift: architecture and product docs fall behind the
code, and the status of planned work is scattered across TODO files, spec status lines,
plan checkboxes and CLAUDE.md notes that nothing reconciles. This project defines one
convention for keeping those current, a vendored tool that enforces it mechanically,
and a Claude Code skill (`project-docs`) that sets a project up, migrates existing
projects, and triages ad-hoc work into a backlog.

**Success means:** one skill invocation sets a project up; from then on stale docs are
flagged at edit time (Claude hooks) and at commit time (git hook); work status lives in
one mechanically-checked place; the user can jot work into `TODO.md` at any time and
the skill turns it into specified backlog items.

## Prior art (surveyed 2026-09-30)

Four agent-built projects that had each grown part of this were surveyed:

| Project | Keeps | Lesson |
|---|---|---|
| A: a content-and-engine project | A Markdown→HTML builder with `--check`, backlog B-nn, D-nn decisions | A check nothing calls is not enforcement. |
| B: a data pipeline with a CLI and UI | A doc-map, Claude PostToolUse/Stop reminders, a pre-commit rebuild, a docs test gate | The doc-map and agent-time reminders work; pre-commit rebuilding from the working tree is wrong; hooks config duplicated outside the repo drifts. |
| C: a simulation project | A roadmap generated from specs/plans/TODO, drift detection, `core.hooksPath` install | "A pointer cannot drift." Plan checkboxes are never ticked — not a progress signal. Stamp from content, not HEAD or clock. |
| D: a desktop app | Nothing automated; a very large TODO.md and a decision log thousands of lines long | Unbounded status files; batch "catch-up" doc commits; the user's TODO.md jotting is a real workflow worth keeping. |

Common failures across all four: docs updated in catch-up commits after the code;
spec `**Status:**` lines disagreeing with reality; status spread over 3–5 places;
agent-facing text (CLAUDE.md) going stale unchecked.

## Decisions

1. **Distribution: vendored copy.** The skill copies a versioned tool into each project.
   Projects are self-contained; hooks work in every clone and worktree; updating is
   re-running the skill.
2. **Status model: frontmatter + generated roadmap.** Specs and plans carry YAML
   frontmatter status; a `docs/backlog.md` holds IDed items; the tool generates the
   roadmap and detects drift.
3. **Enforcement: tiered.** Mechanical issues are auto-fixed or block; judgment issues
   (code changed, mapped doc didn't) warn.
4. **Agent hooks: yes.** PostToolUse (edit) and Stop hooks, committed in the project's
   `.claude/settings.json`, never blocking.
5. **Runtime: Python via `uv run`.** Single file with PEP 723 inline metadata.
6. **Adoption: init + adopt modes; pilot adopt on one existing project** (project A).
   The others are migrated later, outside this effort.
7. **Cross-platform.** Linux, macOS and Windows are all first-class. No PowerShell,
   no bash-isms; hooks are POSIX `sh` (Git for Windows ships `sh`); everything else is
   Python using `pathlib`.
8. **`TODO.md` inbox.** The user may add items ad hoc to `TODO.md` at the repo root at
   any time. It is free-form and user-owned; the skill triages it into the backlog.

## 1. The convention

### Layout of an adopting project

```
TODO.md                  inbox — user-owned, free-form, ad hoc (see "Inbox" below)
docs/
  pmdocs.toml            config: site title, spec/plan dirs, [[map]] doc-map
  index.md               overview + "what to read when"
  product.md             what it is, who it's for, non-goals
  architecture.md        may grow into architecture/*.md
  decisions.md           D-nn records
  backlog.md             open work only, B-nn items
  backlog-archive.md     closed items, moved here, never deleted
  roadmap.md             GENERATED
  superpowers/specs/     specs (superpowers' default location)
  superpowers/plans/     plans
  site/                  GENERATED HTML, committed
scripts/pmdocs.py        vendored tool
scripts/hooks/           vendored git hooks (core.hooksPath points here)
.claude/settings.json    PostToolUse + Stop hook entries (merged, not overwritten)
```

Spec and plan directories are configurable in `pmdocs.toml` for projects that keep
them elsewhere; the defaults match the superpowers skills.

### Frontmatter

YAML between `---` lines on every page under `docs/` except generated files.

Reference pages:

```yaml
title: Architecture
summary: How the pieces fit together.
order: 20
```

Specs:

```yaml
title: Rising parts
status: draft | approved | in-progress | shipped | superseded | abandoned
created: 2026-09-29
backlog: [B07]
superseded_by: superpowers/specs/2026-10-10-rising-parts-v2-design.md   # when superseded
```

Plans:

```yaml
title: Rising parts implementation
status: draft | approved | in-progress | shipped | abandoned
spec: superpowers/specs/2026-09-29-rising-parts-design.md
```

There is no `updated` field — git history is the authority, and a hand-maintained date
is one more thing to drift.

### Backlog items

`docs/backlog.md` and `docs/backlog-archive.md` hold items as H2 headings, each followed
by exactly one metadata line, then free prose:

```markdown
## B07. Rising parts pass through host
Status: in-progress · Spec: superpowers/specs/2026-09-29-rising-parts-design.md · Added: 2026-09-20 · Source: TODO.md

What and why, acceptance criteria, open questions.
```

- `Status` is required: `open | in-progress | blocked | done | dropped`.
- `Added` is required (ISO date). `Spec`, `Source` and `Closed` (ISO date) are optional.
- IDs are `B` + zero-padded number, never reused; the next ID is max(backlog ∪ archive) + 1.
- Metadata fields are separated by ` · ` (U+00B7 with spaces); the parser also accepts `|`.

### Decisions

`docs/decisions.md` holds `## Dnn. Title` records with **Context / Decision / Why /
Consequences** paragraphs. A reversed decision gets `Status: superseded by Dmm` beneath
its heading; its text is not rewritten. IDs are never reused.

### Inbox: `TODO.md`

- Lives at the repo root. Belongs to the user.
- Free-form: bullets, checkboxes, prose, anything. The tool never validates its format.
- Agents may **append** to it (e.g. "noted during X") but never rewrite or reorder the
  user's text.
- Items leave the inbox only through **triage** (skill workflow, below), and only after
  the user approves the backlog item that replaces them.
- The tool counts inbox items (top-level list items, or non-blank paragraphs when there
  are none) and reports the count in `check`, the Stop hook and the roadmap. It never
  blocks on the inbox.

### Drift rules

| Rule | Tier |
|---|---|
| Item with `done`/`dropped` still in `backlog.md` | auto-fixable (`check --fix` moves it to the archive, adds `Closed:` if missing) |
| Open item in `backlog-archive.md` | blocking |
| Spec has a plan with status ≠ draft, but spec is still `draft` | warning |
| Spec `shipped` but a linked backlog item is still `open`/`in-progress` | warning |
| Plan `shipped` but its spec isn't `shipped`/`superseded` | warning |
| Reference to a missing B-id, D-id, spec or plan | blocking |
| Duplicate B-id or D-id | blocking |
| Spec or plan with no frontmatter | auto-fixable (`--fix` adds `title` from the H1, `status: draft`, and for a plan `spec` from a `**Spec:**` line), blocking if not fixed |
| Page still containing a `pmdocs:fill` template marker | warning |
| Item `in-progress` for >30 days with no commit touching its spec/plan or backlog entry | warning (`check` only — it depends on the clock, so it is not in the roadmap or the pre-commit hook) |

References are checked only where they are structured: spec `backlog`, spec
`superseded_by`, plan `spec`, backlog `Spec:`, and `Status: superseded by Dnn` on
decisions. Prose mentions of IDs are not parsed. A plan's `spec` is optional (some plans
have no spec), but must resolve when present.

Plan checkboxes are not read.

## 2. The tool: `scripts/pmdocs.py`

Single file. PEP 723 header: `requires-python = ">=3.11"`, dependencies `markdown-it-py`,
`pyyaml`. Invoked everywhere as `uv run scripts/pmdocs.py <command>`. The file header
states `pmdocs vX.Y.Z — vendored from pm-framework; do not edit, re-run the
project-docs skill to update`.

### Commands

**`build [--check]`**
- Renders every non-generated `docs/**/*.md` (excluding `site/`) to `docs/site/`,
  mirroring paths. Generates `docs/roadmap.md` first so it is rendered too.
- One built-in template: inline CSS with light and dark themes (`prefers-color-scheme`),
  no external assets. A fixed sidebar (amended in 0.2.0, decision D09): Overview,
  Roadmap, Backlog, Product, Architecture, Decisions — project pages nested under a
  category by `parent:` frontmatter, sorted by `order` then `title` — then Specs, Plans,
  extra groups, "Other" and the backlog archive. Per-page "On this page" TOC from H2/H3,
  collapsible (a closed `<details>`, no script).
- `.md` links are rewritten to `.html`. The frontmatter is rendered as a small status
  badge line, not as raw YAML.
- Line endings: inputs are read with CRLF normalized to LF (and a BOM stripped); init
  and adopt add `.gitattributes` lines forcing LF on `docs/site/**/*.html`,
  `docs/roadmap.md`, `scripts/pmdocs.py` and `scripts/hooks/*` — the last because a
  CRLF `#!/bin/sh` line breaks the hook. Binary assets are deliberately not matched.
- Deterministic: sorted traversal, no timestamps, LF endings, UTF-8. Writes only files
  whose content changed and deletes orphaned `.html` files in `site/`. Building twice
  yields no diff.
- The roadmap: an initiatives table (specs with status, linked plans, backlog IDs), the
  open backlog grouped by status, the inbox count, a drift section listing every rule
  hit, and a "What this cannot tell you" note (e.g. a spec that claims more than it
  delivers).
- `--check` writes nothing; it exits 1 if any output would change.

**`check [--staged] [--fix]`**
- Validates: frontmatter parses and status values are in vocabulary; backlog lines parse;
  internal links and anchors resolve; drift rules; doc-map coverage (a tracked source
  file matched by no `[[map]]` glob → warning).
- Staleness: for each changed file matched by a `[[map]]` entry, if none of that entry's
  pages changed in the same change set → warning naming the pages. The change set is
  the working tree vs HEAD plus untracked files, or with `--staged`, the index vs HEAD.
- Reports the inbox count.
- `--fix` applies the auto-fixable rules and says what it changed.
- Output lines are prefixed `ERROR`, `WARN`, `FIXED` or `INFO`. Exit 1 if any `ERROR`,
  else 0.

**`hook pre-commit`** (called by `scripts/hooks/pre-commit`)
1. If `PMDOCS_SKIP=1` or a merge/rebase/cherry-pick is in progress → exit 0.
2. `check --staged --fix`; stage any files `--fix` changed. A fix is skipped for any
   file with unstaged changes or that is untracked, so the hook never stages work the
   user didn't stage.
3. Any `ERROR` → print the errors and the bypass hint, exit **10**. (Not 1: `uv` and
   Python use 1 and 2 for their own failures, which must not block.)
4. Build **from the index**: export staged `docs/` into a temp dir (`git
   checkout-index`), build there, copy `site/` and `roadmap.md` back, then
   `git add docs/site docs/roadmap.md`. This way the commit contains HTML matching
   exactly the Markdown being committed, even with `git commit <paths>`.
5. Print warnings; exit 0.

**`hook post-edit`** (Claude Code PostToolUse, matcher `Edit|Write|MultiEdit`)
Reads the tool-call JSON on stdin, takes `tool_input.file_path`; if it matches a
`[[map]]` entry, emits `hookSpecificOutput.additionalContext`: "`<path>` is documented
in `<pages>`. If this edit changes behavior, update those pages in the same change."
Never fails: any exception → exit 0 with no output.

**`hook stop`** (Claude Code Stop)
Runs the staleness check against the working tree and, if anything is stale or the
inbox is non-empty, emits a `systemMessage` (shown to the user) with both. Stale pages —
and only those — also go to the agent as `hookSpecificOutput.additionalContext`, and not
on a turn a Stop hook already caused (`stop_hook_active`): that context re-invokes the
agent, so a persisting condition would otherwise loop. Never blocks, never fails.

**`install-hooks [--status | --uninstall]`**
- Sets `git config core.hooksPath scripts/hooks`. Refuses, and explains how to chain,
  if `core.hooksPath` is already set to something else or `.git/hooks` contains
  non-sample hooks.
- Merges the two hook entries into `.claude/settings.json` (creating it if absent),
  preserving existing entries and not duplicating ours on re-run.
- Marks `scripts/hooks/*` executable in git (`git update-index --chmod=+x`) so POSIX
  clones get working hooks.
- `--status` reports each piece; `--uninstall` removes exactly what install added.

**`version`** prints the vendored version.

### Git hook script

`scripts/hooks/pre-commit` is POSIX `sh`:

```sh
#!/bin/sh
[ "$PMDOCS_SKIP" = "1" ] && exit 0
if ! command -v uv >/dev/null 2>&1; then
  echo "pmdocs: uv not found; docs not checked (install uv to enable)" >&2
  exit 0
fi
uv run --quiet scripts/pmdocs.py hook pre-commit
status=$?
[ $status -eq 10 ] && exit 1
[ $status -ne 0 ] && echo "pmdocs: tool failed (exit $status); commit allowed" >&2
exit 0
```

Only a genuine doc error (exit 10) blocks. A tool crash, a missing `uv`, or any other
failure lets the commit through with a message.

### Configuration: `docs/pmdocs.toml`

```toml
[site]
title = "my-project"

[paths]
specs = "docs/superpowers/specs"
plans = "docs/superpowers/plans"
exclude = ["docs/course/**"]     # pages outside the convention: not validated, not rendered

[[map]]
paths = ["src/my_project/engine/**"]
pages = ["docs/architecture.md"]

[[map]]
paths = ["scripts/**"]
pages = ["docs/code-layout.md"]

[coverage]
include = ["src/**", "scripts/**"]
exclude = ["scripts/pmdocs.py", "scripts/hooks/**"]
```

Globs use `/` on every OS; the tool normalizes paths before matching.

## 3. The skill and this repo

### Repo layout (`pm-framework`)

```
skill/project-docs/
  SKILL.md                   behaviors + workflows (init, adopt, triage, update)
  references/convention.md   the full convention (section 1), loaded on demand
  references/adopt.md        migration playbook
  assets/
    pmdocs.py                synced copy of tool/pmdocs.py
    hooks/pre-commit
    templates/               index.md, product.md, architecture.md, decisions.md,
                             backlog.md, backlog-archive.md, TODO.md, pmdocs.toml
    claude-md-snippet.md
tool/pmdocs.py               development home of the tool
tests/                       pytest suite
scripts/sync_assets.py       copies tool/pmdocs.py → skill assets (a test checks they match)
install.py                   installs the skill into ~/.claude/skills/project-docs
docs/                        this project follows its own convention
```

`install.py` (run with `uv run install.py`) links `skill/project-docs` to
`~/.claude/skills/project-docs`: a symlink on Linux/macOS, a directory junction on
Windows (no admin rights needed), or a plain copy with `--copy`. It refuses to replace
an existing non-link directory and offers `--uninstall`.

### `SKILL.md` workflows

**init** (new project)
1. Vendor `pmdocs.py` and `hooks/` into `scripts/`.
2. Write the starter pages from templates, filling them from the actual code (not
   placeholders). Draft `pmdocs.toml`'s doc-map from the source tree.
3. Create `TODO.md` if absent.
4. Add the Docs duties snippet to the project's `CLAUDE.md` (creating it if absent).
5. Run `install-hooks`, `build` and `check`; report the results.

**adopt** (existing project)
1. Inventory: existing docs, HTML builders, hooks and their installation, TODO/backlog
   files, decision logs, bold `**Status:**` lines, plan headers.
2. **Propose a mapping table and stop for user approval.** For example: `TODO.md` →
   triaged into `backlog.md`/`backlog-archive.md`; `**Status:**` lines → frontmatter;
   an existing HTML builder → retired.
3. Migrate per the approved table. The existing TODO contents are treated as inbox
   items: the user chooses whether to triage them now or leave them in `TODO.md`.
4. Retire conflicting tooling (old hooks, old builders) only with explicit approval.
5. Run init's vendoring, config, doc-map, CLAUDE.md and install/build/check steps — the
   config (`docs/pmdocs.toml`) must exist before `install-hooks`. Starter pages are
   copied only where no existing page plays that role.

**triage** (pull from the inbox)
1. Read `TODO.md` and list its items.
2. For each item the user picks: ask the clarifying questions that matter (what,
   why, acceptance criteria, priority), one at a time.
3. Draft the backlog item(s) with `Source: TODO.md` and show them.
4. On approval: append to `docs/backlog.md` with the next B-ids and remove the original
   line(s) from `TODO.md`. Nothing is removed from the inbox without approval.
5. Run `check`.

**update**
Compare the project's `pmdocs.py version` with the skill's; if older, re-vendor the
tool and hook, re-run `install-hooks` (idempotent), then run `build` and `check`.

### Behaviors (the CLAUDE.md snippet)

Short, and inserted verbatim:
- Update the pages `docs/pmdocs.toml` maps to your change **in the same commit**.
- New source directory → add it to the doc-map.
- Close work by setting its status; never delete backlog items or decisions.
- Record non-obvious decisions as D-nn in `docs/decisions.md`.
- Verify claims against the code, not against older docs.
- Never hand-edit `docs/site/` or `docs/roadmap.md`.
- `TODO.md` is the user's inbox: append, never rewrite; use the triage workflow to move
  items into the backlog.

## Testing

pytest, with fixtures that build throwaway git repos in `tmp_path`:
- `build` determinism: build twice → no diff; `--check` exits 0, then 1 after an edit.
- Link rewriting, TOC, nav order, orphan deletion.
- Each drift rule and its tier; `--fix` archives closed items; ID allocation.
- Staleness with `--staged` vs the working tree, including untracked files.
- The pre-commit hook: a blocking error exits 1; warnings exit 0; a tool crash lets the
  commit through; `PMDOCS_SKIP`; the build uses the index when index and working tree
  differ.
- `install-hooks`: refuses when hooks exist, settings merge preserves existing entries,
  idempotent, uninstall reverses.
- The post-edit and stop JSON contracts.
- The inbox count on bullet, checkbox and prose inputs.
- `sync_assets` parity: skill asset == `tool/pmdocs.py`.
- Paths: Windows-style separators in inputs are normalized.

End to end: pilot **adopt** on project A on a branch, retiring its own HTML builder.

## Out of scope (v1)

- CI integration.
- Cross-project dashboards.
- Migrating projects B, C and D (later, with adopt).
- A Node runtime.
- Checking agent-facing prose (CLAUDE.md) for staleness beyond the doc-map.
