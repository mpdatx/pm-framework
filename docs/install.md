---
title: Install
summary: Install the project-docs skill, use it in a project, keep projects current, and uninstall.
order: 2
---

# Install

## Requirements

- [Claude Code](https://claude.com/claude-code).
- `git`.
- [`uv`](https://docs.astral.sh/uv/). It runs the tool with the right Python and its two
  dependencies (`markdown-it-py`, `pyyaml`), so no virtualenv or `pip install` is needed.
- Linux, macOS or Windows. On Windows the git hook runs under the `sh` that ships with
  Git for Windows.

## Install the skill

```sh
git clone <this repository> pm-framework
cd pm-framework
uv run install.py
```

This links `skill/project-docs/` into `~/.claude/skills/project-docs`. The link is a
symlink, or a directory junction on Windows without symlink privilege.

Options:

| Command | Effect |
|---|---|
| `uv run install.py --copy` | Copy instead of linking; re-run after pulling a new version. |
| `uv run install.py --dest PATH` | Install somewhere other than `~/.claude/skills/project-docs`. |
| `uv run install.py --uninstall` | Remove what the installer created (it refuses to delete anything else). |

Start a new Claude Code session afterwards. `project-docs` should appear in its list of
available skills.

## Use it in a project

In the project's directory, ask Claude Code in plain words. The skill picks the workflow:

| You say | Workflow |
|---|---|
| "Set up project-docs here" (new or undocumented project) | **init**: starter pages, doc-map, vendored tool, hooks |
| "Adopt project-docs" (a project with existing docs) | **adopt**: proposes a mapping of your existing docs and waits for your approval |
| "Triage TODO.md" | **triage**: turns your inbox notes into backlog items with you |
| "Update project-docs" | **update**: re-vendors a newer tool and refreshes the CLAUDE.md duties |

Adopting a project adds:

- `docs/pmdocs.toml` (config and doc-map), `docs/backlog.md`, `docs/decisions.md` and a
  generated `docs/roadmap.md` and `docs/site/`;
- `scripts/pmdocs.py` and `scripts/hooks/pre-commit` (vendored; git's `core.hooksPath`
  points at `scripts/hooks`);
- two Claude Code hooks in `.claude/settings.json`;
- a short "Docs duties" section in the project's `CLAUDE.md`.

If `.claude/` is gitignored in that project, `install-hooks` warns you: the Claude hooks
then won't reach other clones unless `settings.json` is re-included (see the adopt
reference).

## Keep projects current

Each adopted project carries its own copy of the tool, so pulling a new version of this
repository changes nothing in them until you run **update** there. It compares the
project's `VERSION` with the installed skill's and re-vendors if the skill is newer.

## For maintainers

In a clone where releases are cut (one with a `release` branch or `v*` tags), the
installed skill links `.release/`, a worktree of the `release` branch, rather than your
working tree. Unreleased work never reaches other projects.

```sh
uv run pytest                   # the suite
uv run scripts/sync_assets.py   # after changing tool/
uv run scripts/release.py       # bump VERSION in tool/pmdocs.py first; tags and publishes
uv run install.py --dev         # try unreleased skill changes; re-run without --dev after
```

[Architecture](architecture.md#releases) covers the release mechanics.
