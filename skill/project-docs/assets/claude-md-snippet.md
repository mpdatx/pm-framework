## Docs duties (project-docs)

- `docs/` is the reference documentation; `docs/pmdocs.toml` maps source paths to the
  pages that describe them. Update the mapped pages **in the same commit** as the code.
- New source directory → add a `[[map]]` entry for it. New page under `docs/` → give
  it `parent:` (overview, product, architecture or decisions) so it nests in the sidebar.
- Work status lives in frontmatter (`status:` on specs and plans) and in
  `docs/backlog.md` (`## Bnn. Title` + `Status: … · Added: …`). Close work by setting
  its status — never delete backlog items or decisions.
- Record non-obvious decisions as `## Dnn.` in `docs/decisions.md`.
- Verify claims against the code, not against older docs.
- Never hand-edit `docs/site/` or `docs/roadmap.md` — `uv run scripts/pmdocs.py build`.
- `TODO.md` is the user's inbox: append, never rewrite. Move items into the backlog
  with the project-docs triage workflow, and only with the user's approval.
- Capture work you discover: when a question, feedback or finding reveals work outside
  the current task, offer to capture it — a one-line `TODO.md` note by default, or a
  drafted backlog item when the what and why are clear. Never drop it silently.
- Run `uv run scripts/pmdocs.py check` before finishing. The pre-commit hook blocks on
  doc errors; bypass once with `PMDOCS_SKIP=1` only when the user says so.
