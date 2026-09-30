---
title: Product
summary: What project-docs gives a project, and what it deliberately does not do.
order: 10
---

# Product

## Purpose

Agent-built projects drift: docs fall behind the code, and the status of planned work is
scattered across TODO files, spec status lines and plan checkboxes that nothing
reconciles. project-docs gives any project one place for each kind of fact and checks them
mechanically, so drift is caught while the agent is still editing and again at commit.

## Capabilities

- **Convention**: `docs/` with product, architecture, decisions, backlog (+ archive),
  generated roadmap and HTML site; YAML frontmatter status on specs and plans; `TODO.md`
  as the user's free-form inbox. Only the backlog, archive, decisions, roadmap and index
  have fixed names — a project keeps its own pages — and `[site] nav` sets the sidebar
  order. `[site] extra` renders Markdown that must live elsewhere (a skill's own files,
  a README) into the same site.
- **Skill workflows**: init (new project), adopt (migrate existing docs, with an approved
  mapping), triage (inbox → backlog with the user), update (re-vendor the tool and
  refresh the project's CLAUDE.md duties).
- **Capturing discovered work**: when a question, feedback or a finding reveals work
  outside the current task, the agent offers to note it in `TODO.md` or draft a backlog
  item, rather than letting it scroll away.
- **Tool** (`scripts/pmdocs.py`): build the site and roadmap, check frontmatter, links,
  drift and staleness, apply mechanical fixes, install hooks.
- **Enforcement**: pre-commit blocks only on doc errors and builds the site from the
  index; Claude Code hooks name the pages covering each edited file and list stale pages
  at the end of a turn.
- **Cross-platform**: Linux, macOS and Windows; POSIX `sh` hook; Python via `uv`.

## Non-goals

- CI integration, cross-project dashboards, a Node runtime.
- Judging whether prose is accurate — the tool only knows whether a page changed
  alongside the code it covers.
- Reading plan checkboxes as progress.
- Editing the user's `TODO.md` other than through approved triage.
