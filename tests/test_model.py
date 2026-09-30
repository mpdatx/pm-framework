import pmdocs
from helpers import has, write

SPEC = "docs/superpowers/specs/2026-09-01-x-design.md"
PLAN = "docs/superpowers/plans/2026-09-02-x.md"


def spec_text(status="approved", extra=""):
    return f"---\ntitle: X\nstatus: {status}\ncreated: 2026-09-01\n{extra}---\n\n# X\n"


def plan_text(status="approved", spec="superpowers/specs/2026-09-01-x-design.md"):
    return f"---\ntitle: X plan\nstatus: {status}\nspec: {spec}\n---\n\n# X plan\n"


def backlog_text(*items, title="Backlog"):
    return f"---\ntitle: {title}\n---\n\n# {title}\n\n" + "\n\n".join(items) + "\n"


def model(repo):
    return pmdocs.load_model(pmdocs.load_config(repo))


def errors(findings):
    return [f for f in findings if f.level == "ERROR"]


def test_clean_repo_has_no_findings(repo):
    m = model(repo)
    assert pmdocs.validate(m) == []
    assert pmdocs.check_links(m) == []


def test_model_classifies_pages(repo):
    write(repo, SPEC, spec_text())
    write(repo, PLAN, plan_text())
    m = model(repo)
    assert list(m.specs) == [SPEC] and list(m.plans) == [PLAN]
    assert set(m.pages) == {"docs/index.md", SPEC, PLAN}


def test_missing_frontmatter_is_error(repo):
    write(repo, "docs/architecture.md", "# Arch\n")
    assert has(pmdocs.validate(model(repo)), "ERROR", "missing frontmatter")


def test_missing_title_is_error(repo):
    write(repo, "docs/architecture.md", "---\nsummary: x\n---\n")
    assert has(pmdocs.validate(model(repo)), "ERROR", "frontmatter has no title")


def test_bad_spec_status(repo):
    write(repo, SPEC, spec_text("done"))
    assert has(pmdocs.validate(model(repo)), "ERROR", "status 'done' is not one of")


def test_spec_backlog_ref_missing(repo):
    write(repo, SPEC, spec_text(extra="backlog: [B09]\n"))
    assert has(pmdocs.validate(model(repo)), "ERROR", "backlog item B09 does not exist")


def test_spec_backlog_ref_ignores_zero_padding(repo):
    write(repo, SPEC, spec_text(extra="backlog: [B9]\n"))
    write(repo, "docs/backlog.md", backlog_text("## B09. Thing\nStatus: open · Added: 2026-09-01"))
    assert errors(pmdocs.validate(model(repo))) == []


def test_superseded_by_must_exist(repo):
    write(repo, SPEC, spec_text("superseded", "superseded_by: superpowers/specs/nope.md\n"))
    assert has(pmdocs.validate(model(repo)), "ERROR", "superseded_by superpowers/specs/nope.md does not exist")


def test_plan_spec_missing(repo):
    write(repo, PLAN, plan_text(spec="superpowers/specs/nope.md"))
    assert has(pmdocs.validate(model(repo)), "ERROR", "spec superpowers/specs/nope.md does not exist")


def test_plan_without_spec_is_fine(repo):
    write(repo, PLAN, "---\ntitle: P\nstatus: draft\n---\n")
    assert pmdocs.validate(model(repo)) == []


def test_bad_plan_status(repo):
    write(repo, SPEC, spec_text())
    write(repo, PLAN, plan_text("superseded"))
    assert has(pmdocs.validate(model(repo)), "ERROR", "status 'superseded' is not one of")


def test_backlog_item_errors(repo):
    write(repo, "docs/backlog.md", backlog_text(
        "## B01. No status\nAdded: 2026-09-01",
        "## B02. Bad date\nStatus: open · Added: yesterday",
        "## B2. Duplicate\nStatus: open · Added: 2026-09-01",
        "## B03. Bad spec\nStatus: open · Added: 2026-09-01 · Spec: superpowers/specs/nope.md"))
    f = pmdocs.validate(model(repo))
    assert has(f, "ERROR", "B01 status None is not one of")
    assert has(f, "ERROR", "B02 needs 'Added: YYYY-MM-DD'")
    assert has(f, "ERROR", "B2 duplicates docs/backlog.md:")
    assert has(f, "ERROR", "B03 spec superpowers/specs/nope.md does not exist")


def test_closed_item_in_backlog_warns(repo):
    write(repo, "docs/backlog.md", backlog_text("## B01. Done\nStatus: done · Added: 2026-09-01"))
    f = pmdocs.validate(model(repo))
    assert errors(f) == []
    assert has(f, "WARN", "B01 is done; check --fix moves it to docs/backlog-archive.md")


def test_open_item_in_archive_is_error(repo):
    write(repo, "docs/backlog-archive.md",
          backlog_text("## B01. Oops\nStatus: open · Added: 2026-09-01", title="Backlog archive"))
    assert has(pmdocs.validate(model(repo)), "ERROR", "B01 is open but archived")


def test_duplicate_across_backlog_and_archive(repo):
    write(repo, "docs/backlog.md", backlog_text("## B01. A\nStatus: open · Added: 2026-09-01"))
    write(repo, "docs/backlog-archive.md",
          backlog_text("## B01. B\nStatus: done · Added: 2026-09-01", title="Backlog archive"))
    assert has(pmdocs.validate(model(repo)), "ERROR", "B01 duplicates")


def test_decision_superseded_by_missing(repo):
    write(repo, "docs/decisions.md",
          "---\ntitle: Decisions\n---\n\n## D01. Old\nStatus: superseded by D02\n\nText.\n")
    assert has(pmdocs.validate(model(repo)), "ERROR", "D01 is superseded by D02, which does not exist")


def test_duplicate_decision(repo):
    write(repo, "docs/decisions.md",
          "---\ntitle: Decisions\n---\n\n## D01. A\n\nx\n\n## D1. B\n\ny\n")
    assert has(pmdocs.validate(model(repo)), "ERROR", "D1 duplicates")


def test_map_page_missing(repo):
    write(repo, "docs/pmdocs.toml", '[[map]]\npaths = ["src/**"]\npages = ["docs/architecture.md"]\n')
    assert has(pmdocs.validate(model(repo)), "ERROR", "[[map]] page docs/architecture.md does not exist")


def test_fill_marker_warns(repo):
    write(repo, "docs/product.md", "---\ntitle: Product\n---\n\n<!-- pmdocs:fill Purpose. -->\n")
    assert has(pmdocs.validate(model(repo)), "WARN", "pmdocs:fill")


def test_mentioning_the_fill_marker_is_not_a_marker(repo):
    write(repo, "docs/product.md", "---\ntitle: Product\n---\n\nTemplates carry `pmdocs:fill` markers.\n")
    assert pmdocs.validate(model(repo)) == []


def test_fill_marker_inside_code_block_is_not_a_marker(repo):
    write(repo, "docs/product.md",
          "---\ntitle: Product\n---\n\n```markdown\n<!-- pmdocs:fill Purpose. -->\n```\n")
    assert pmdocs.validate(model(repo)) == []


def test_excluded_pages_are_ignored(repo):
    write(repo, "docs/pmdocs.toml", '[paths]\nexclude = ["docs/course/**"]\n')
    write(repo, "docs/course/lesson-1.md", "# No frontmatter here\n")
    m = model(repo)
    assert "docs/course/lesson-1.md" not in m.pages
    assert pmdocs.validate(m) == []


def test_generated_roadmap_is_not_validated(repo):
    write(repo, "docs/roadmap.md", "# stale, no frontmatter\n")
    assert pmdocs.validate(model(repo)) == []


def test_links(repo):
    write(repo, "src/a.py", "x = 1\n")
    write(repo, "docs/architecture.md", "---\ntitle: Arch\n---\n\n# Arch\n\n## Data flow\n\ntext\n")
    write(repo, "docs/index.md",
          "---\ntitle: Demo\n---\n\n# Demo\n\n"
          "[ok](architecture.md#data-flow) [bad anchor](architecture.md#nope) "
          "[missing](nope.md) [code](../src/a.py) [roadmap](roadmap.md) "
          "[web](https://example.com) [self](#demo) [gone](../src/gone.py)\n")
    msgs = [f.msg for f in pmdocs.check_links(model(repo))]
    assert msgs == ["broken anchor architecture.md#nope", "broken link nope.md", "broken link ../src/gone.py"]


def test_link_to_excluded_page_is_fine(repo):
    write(repo, "docs/pmdocs.toml", '[paths]\nexclude = ["docs/course/**"]\n')
    write(repo, "docs/course/lesson-1.md", "# L1\n")
    write(repo, "docs/index.md", "---\ntitle: Demo\n---\n\n[l1](course/lesson-1.md)\n")
    assert pmdocs.check_links(model(repo)) == []


def test_slugify_and_duplicate_headings():
    tokens = pmdocs.markdown().parse("# Top\n\n## One `code`\n\n## One code\n\n### Two!\n")
    assert pmdocs.headings(tokens) == [(1, "Top", "top"), (2, "One `code`", "one-code"),
                                       (2, "One code", "one-code-1"), (3, "Two!", "two")]
