---
title: Adoption playbook
summary: How to migrate a project that already has docs, TODO files or hooks — the inventory checklist, mapping patterns, and hazards learned in real migrations. The skill loads it for adopt.
---

# Adopting project-docs in an existing project

## Inventory checklist

- [ ] Docs: every `.md` under `docs/` and the root — role (reference, spec, plan, log, lesson, generated).
- [ ] Generated docs: any builder script (`build_docs.py`, `docs_site.py`, `roadmap.py`, …) and its outputs.
- [ ] Git hooks: `git config core.hooksPath`; non-sample files in `.git/hooks`; husky, lefthook, `.pre-commit-config.yaml`.
- [ ] Claude hooks: `.claude/settings.json` and `settings.local.json` — doc reminders, Stop hooks.
- [ ] Is `.claude/` gitignored? (`git check-ignore -q .claude/settings.json` exits 0 if so.)
  If it is, decide with the user whether to share `settings.json` — otherwise clones get
  no Claude hooks. To share it, the ignore rules must be `.claude/*` then
  `!.claude/settings.json`; `.claude/` plus the negation silently does nothing, because
  git cannot re-include a file whose parent directory is excluded. Don't judge from
  `git check-ignore -v`: it prints a matching negation pattern too.
- [ ] Work tracking: `TODO.md`, backlog files, milestone plans, status tables in index pages.
- [ ] Decision logs: numbering scheme and heading format.
- [ ] Spec/plan headers: `**Status:**`, `**Date:**`, `**Spec:**` lines.
- [ ] Markdown outside `docs/` (`git ls-files "*.md"`): README (rendered by default),
  CONTRIBUTING, CHANGELOG, `adr/`, a skill's own files. Decide per folder: a named
  `[[site.extra]]` group in the site, or left out.
- [ ] CLAUDE.md rules about docs — they will be replaced by the snippet; note anything project-specific to keep.

## Mapping patterns

| Existing | Becomes |
|---|---|
| `**Status:** approved 2026-09-24` in a spec | frontmatter `status: approved`, `created: 2026-09-24` |
| `**Status:** BUILT and merged …` | `status: shipped` |
| "Draft — awaiting review" on something that was built | ask; usually `shipped` |
| Bold `**Spec:**` line in a plan | frontmatter `spec:` (docs/-relative) |
| `## B01. Title` + `**Status: DONE, 2026-09-27**` | `Status: done · Added: <first commit date> · Closed: 2026-09-27`, moved to the archive |
| `## D99 — Title (2026-09-29)` | `## D99. Title` (keep the date in the body) |
| TOML `+++` frontmatter | YAML `---` frontmatter, same keys (`title`, `summary`, `order`; drop `updated`) |
| A `doc-map.toml` (globs → pages) | `[[map]]` entries in `docs/pmdocs.toml` |
| Free-form `TODO.md` with Done/archive sections | done entries → archive (if they carry requirements) or dropped; open entries stay in `TODO.md` as inbox |
| Sibling `.html` next to each `.md` | deleted; output moves to `docs/site/` |
| Lesson/course/content pages without frontmatter | `[paths] exclude` |
| A hand-maintained "state of the project" table | delete it; the roadmap replaces it (ask first) |
| A "code layout" / file-map / component page | `parent: architecture` |
| A how-to, install or getting-started page | `parent: overview` |
| A feature, user-guide or capabilities page | `parent: product` |
| An execution ledger or design log with rulings | `parent: decisions` |
| An existing architecture overview / decision log | becomes `architecture.md` / `decisions.md` itself |
| A "waiting on your eye/ear" section, a pending visual or listening check | one gate each (`Status: waiting`); non-user items found there go to the backlog |
| A "needs a decision" item, or options (1)/(2) awaiting a choice | a gate; the options go under Setup |
| A "next test set up" note buried in a data file or notes string | a gate whose Evidence points at that file |
| A verdict restated in a spec status, CLAUDE.md and TODO | recorded once in its gate; the restatements become "see Gnn" |
| A detailed verdict log kept beside the artifact (e.g. a `sources.md` listening log) | stays where it is; the gate links it as Evidence |

Finding an item's `Added` date: `git log --format=%as -S "<a distinctive phrase from the item>" -- docs/backlog.md`,
and take the last line (the oldest commit). If unknown, use the date of the adoption commit and say so in the item.

## Migration hazards (learned in the pilot adoption)

- **Add frontmatter by prepending only.** Never normalise whitespace while migrating:
  collapsing blank lines silently rewrote 328 lines of Python inside a plan's code
  blocks. Afterwards, check `git diff --numstat -- docs`: a page should show only its
  added header lines and any status lines you deliberately removed.
- **Retiring a builder touches more than CLAUDE.md.** Search every page for the old
  builder's name and for `.html` (`code-layout`-style pages and the index's "about these
  docs" section describe it too) and rewrite those passages in the same commit.
- **Dropping a docs-only dependency changes the lockfile.** Removing an extra such as
  `docs = ["markdown"]` updates `uv.lock` the next time `uv run` resolves the project;
  commit that on the adoption branch.
- **Run the project's own test suite and validators afterwards** — they may reference
  the retired builder or the old HTML.
- **Nested code fences**: a ```` ```bash ```` fence inside a ```` ```markdown ```` fence
  closes the outer one (CommonMark), turning example lines into real prose — links in
  them are then genuinely broken. Widen the outer fence to four backticks.
- **Prove the hooks in the real repository**: a mapped source edit should commit with a
  staleness WARN; a page stripped of its frontmatter should be blocked. Undo both.

## Common starting points

- **A Markdown→HTML builder that writes `.html` next to each page, and an existing
  B-nn backlog** (the pilot): retire the builder, its sibling `.html` files and any
  docs-only dependency; exclude non-reference content (lessons, notes) via
  `[paths] exclude`; convert bold status lines; turn unnumbered "also open" bullets into
  numbered items; keep decision numbers. Expect `check` to be clean on the first run.
- **Its own doc-map, docs builder and Claude reminder hooks**: fold the doc-map into
  `[[map]]` entries, convert TOML (`+++`) frontmatter to YAML, and replace the reminder
  hooks with pmdocs' (check both `settings.json` and any copy outside the repo). If
  `core.hooksPath` points elsewhere, chain pmdocs from that pre-commit (exit 10 blocks).
  Decide with the user whether an existing docs test gate stays.
- **`core.hooksPath` already set to `scripts/hooks`**, with its own `pre-commit` (and
  perhaps `post-merge`): the same path pmdocs vendors to. Replacing its pre-commit
  retires whatever it ran (e.g. a roadmap generator); decide about other hooks with the user.
- **No tooling, a very large `TODO.md` and a long decision log**: leave most of `TODO.md`
  as inbox for triage; convert decision headings such as `## D99 — Title (date)` to
  `## D99. Title`; fold a milestone plan into `product.md`.
