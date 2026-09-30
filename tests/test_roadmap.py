import pmdocs
from helpers import write
from test_model import PLAN, SPEC, backlog_text, model, plan_text, spec_text


def seeded(repo):
    write(repo, SPEC, spec_text("in-progress", "backlog: [B01]\n"))
    write(repo, PLAN, plan_text("in-progress"))
    write(repo, "docs/backlog.md", backlog_text(
        "## B01. Build X\nStatus: in-progress · Spec: superpowers/specs/2026-09-01-x-design.md · Added: 2026-09-01",
        "## B02. Later | maybe\nStatus: open · Added: 2026-09-02",
        "## B03. Stuck\nStatus: blocked · Added: 2026-09-03"))
    write(repo, "TODO.md", "- idea one\n- idea two\n")
    return model(repo)


def test_roadmap_content(repo):
    text = pmdocs.render_roadmap(seeded(repo))
    assert text.startswith("---\ntitle: Roadmap\n")
    assert pmdocs.GENERATED_BANNER in text
    assert ("| [X](superpowers/specs/2026-09-01-x-design.md) | in-progress | "
            "[X plan](superpowers/plans/2026-09-02-x.md) (in-progress) | B01 |") in text
    assert text.index("### In progress") < text.index("### Blocked") < text.index("### Open")
    assert "- **B01** [Build X](backlog.md#b01-build-x) — [spec](superpowers/specs/2026-09-01-x-design.md)" in text
    assert "2 item(s) in `TODO.md` awaiting triage." in text
    assert "No drift detected." in text
    assert "Closed items: none yet." in text


def test_roadmap_empty_project(repo):
    text = pmdocs.render_roadmap(model(repo))
    assert "No specs yet." in text and "Nothing open." in text and "\nEmpty.\n" in text


def test_roadmap_lists_drift(repo):
    write(repo, SPEC, spec_text("draft"))
    write(repo, PLAN, plan_text("in-progress"))
    assert f"still draft, but plan {PLAN} is in-progress" in pmdocs.render_roadmap(model(repo))


def test_roadmap_counts_archive(repo):
    write(repo, "docs/backlog-archive.md",
          backlog_text("## B01. X\nStatus: done · Added: 2026-09-01", title="Backlog archive"))
    assert "Closed items: 1 in [the archive](backlog-archive.md)." in pmdocs.render_roadmap(model(repo))


def test_roadmap_escapes_markdown_in_titles(repo):
    write(repo, SPEC, spec_text().replace("title: X", "title: 'Rising *parts* `x` a_b'"))
    text = pmdocs.render_roadmap(model(repo))
    assert r"[Rising \*parts\* \`x\` a\_b](superpowers/specs/2026-09-01-x-design.md)" in text


def test_roadmap_deterministic(repo):
    m = seeded(repo)
    assert pmdocs.render_roadmap(m) == pmdocs.render_roadmap(m)


def test_roadmap_frontmatter_is_valid(repo):
    meta, _, err = pmdocs.split_frontmatter(pmdocs.render_roadmap(seeded(repo)))
    assert err is None and meta["title"] == "Roadmap" and meta["order"] == 5
