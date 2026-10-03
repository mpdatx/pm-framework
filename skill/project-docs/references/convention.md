---
title: Convention reference
summary: The full convention — file layout, frontmatter, backlog and decision formats, every check and its tier, and the tool's commands. The skill loads it before init and adopt.
---

# The project-docs convention

## Layout

The layout lives at a **doc root** — the repository top, or a subfolder for one project
inside a larger repository (see [Doc roots](#doc-roots)). All paths below are relative
to it.

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
  gates.md               questions waiting on the user, ## Gnn. records with verdicts
  gates-archive.md       answered / dropped gates (moved, never deleted)
  roadmap.md             GENERATED
  superpowers/specs/     specs
  superpowers/plans/     plans
  site/                  GENERATED HTML, committed
scripts/pmdocs.py        vendored tool
scripts/hooks/pre-commit vendored git hook (core.hooksPath = scripts/hooks)
.claude/settings.json    PostToolUse, Stop and SessionStart hooks (merged by install-hooks)
```

## Doc roots

A doc root is any folder containing `docs/pmdocs.toml`. A repository may hold several:
one at the top, one per package, or both.

- **Everything is relative to the doc root.** Doc-map paths and pages, `[coverage]`,
  `[[site.extra]]`, `TODO.md`, the README, the site, the backlog and the gates. A
  configured path that leaves the doc root (`../…`) is an ERROR; shared code is
  documented by the doc root that contains it.
- **Nested doc roots own their subtree.** A doc root inside another — `packages/a/`
  under a top-level umbrella — takes its files out of the outer one's pages, coverage
  and staleness. Nothing needs excluding by hand.
- **One git hook serves the whole repository.** The vendored `scripts/hooks/pre-commit`
  is a dispatcher: it runs every doc root's own tool for the doc roots a commit
  touches, and blocks if any reports an error. `core.hooksPath` points at whichever doc
  root installed first; the others reuse it (`install-hooks --status` lists the doc
  roots it covers).
- **Claude Code hooks live in the repository top's `.claude/settings.json`**, one set
  per doc root. Each finds its tool through git
  (`"$(git rev-parse --show-toplevel)/<doc root>/scripts/pmdocs.py"`) and answers only
  for its own project; with several doc roots, their notes carry the project's
  `[site] title`.
- **Inbox, backlog, gates and roadmap are per doc root.**

## Frontmatter (YAML, between `---` lines)

Every page under `docs/` except generated files and `[paths] exclude` globs needs a
`title`. Optional on any page: `summary` (shown under the title), `order` (position among
its siblings, default 50).

Specs add `status` (`draft | approved | in-progress | shipped | superseded | abandoned`),
`created`, `backlog` (list of B-ids), `gates` (list of G-ids the spec's acceptance waits
on) and, when superseded, `superseded_by` (a docs/-relative path). Plans add `status`
(`draft | approved | in-progress | shipped | abandoned`) and optionally `spec` (a
docs/-relative path). There is no `updated` field — git history is the authority.

## The sidebar (fixed)

Every adopted project has the same sidebar, so work status is always in the same,
prominent place. Projects cannot reorder it:

```
Overview        index.md          ↳ pages with parent: overview
Waiting on you  gates.md
Roadmap         roadmap.md        (generated; leads with what is waiting on you)
Backlog         backlog.md
Product         product.md        ↳ pages with parent: product
Architecture    architecture.md   ↳ pages with parent: architecture
Decisions       decisions.md      ↳ pages with parent: decisions
Specs · Plans   newest first
extra groups    README ("Repository") and [[site.extra]] groups, in config order
Other           project pages with no usable parent (each a WARN)
Backlog archive, Gates archive    last, below a divider
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

## Backlog items

```
## B07. Title
Status: in-progress · Spec: superpowers/specs/2026-09-29-x-design.md · Added: 2026-09-20 · Source: TODO.md

Free prose: what and why, acceptance criteria, open questions.
```

- `Status` (`open | in-progress | blocked | done | dropped`) and `Added` are required.
- `Spec`, `Source`, `Gate` and `Closed` are optional. Separator ` · ` (`|` also accepted).
- IDs are never reused; the next is max(backlog ∪ archive) + 1. `B7` and `B07` are the same item.
- Work that can't proceed until the user answers a gate: `Status: blocked · Gate: G04`.

## Gates

A gate is a question only the user can answer — an in-person look, a listening pass,
an A/B choice, an approval, a decision. It is recorded **once**, in `docs/gates.md`;
specs (`gates: [G04]`), backlog items (`Gate: G04`), CLAUDE.md and commit messages refer
to it by ID instead of restating the verdict.

```
## G04. The question, as the user will read it
Status: waiting · Asked: 2026-09-28 · For: B03 · Needs: Live running, playback healthy

Setup: exactly what to look at or run.
Passes if: what a "yes" looks like.
Evidence: paths to the build, render, demo or log.

### Verdicts

- 2026-09-29 — "the user's words, verbatim" — pass. Checked: playback healthy.
```

- `Status` (`waiting | answered | dropped`) and `Asked` are required; `For` (B- or
  G-ids) and `Needs` (preconditions) are optional.
- A verdict is a dated line under the gate, quoting the user; record it the moment it is
  given. Answered gates need at least one. To retract, add a new dated line saying what
  is withdrawn and set the gate back to `waiting` (move it back from the archive).
- Answered and dropped gates move to `docs/gates-archive.md` (the hook does it).
- The roadmap leads with "Waiting on you"; each Claude session starts with a note listing
  open gates and in-flight work; the end-of-turn note tells the user how many gates wait.

## Decisions

`## Dnn. Title`, then **Context / Decision / Why / Consequences**. A reversed decision
gets `Status: superseded by Dmm` directly under its heading; its text is not rewritten.

## Inbox

`TODO.md` at the root belongs to the user. Any format. Agents append, never rewrite.
Items leave only through triage, with approval. The tool only counts items: top-level
list items, or — in a file with no list — the paragraphs after its first section
heading (the first heading after the `# TODO` title). Text above or directly under the
title, `---` rules, comments and code blocks never count, so a `TODO.md` of a title, a
description and empty sections is empty. A file with no headings counts every paragraph.

## Checks and tiers

| Finding | Tier |
|---|---|
| Missing/invalid frontmatter or title; status outside vocabulary | ERROR (blocks commit) |
| Broken link or anchor; missing B-id, D-id, G-id, spec or plan reference; duplicate ID | ERROR |
| Open item or waiting gate in an archive; `[[map]]` page missing | ERROR |
| Spec/plan without frontmatter | FIXED by the hook (draft header), else ERROR |
| Done/dropped item still in the backlog; answered/dropped gate still in `gates.md` | FIXED by the hook (moved to the archive) |
| Answered gate with no dated verdict | WARN |
| Spec shipped while one of its gates is waiting; item blocked on an answered gate | WARN |
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
| `hook post-edit` / `hook stop` / `hook session-start` | Claude Code hooks; never block. |
| `install-hooks [--status\|--uninstall]` | `core.hooksPath` + `.claude/settings.json`. |
| `version` | Vendored version. |

Bypass the git hook once with `PMDOCS_SKIP=1 git commit …` or `git commit --no-verify`.

After `git commit <paths>` (or `-o`), the commit itself is right — its HTML matches the
Markdown it contains — but git keeps the real index locked during such a commit, so the
hook cannot stage the rebuilt site there. `git status` then shows `docs/site/` as
modified. Run `git add docs/site docs/roadmap.md` (or just make the next commit normally)
before any `--no-verify` commit, or that commit would carry the older site.
