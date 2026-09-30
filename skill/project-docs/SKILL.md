---
name: project-docs
description: Use when setting up or migrating a project's documentation and work tracking (architecture and product docs, backlog, decisions, roadmap, generated HTML, git-hook freshness checks), when the user asks to triage TODO.md into the backlog, or when working in a project that has docs/pmdocs.toml and its docs or work status need updating.
---

# project-docs

Keeps a project's architecture docs, product docs and work status current. Markdown in
`docs/` is the source of truth. A vendored tool, `scripts/pmdocs.py`, generates the HTML
site (`docs/site/`) and `docs/roadmap.md`, validates everything, and runs from a git
pre-commit hook (blocks on doc errors, warns on staleness) and from Claude Code hooks
(flags stale pages while you work).

`SKILL_DIR` is the directory containing this file. Run the tool from the project root:
`uv run scripts/pmdocs.py <build|check|install-hooks|version>`. Before **init** or
**adopt**, read `SKILL_DIR/references/convention.md`.

## Which workflow

| Situation | Workflow |
|---|---|
| No `docs/pmdocs.toml`; little or no existing documentation | **init** |
| No `docs/pmdocs.toml`; existing docs, TODO/backlog files, decision logs or doc hooks | **adopt** |
| User asks to triage, process or groom `TODO.md` | **triage** |
| `VERSION` in `scripts/pmdocs.py` is older than in `SKILL_DIR/assets/pmdocs.py` | **update** |
| Ordinary work in a project that has `docs/pmdocs.toml` | **Everyday duties** |

## init

1. Check `git rev-parse --show-toplevel` is the project root and `uv --version` works.
   If uv is missing, stop and tell the user (https://docs.astral.sh/uv/).
2. Vendor the tool — copy the bytes exactly, they must stay LF:
   - `SKILL_DIR/assets/pmdocs.py` → `scripts/pmdocs.py`
   - `SKILL_DIR/assets/hooks/pre-commit` → `scripts/hooks/pre-commit`
3. Add the lines of `SKILL_DIR/assets/gitattributes` to `.gitattributes` (create it if
   absent; skip lines already present).
4. Copy templates from `SKILL_DIR/assets/templates/`: `index.md`, `product.md`,
   `architecture.md`, `decisions.md`, `backlog.md`, `backlog-archive.md`, `gates.md`,
   `gates-archive.md` → `docs/`;
   `pmdocs.toml` → `docs/` with `PROJECT` replaced by the directory name; `TODO.md` → the
   project root, only if absent.
5. Fill every `pmdocs:fill` marker from the actual code — read it; don't invent. Remove
   each marker once its section is written. Ask the user for anything the code can't tell you.
6. Write the doc-map in `docs/pmdocs.toml`: one `[[map]]` per area of the source tree,
   pointing at the page that describes it. Set `[coverage] include` to the source roots.
   Then decide what else joins the site. List the Markdown outside `docs/`
   (`git ls-files "*.md"`, minus `docs/` and `TODO.md`), grouped by folder. The root
   README is rendered by default (`readme = false` under `[site]` turns it off). Propose
   a `[[site.extra]]` group — name, one-sentence `about`, paths — for any other set worth
   reading in the site (e.g. `adr/`, `CONTRIBUTING.md`), and ask the user which to include.
   Leaving files out is a fine answer.
7. Append `SKILL_DIR/assets/claude-md-snippet.md` to the project's `CLAUDE.md` (create
   it if absent).
8. Run `uv run scripts/pmdocs.py install-hooks`, then `build`, then `check`. Fix every
   ERROR. Resolve each WARN, or tell the user why it stands.
9. Commit (`docs: adopt the project-docs convention`) and report what was set up.

## adopt

Read `SKILL_DIR/references/adopt.md` first — it has the inventory checklist and the
mapping patterns from real migrations.

1. Inventory, read-only: doc files and their roles; HTML builders; git hooks
   (`git config core.hooksPath`, `.git/hooks`, husky/lefthook/pre-commit configs); Claude
   hooks in `.claude/settings*.json`; TODO/backlog files; decision logs; spec and plan
   headers (`**Status:**` lines); documentation rules in `CLAUDE.md`; Markdown outside
   `docs/` (`git ls-files "*.md"`), grouped by folder; and everything **waiting on the
   user** — "waiting on your eye/ear" sections, pending listening or visual checks,
   open decisions, "next test set up" notes, even inside data files — plus where
   verdicts have been recorded so far.
2. Propose a mapping table — every existing artifact → its fate (kept, converted, merged,
   excluded, retired) — and **stop for the user's approval**. Touch nothing before it.
   Every existing page that is kept gets a **parent** column: which category of the fixed
   sidebar it belongs under — `overview`, `product`, `architecture` or `decisions` (see
   `references/convention.md`). An existing page that already plays a category's role
   (an architecture overview, a decision log) becomes that category's page instead.
   Markdown outside `docs/` gets a row per folder: rendered in the site as a
   `[[site.extra]]` group (proposed name and `about`), or left out. The root README is in
   by default; say so, and offer `readme = false`.
3. Work on a branch: `git switch -c pmdocs-adopt`.
4. Migrate per the approved table:
   - Every page under `docs/` gets frontmatter — with its approved `parent:` — or is
     listed in `[paths] exclude`.
   - Specs and plans: `**Status:**` lines → `status:` in the vocabulary. When unsure
     which status applies, ask.
   - Existing backlog/TODO: items with real requirements → `docs/backlog.md` as B-nn
     (closed ones → `docs/backlog-archive.md`); loose ideas stay in `TODO.md` for triage.
     If the file is large, ask the user which they prefer.
   - Decision logs → `docs/decisions.md` as `## Dnn. Title`, keeping existing numbers.
   - Each question still waiting on the user → a gate in `docs/gates.md` (`## Gnn.`,
     `Status: waiting`), with its setup, pass condition and evidence; work blocked on it
     → `Status: blocked · Gate: Gnn`. Recent answered ones may become archived gates with
     their verdicts. Detailed verdict logs already kept elsewhere stay where they are,
     linked as evidence; statements that restate a verdict elsewhere become "see Gnn".
   - Approved outside-`docs/` groups → `[[site.extra]]` entries in `docs/pmdocs.toml`
     (they stay where they are; the site renders them with their source path shown).
5. Retire conflicting tooling (old builders, hooks, `core.hooksPath`) only with explicit
   approval.
6. Run init steps 2, 3, 4, 6, 7 and 8, in that order. In step 4 copy only the templates
   the project lacks — `docs/pmdocs.toml` always, starter pages only where no page plays
   that role, `TODO.md` only if absent; add exclusions from the mapping to
   `[paths] exclude`. In step 6 fold any existing doc-map into `[[map]]` entries. If
   `install-hooks` refuses because hooks exist, follow its message.
7. Commit on the branch and summarize: what moved where, what was retired, open WARNs.

## triage

Moves items from the user's `TODO.md` inbox into `docs/backlog.md`.

1. Read `TODO.md`; list its items numbered, one line each. Ask which to triage
   (default: all, in order).
2. For each chosen item, ask the clarifying questions that matter, one at a time: what
   exactly, why, how we'll know it's done, what blocks it. Skip what's already clear. If
   an item is really several, split it. If it duplicates a backlog item, say so and
   propose merging.
3. Draft the backlog entries:

   ```
   ## B<next>. <Title>
   Status: open · Added: <today> · Source: TODO.md

   <What and why. Acceptance criteria as a short list. Open questions.>
   ```

   The next ID is one more than the highest B-number in backlog and archive. Never reuse one.
4. Show the drafts and the exact `TODO.md` lines they replace. **Wait for approval.**
5. On approval, append the entries to `docs/backlog.md` and delete exactly those lines
   from `TODO.md`. Never edit other `TODO.md` text.
6. Run `uv run scripts/pmdocs.py check`. Commit (`docs(backlog): triage N items from
   TODO.md`) if the user wants it committed.

## update

1. Compare `VERSION` in `scripts/pmdocs.py` with `SKILL_DIR/assets/pmdocs.py`.
2. If older: repeat init step 2, add any missing `.gitattributes` lines (init step 3),
   run `install-hooks` (idempotent), `build`, `check`.
3. Replace the project's `## Docs duties (project-docs)` section in `CLAUDE.md` with the
   current `SKILL_DIR/assets/claude-md-snippet.md` (the duties evolve with the skill);
   leave the rest of `CLAUDE.md` untouched.
4. Resolve what the new version flags in `check`, with the user. Moving to 0.2.0 or later:
   delete `[site] nav` from `docs/pmdocs.toml` (an ERROR now), and propose a `parent:` for
   every page that warns "no parent" — one table, approved before you edit. Moving to
   0.3.0 or later: copy `gates.md` and `gates-archive.md` from the templates if absent,
   and propose gates for anything currently waiting on the user (adopt step 1's list).
5. Commit (`chore: update pmdocs to <version>`).

## Everyday duties

- Changing code: `docs/pmdocs.toml` says which pages cover it. Update them **in the same
  commit**. The post-edit hook names the pages; the Stop hook lists what is stale.
- New source directory: add a `[[map]]` entry.
- New page under `docs/`: give it a `parent:` (`overview`, `product`, `architecture` or
  `decisions`) so it sits under that category in the sidebar, not under "Other".
- Backlog: `in-progress` when you start, `done` when finished, `dropped` when
  abandoned. The hook archives closed items when `docs/backlog.md` is fully staged;
  otherwise run `uv run scripts/pmdocs.py check --fix`. Never delete items or decisions.
- Specs and plans: keep `status:` truthful — `approved` when the user approves,
  `in-progress` when implementation starts, `shipped` when merged. The pre-commit hook
  gives a new spec or plan without frontmatter a `draft` header; correct it.
- Non-obvious choices: add `## Dnn.` to `docs/decisions.md`.
- Never hand-edit `docs/site/` or `docs/roadmap.md`.
- `TODO.md` belongs to the user. You may append (`- noted while doing X: …`); never rewrite.
- Capture work you discover. When a question, feedback or a finding reveals work that
  is not being done in this task, say so and offer to capture it — never drop it
  silently. Default: append a one-line note to `TODO.md` (`- noted while <task>: …`). If
  the what and why are already clear, offer a drafted backlog item instead. Offer once,
  briefly, at a natural pause; the user decides.
- Gates — questions only the user can answer (a look, a listen, an approval, a
  decision) live in `docs/gates.md`:
  - When you hand the user something to judge, open a gate first: `## Gnn. <the
    question>`, `Status: waiting · Asked: <today> · For: Bnn · Needs: <preconditions>`,
    then Setup, "Passes if", Evidence. Work that can't proceed → `Status: blocked · Gate: Gnn`.
  - When the user gives a verdict, record it in the gate **at once, verbatim**:
    `- YYYY-MM-DD — "<their words>" — pass/fail/unclear. Checked: <preconditions>`,
    then set `Status: answered` (the hook archives it) and unblock the work.
  - Everywhere else — specs (`gates: [Gnn]`), backlog, CLAUDE.md, commits — refer to
    the gate by ID; never restate the verdict. A retraction is a new dated line in the
    gate, which goes back to `waiting`.
  - Each session starts with a note listing open gates; raise the relevant ones with
    the user rather than waiting to be asked.
- Before finishing: `uv run scripts/pmdocs.py check`.

## Red flags

| Thought | Reality |
|---|---|
| "I'll update the docs in a follow-up commit" | That is how every surveyed project drifted. Same commit. |
| "The hook only warned, so it's fine" | Warnings are the judgment tier. Judge them. |
| "I'll tidy the user's TODO.md while I'm here" | It's their inbox. Append only; triage with approval. |
| "That's out of scope, I'll just mention it" | A mention scrolls away. Offer to capture it in `TODO.md` or the backlog. |
| "The user said it looked right; I'll note it in the spec and CLAUDE.md" | Record it once, in the gate, verbatim. Everything else says "see Gnn". |
| "PMDOCS_SKIP=1 gets me past this" | Only when the user says so. Fix the doc error. |
| "The plan's checkboxes show progress" | They don't. Status lives in frontmatter and the backlog. |
