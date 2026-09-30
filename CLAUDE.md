# pm-framework

The project-docs convention, its tool and its skill. The tool is one file,
`tool/pmdocs.py`; it is vendored into other projects, so it stays a single file with
only `markdown-it-py` and `pyyaml` as dependencies.

## Things that look wrong but aren't

- `scripts/pmdocs.py`, `scripts/hooks/pre-commit` and `skill/project-docs/assets/pmdocs.py`
  are **copies** of `tool/`. Edit `tool/`, then run `uv run scripts/sync_assets.py`; a
  test fails if they differ.
- The tool exits **10** to block a commit, not 1 — see decision D04.
- `tool/hooks/pre-commit` must stay LF; `.gitattributes` enforces it.
- One big file is deliberate (vendoring); it is split into `# === section ===` blocks.
- `.release/` is a git worktree of the `release` branch, not stray files — the installed
  skill links it (D08). Never edit it; ship with `uv run scripts/release.py`. Bump
  `VERSION` once per release, not per change: other projects' **update** compares it.
- Grep/Glob will find a second copy of everything under `.release/`; edit the one at the
  repo root.

## Run and test

    uv run pytest
    uv run scripts/pmdocs.py check
    uv run scripts/pmdocs.py build

## Docs duties (project-docs)

- `docs/` is the reference documentation; `docs/pmdocs.toml` maps source paths to the
  pages that describe them. Update the mapped pages **in the same commit** as the code.
- New source directory → add a `[[map]]` entry for it. New page under `docs/` → give
  it `parent:` (overview, product, architecture or decisions) so it nests in the sidebar.
- Work status lives in frontmatter (`status:` on specs and plans) and in
  `docs/backlog.md` (`## Bnn. Title` + `Status: … · Added: …`). Close work by setting
  its status — never delete backlog items or decisions.
- Record non-obvious decisions as `## Dnn.` in `docs/decisions.md`.
- Anything only the user can settle (a look, a listen, an approval, a decision) is a
  gate in `docs/gates.md` (`## Gnn.`, `Status: waiting`). Open the gate before handing
  it over; when the user answers, record their words in it at once, verbatim and dated;
  everywhere else refer to it by ID instead of restating the verdict.
- Verify claims against the code, not against older docs.
- Never hand-edit `docs/site/` or `docs/roadmap.md` — `uv run scripts/pmdocs.py build`.
- `TODO.md` is the user's inbox: append, never rewrite. Move items into the backlog
  with the project-docs triage workflow, and only with the user's approval.
- Capture work you discover: when a question, feedback or finding reveals work outside
  the current task, offer to capture it — a one-line `TODO.md` note by default, or a
  drafted backlog item when the what and why are clear. Never drop it silently.
- Run `uv run scripts/pmdocs.py check` before finishing. The pre-commit hook blocks on
  doc errors; bypass once with `PMDOCS_SKIP=1` only when the user says so.
