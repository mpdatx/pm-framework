---
title: Backlog
summary: Open work. Closed items move to the archive.
order: 90
---

# Backlog

## B09. Doc roots: project-docs in subfolders and monorepos
Status: open · Spec: superpowers/specs/2026-10-02-doc-roots-design.md · Added: 2026-10-02

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
