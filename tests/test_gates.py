import pmdocs
from helpers import has, write
from test_model import SPEC, backlog_text, model, spec_text

GATES_REL = "docs/gates.md"
GATES_ARCHIVE_REL = "docs/gates-archive.md"


def gates_text(*items, title="Waiting on you"):
    return f"---\ntitle: {title}\n---\n\n# {title}\n\n" + "\n\n".join(items) + "\n"


WAITING = ("## G04. Felt-piano pass 8: does Dry/Wet alone explain the wash?\n"
           "Status: waiting · Asked: 2026-09-28 · For: B03 · Needs: Live running\n\n"
           "Setup: both tracks at 5.00 s.\nPasses if: the wash is on B only.")
ANSWERED = ("## G02. Rows C vs D: does workstream 4 land?\n"
            "Status: answered · Asked: 2026-09-12\n\n"
            "### Verdicts\n\n- 2026-09-25 — \"D reads as a building\" — pass.")


def test_gates_are_parsed_into_the_model(repo):
    write(repo, GATES_REL, gates_text(WAITING))
    write(repo, "docs/backlog.md", backlog_text("## B03. Decide felt-piano\nStatus: blocked · Added: 2026-09-27"))
    m = model(repo)
    [g] = m.gates
    assert g.id == "G04" and g.status == "waiting"
    assert g.fields["Needs"] == "Live running" and g.fields["For"] == "B03"
    assert pmdocs.validate(m) == []


def test_gate_field_errors(repo):
    write(repo, GATES_REL, gates_text(
        "## G01. No status\nAsked: 2026-09-01",
        "## G02. Bad date\nStatus: waiting · Asked: soon",
        "## G03. Bad ref\nStatus: waiting · Asked: 2026-09-01 · For: B99",
        "## G3. Duplicate\nStatus: waiting · Asked: 2026-09-01"))
    f = pmdocs.validate(model(repo))
    assert has(f, "ERROR", "G01 status None is not one of waiting, answered, dropped")
    assert has(f, "ERROR", "G02 needs 'Asked: YYYY-MM-DD'")
    assert has(f, "ERROR", "G03 is for B99, which does not exist")
    assert has(f, "ERROR", "G3 duplicates")


def test_answered_gate_needs_a_recorded_verdict(repo):
    write(repo, GATES_ARCHIVE_REL, gates_text(
        "## G05. Nothing recorded\nStatus: answered · Asked: 2026-09-01", title="Gates archive"))
    assert has(pmdocs.validate(model(repo)), "WARN", "G05 is answered but has no dated verdict")


def test_waiting_gate_in_archive_is_error(repo):
    write(repo, GATES_ARCHIVE_REL, gates_text(WAITING, title="Gates archive"))
    assert has(pmdocs.validate(model(repo)), "ERROR", "G04 is waiting but archived")


def test_fix_archives_answered_gates(repo):
    write(repo, GATES_REL, gates_text(WAITING, ANSWERED))
    cfg = pmdocs.load_config(repo)
    fixed, touched = pmdocs.apply_fixes(cfg, pmdocs.load_model(cfg), "2026-09-30")
    assert has(fixed, "FIXED", "moved G02 to docs/gates-archive.md")
    assert {GATES_REL, GATES_ARCHIVE_REL} <= set(touched)
    open_text = (repo / GATES_REL).read_text(encoding="utf-8")
    archive = (repo / GATES_ARCHIVE_REL).read_text(encoding="utf-8")
    assert "G02" not in open_text and "G04" in open_text
    assert "## G02. Rows C vs D" in archive and "\"D reads as a building\"" in archive


def test_spec_shipped_while_its_gate_waits_is_drift(repo):
    write(repo, SPEC, spec_text("shipped", "gates: [G04]\n"))
    write(repo, GATES_REL, gates_text(WAITING.replace(" · For: B03", "")))
    assert has(pmdocs.drift_static(model(repo)), "WARN", "shipped, but gate G04 is still waiting")


def test_spec_gate_ref_must_exist(repo):
    write(repo, SPEC, spec_text("approved", "gates: [G09]\n"))
    assert has(pmdocs.validate(model(repo)), "ERROR", "gate G09 does not exist")


def test_backlog_item_blocked_on_an_answered_gate_is_drift(repo):
    write(repo, "docs/backlog.md", backlog_text("## B03. Decide\nStatus: blocked · Added: 2026-09-27 · Gate: G02"))
    write(repo, GATES_ARCHIVE_REL, gates_text(ANSWERED, title="Gates archive"))
    assert has(pmdocs.drift_static(model(repo)), "WARN", "B03 is blocked on G02, which is answered")


def test_roadmap_leads_with_what_is_waiting_on_the_user(repo):
    write(repo, GATES_REL, gates_text(WAITING))
    write(repo, "docs/backlog.md", backlog_text("## B03. Decide\nStatus: blocked · Added: 2026-09-27 · Gate: G04"))
    text = pmdocs.render_roadmap(model(repo))
    assert text.index("## Waiting on you") < text.index("## Initiatives")
    assert ("- **G04** [Felt-piano pass 8: does Dry/Wet alone explain the wash?]"
            "(gates.md#g04-felt-piano-pass-8-does-drywet-alone-explain-the-wash) — "
            "needs: Live running · for: B03 · asked 2026-09-28") in text


def test_roadmap_says_when_nothing_is_waiting(repo):
    assert "Nothing is waiting on you." in pmdocs.render_roadmap(model(repo))


def test_sidebar_puts_gates_after_overview_and_archives_last(repo):
    from test_site import outline
    write(repo, GATES_REL, gates_text(WAITING))
    write(repo, GATES_ARCHIVE_REL, gates_text(ANSWERED, title="Gates archive"))
    write(repo, "docs/backlog.md", backlog_text("## B03. Decide\nStatus: blocked · Added: 2026-09-27"))
    write(repo, "docs/backlog-archive.md", "---\ntitle: Backlog archive\n---\n")
    pmdocs.build(pmdocs.load_config(repo))
    o = outline((repo / "docs/site/index.html").read_text(encoding="utf-8"))
    assert o[:4] == ["Demo", "Waiting on you", "Roadmap", "Backlog"]
    assert o[-3:] == ["---", "Backlog archive", "Gates archive"]


def test_backlog_gate_ref_must_exist(repo):
    write(repo, "docs/backlog.md", backlog_text("## B03. Decide\nStatus: blocked · Added: 2026-09-27 · Gate: G77"))
    assert has(pmdocs.validate(model(repo)), "ERROR", "B03 gate G77 does not exist")
