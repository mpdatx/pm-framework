# pm-framework

**project-docs** — a convention, a tool and a Claude Code skill for keeping a project's
architecture docs, product docs and work status current.

- Markdown in `docs/` is the source; HTML (`docs/site/`) and `docs/roadmap.md` are generated.
- A pre-commit hook blocks on doc errors and warns when code changes without its docs.
- Claude Code hooks name the pages covering each file you edit.
- `TODO.md` is your inbox; the skill triages it into a backlog with you.

## Install the skill

    uv run scripts/release.py  # first time only, if .release/ doesn't exist yet
    uv run install.py          # links the released skill into ~/.claude/skills/
    uv run install.py --copy   # or copy it

Then, in any project, ask Claude to set up project-docs (init), migrate existing docs
(adopt), or triage `TODO.md`.

## Develop

    uv run pytest
    uv run scripts/sync_assets.py   # after changing tool/
    uv run scripts/release.py       # ship: bump VERSION in tool/pmdocs.py first
    uv run install.py --dev         # try unreleased skill changes (re-run without --dev after)

Docs: [docs/index.md](docs/index.md) (rendered: `docs/site/index.html`).
