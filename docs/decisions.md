---
title: Decisions
summary: Why project-docs is the way it is. Records are never rewritten; superseded ones are marked.
order: 30
---

# Decisions

## D01. Vendor the tool into each project

**Context.** The tool must run in every clone, worktree and machine of an adopting project.
**Decision.** The skill copies a versioned single file into `scripts/pmdocs.py`.
**Why.** Projects stay self-contained; a central path couples every project to this
machine; an installed CLI needs an install step on every clone.
**Consequences.** Updating means re-running the skill's update workflow.

## D02. Status in frontmatter plus a generated roadmap

**Context.** The surveyed projects kept status in 3–5 places that drifted apart.
**Decision.** Specs and plans carry `status:` frontmatter; a backlog holds B-nn items; the
roadmap is generated from both and lists drift.
**Why.** One mechanically checked source per fact.
**Consequences.** Specs written by other skills need frontmatter; the hook adds a draft header.

## D03. Tiered enforcement

**Context.** Every surveyed project was warn-only and still drifted; blocking on judgment
calls adds friction to every refactor.
**Decision.** Mechanical problems block or are auto-fixed; staleness warns.
**Why.** Mechanical errors have exactly one right fix; staleness needs judgment.
**Consequences.** The agent must act on warnings — the skill's red flags say so.

## D04. Exit code 10 means "block"

**Context.** `uv` and Python exit 1 or 2 on their own failures.
**Decision.** Only exit 10 from the tool blocks a commit.
**Why.** A broken tool must never stop someone from committing.
**Consequences.** Hooks written by hand to chain pmdocs must test for 10.

## D05. Build from the index

**Context.** A surveyed project rebuilt from the working tree, so partial commits carried
HTML for Markdown that wasn't committed.
**Decision.** The pre-commit hook exports the index to a temp dir and builds there.
**Why.** The commit's HTML matches exactly the Markdown in the commit.
**Consequences.** Links out of `docs/` are resolved against the working tree.

## D06. TODO.md is the user's inbox

**Context.** Users jot ideas ad hoc; in a surveyed project, agents rewriting that file lost notes.
**Decision.** `TODO.md` is free-form and user-owned; items move to the backlog only
through triage with approval.
**Why.** Capture must stay frictionless; the backlog must stay specified.
**Consequences.** The tool only counts inbox items and never blocks on them.

## D07. The tool exempts its own vendored files

**Context.** In the pilot project a broad map (`scripts/** -> code-layout.md`) matched
the vendored `scripts/pmdocs.py`, so every `update` commit warned that docs were stale (B07).
**Decision.** Staleness and coverage skip `scripts/pmdocs.py` and
`scripts/hooks/pre-commit`, built into the tool rather than configured per project.
**Why.** The fix then reaches every adopted project with the next update, and no project
has to remember an exclusion; those files are documented by pm-framework, not by the
project that vendors them.
**Consequences.** A project that deliberately edits its vendored copy gets no staleness
warning for it — but the header already says not to edit it.

## D08. Other projects consume releases, not the working tree

**Context.** The installed skill linked this repository's working tree, so unsaved edits
to `SKILL.md` and unreleased `pmdocs.py` copies were live in every session and could be
vendored mid-change; `VERSION` was bumped as work happened (B08).
**Decision.** A `release` branch checked out as a gitignored worktree at `.release/`;
`scripts/release.py` tags `v<VERSION>` from a clean, tested, synced `master` and
fast-forwards it. `install.py` links the release by default; `--dev` is an explicit
opt-in.
**Why.** A worktree inside the repo adds no second project-like directory beside it; a
branch plus tags gives a history of exactly what was shipped; nothing in the skill's
workflows had to change, because they already read from the installed directory.
**Consequences.** Changes reach other projects only after `release.py`. Testing a skill
change in another project before release needs `install.py --dev` (and a later re-install).

## D09. A fixed sidebar; project pages attach with `parent:`

**Context.** `[site] nav` let each project order its sidebar freely, and adopted
projects' own pages could push the backlog and roadmap far down the list — the opposite
of what the convention is for.
**Decision.** The sidebar is fixed: Overview, Roadmap, Backlog, Product, Architecture,
Decisions, then Specs, Plans, extra groups, "Other" and the archive. A project's pages
nest under a category via `parent:` frontmatter; a page without one warns and goes
under "Other". `[site] nav` is removed (an ERROR since 0.2.0).
**Why.** Work status must be in the same, prominent place in every project; a
project's own documentation still fits, as sub-pages of the categories it belongs to.
Frontmatter rather than folders, so adoption moves no files and breaks no links.
**Consequences.** Projects can order pages only among siblings (`order`). Updating to
0.2.0 means deleting `nav` and giving each project page a parent.

## D10. Gates: work waiting on the user is recorded once, by ID

**Context.** In two surveyed projects, work waiting on the user's eye or ear had no
home: the most important pending listening test existed only inside a JSON notes
string; a "waiting on your eye" list mixed user questions with engineering items; a
single verdict was restated in five places, three of which contradicted it; nothing
told a new session what the user still had to answer, and questions sat for up to two
weeks.
**Decision.** A gate (`## Gnn.` in `docs/gates.md`) records one question only the user
can answer — status, date asked, preconditions, setup, pass condition, evidence — and
its dated, verbatim verdicts. Answered gates are archived. Specs and backlog items
reference gates by ID; drift checks catch a spec shipped while its gate waits and work
still blocked on an answered gate. The roadmap leads with "Waiting on you", a
SessionStart hook briefs each new session, and the Stop note counts open gates for the user.
**Why.** One record per question removes the multi-place drift; a named state makes
"waiting on the user" visible instead of implied; recording the verdict at once, in the
user's words, stops it living only in chat.
**Consequences.** Agents must open a gate before handing something to the user and
record verdicts immediately. Adopting or updating to 0.3.0 means mapping existing
waiting items and verdict logs to gates.

## D11. Doc roots: any folder with docs/pmdocs.toml; nested ones own their subtree

**Context.** Placed in a subfolder of a larger repository, project-docs failed silently
(B09): git reports repo-top paths, so staleness never matched; git resolves
`core.hooksPath` from the repo top, so the hook was never run; Claude hook commands
assumed Claude was launched in the project folder.
**Decision.** A doc root is any folder with `docs/pmdocs.toml`, and every path a doc root
owns is relative to it and may not leave it. Nested doc roots own their subtree. A
vendored tool finds its doc root from its own location. The git hook is a dispatcher
serving every doc root in the repository, and Claude hooks find their tool through git.
Inbox, backlog and gates are per doc root. See the doc-roots spec.
**Why.** Monorepos and umbrella-plus-package layouts are common, and a convention that
silently stops checking is worse than none. Confining paths to the doc root keeps each
project self-contained and makes "which docs are stale" unambiguous.
**Consequences.** A shared library is documented by the doc root that contains it, not
by its users. A repository-wide view across doc roots is out of scope for now. A doc root
at the repo top behaves exactly as before.
