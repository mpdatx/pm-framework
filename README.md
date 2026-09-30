# pm-framework

**project-docs** — a convention, a tool and a Claude Code skill for keeping a project's
architecture docs, product docs and work status current.

- Markdown in `docs/` is the source; HTML (`docs/site/`) and `docs/roadmap.md` are generated.
- A pre-commit hook blocks on doc errors and warns when code changes without its docs.
- Claude Code hooks name the pages covering each file you edit.
- `TODO.md` is your inbox; the skill triages it into a backlog with you.

## Install the skill

Needs `git`, [`uv`](https://docs.astral.sh/uv/) and Claude Code.

    git clone <this repository> pm-framework
    cd pm-framework
    uv run install.py          # links the skill into ~/.claude/skills/project-docs

Then, in any project, ask Claude to set up project-docs (init), migrate existing docs
(adopt), or triage `TODO.md`. Full instructions — options, what adoption adds, keeping
projects current, uninstalling — are in [docs/install.md](docs/install.md).

## Develop

    uv run pytest
    uv run scripts/sync_assets.py   # after changing tool/
    uv run scripts/release.py       # ship: bump VERSION in tool/pmdocs.py first
    uv run install.py --dev         # try unreleased skill changes (re-run without --dev after)

In a maintainer's clone the installer links the released skill (`.release/`), never the
working tree; see [docs/architecture.md](docs/architecture.md#releases).

Docs: [docs/index.md](docs/index.md) (rendered: `docs/site/index.html`).

## License

[MIT](LICENSE). The vendored `scripts/pmdocs.py` and `scripts/hooks/pre-commit` that the
skill copies into a project carry the same licence line in their headers.
