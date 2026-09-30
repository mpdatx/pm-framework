---
title: Convention reference
summary: The full convention — file layout, frontmatter, backlog and decision formats, every check and its tier, and the tool's commands. The skill loads it before init and adopt.
---

# The project-docs convention

## Layout

```
TODO.md                  inbox — user-owned, free-form
docs/
  pmdocs.toml            config and doc-map
  index.md               overview + "what to read when"
  product.md             purpose, capabilities, non-goals
  architecture.md        components and code pointers (may grow into architecture/*.md)
  decisions.md           ## Dnn. records
  backlog.md             open work, ## Bnn. items
  backlog-archive.md     closed items (moved, never deleted)
  roadmap.md             GENERATED
  superpowers/specs/     specs
  superpowers/plans/     plans
  site/                  GENERATED HTML, committed
scripts/pmdocs.py        vendored tool
scripts/hooks/pre-commit vendored git hook (core.hooksPath = scripts/hooks)
.claude/settings.json    PostToolUse + Stop hooks (merged by install-hooks)
```

## Frontmatter (YAML, between `---` lines)

Every page under `docs/` except generated files and `[paths] exclude` globs needs a
`title`. Optional on any page: `summary` (shown under the title), `order` (position among
its siblings, default 50).

## The sidebar (fixed)

Every adopted project has the same sidebar, so work status is always in the same,
prominent place. Projects cannot reorder it:

```
Overview        index.md          ↳ pages with parent: overview
Roadmap         roadmap.md        (generated)
Backlog         backlog.md
Product         product.md        ↳ pages with parent: product
Architecture    architecture.md   ↳ pages with parent: architecture
Decisions       decisions.md      ↳ pages with parent: decisions
Specs · Plans   newest first
extra groups    README ("Repository") and [[site.extra]] groups, in config order
Other           project pages with no usable parent (each a WARN)
Backlog archive last, below a divider
```

A project's own page attaches with `parent:` in its frontmatter — one of `overview`,
`product`, `architecture`, `decisions` — and is listed, indented, under that category,
sorted by `order` then title. Files stay where they are, in any folder under `docs/`. A
page without a `parent:` is a WARN and appears under "Other"; an unknown parent is an
ERROR; a parent whose category page doesn't exist is a WARN (and the page goes under
"Other"). Category pages that don't exist are simply absent. (`[site] nav`, which let
projects reorder the sidebar, was removed in 0.2.0 and is now an ERROR.)

Markdown that must live outside `docs/` (a skill's own files, a README, an ADR folder)
can join the site with `[site] extra`. Give each set a group name and a sentence saying
what it is:

```toml
[[site.extra]]
group = "Decision records"
about = "Architecture decision records, kept beside the code in adr/."
paths = ["adr/*.md"]
```

(A plain list of globs, `extra = ["CHANGELOG.md"]`, is one untitled "Reference" group.)

By convention the root `README.md` is rendered without any configuration, as a
"Repository" group. `readme = false` under `[site]` turns that off; listing `README.md`
in a `[[site.extra]]` group of your own replaces the default name and text.
Pages render under `docs/site/extra/<path>.html`, in the listed order. Each shows its
group's `about` text and a "Source:" line naming the file, so a reader knows where it
lives. They need no frontmatter — the title falls back to `name`, then the first H1 —
and their links are checked like any page's.

## Doc-map

`[[map]]` entries in `pmdocs.toml` pair source globs (`paths`) with the pages that
describe them (`pages`). Every path is relative to the repository root, and a page may
live outside `docs/` — a `LICENSE.md`, `CONTRIBUTING.md` or provenance table is often the
page that must change with a source directory. Such pages are checked for staleness but
not rendered into the site.

Specs add `status` (`draft | approved | in-progress | shipped | superseded | abandoned`),
`created`, `backlog` (list of B-ids) and, when superseded, `superseded_by` (a
docs/-relative path). Plans add `status` (`draft | approved | in-progress | shipped |
abandoned`) and optionally `spec` (a docs/-relative path). There is no `updated`
field — git history is the authority.

## Backlog items

```
## B07. Title
Status: in-progress · Spec: superpowers/specs/2026-09-29-x-design.md · Added: 2026-09-20 · Source: TODO.md

Free prose: what and why, acceptance criteria, open questions.
```

- `Status` (`open | in-progress | blocked | done | dropped`) and `Added` are required.
- `Spec`, `Source` and `Closed` are optional. Separator ` · ` (`|` also accepted).
- IDs are never reused; the next is max(backlog ∪ archive) + 1. `B7` and `B07` are the same item.

## Decisions

`## Dnn. Title`, then **Context / Decision / Why / Consequences**. A reversed decision
gets `Status: superseded by Dmm` directly under its heading; its text is not rewritten.

## Inbox

`TODO.md` at the root belongs to the user. Any format. Agents append, never rewrite.
Items leave only through triage, with approval. The tool only counts items.

## Checks and tiers

| Finding | Tier |
|---|---|
| Missing/invalid frontmatter or title; status outside vocabulary | ERROR (blocks commit) |
| Broken link or anchor; missing B-id, D-id, spec or plan reference; duplicate ID | ERROR |
| Open item in the archive; `[[map]]` page missing | ERROR |
| Spec/plan without frontmatter | FIXED by the hook (draft header), else ERROR |
| Done/dropped item still in the backlog | FIXED by the hook (moved to archive) |
| Code changed but none of its mapped pages did | WARN |
| Tracked source file not covered by any `[[map]]` | WARN |
| Spec draft while its plan moved; plan shipped but spec not; spec shipped but backlog item open | WARN |
| `pmdocs:fill` marker left in a page | WARN |
| Item in-progress >30 days without a touching commit | WARN (`check` only) |

Plan checkboxes are never read. The vendored `scripts/pmdocs.py` and
`scripts/hooks/pre-commit` are exempt from staleness and coverage: they change on every
update and are documented by pm-framework, so no `[[map]]` needs to exclude them.

## Tool

| Command | Purpose |
|---|---|
| `build [--check]` | Roadmap + site. `--check` exits 1 if stale, writes nothing. |
| `check [--staged] [--fix]` | All checks. Exit 1 on any ERROR. `--fix` applies FIXED-tier fixes. |
| `hook pre-commit` | Fix → check index → block (exit 10) or build from the index and stage the site. |
| `hook post-edit` / `hook stop` | Claude Code hooks; never block. |
| `install-hooks [--status\|--uninstall]` | `core.hooksPath` + `.claude/settings.json`. |
| `version` | Vendored version. |

Bypass the git hook once with `PMDOCS_SKIP=1 git commit …` or `git commit --no-verify`.

After `git commit <paths>` (or `-o`), the commit itself is right — its HTML matches the
Markdown it contains — but git keeps the real index locked during such a commit, so the
hook cannot stage the rebuilt site there. `git status` then shows `docs/site/` as
modified. Run `git add docs/site docs/roadmap.md` (or just make the next commit normally)
before any `--no-verify` commit, or that commit would carry the older site.
