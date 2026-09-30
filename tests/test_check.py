import pmdocs
from helpers import commit_all, has, run_cli, write
from test_model import PLAN, SPEC, backlog_text

CLOSED = backlog_text(
    "## B01. Done thing\nStatus: done · Added: 2026-09-01\n\nNotes.",
    "## B02. Open thing\nStatus: open · Added: 2026-09-02")


def fix(repo, blocked=frozenset()):
    cfg = pmdocs.load_config(repo)
    return pmdocs.apply_fixes(cfg, pmdocs.load_model(cfg), "2026-09-30", blocked)


def test_fix_moves_closed_items(repo):
    write(repo, "docs/backlog.md", CLOSED)
    fixed, touched = fix(repo)
    assert has(fixed, "FIXED", "moved B01 to docs/backlog-archive.md")
    assert set(touched) == {"docs/backlog.md", "docs/backlog-archive.md"}
    backlog = (repo / "docs/backlog.md").read_text(encoding="utf-8")
    archive = (repo / "docs/backlog-archive.md").read_text(encoding="utf-8")
    assert "B01" not in backlog and "## B02. Open thing" in backlog and backlog.endswith("\n")
    assert archive.startswith("---\ntitle: Backlog archive\n")
    assert ("## B01. Done thing\nStatus: done · Added: 2026-09-01 · Closed: 2026-09-30\n\nNotes.\n") in archive
    cfg = pmdocs.load_config(repo)
    assert pmdocs.validate(pmdocs.load_model(cfg)) == []


def test_fix_keeps_existing_closed_date_and_appends(repo):
    write(repo, "docs/backlog-archive.md",
          backlog_text("## B00. Older\nStatus: done · Added: 2026-08-01 · Closed: 2026-08-02", title="Backlog archive"))
    write(repo, "docs/backlog.md", backlog_text("## B01. Last\nStatus: dropped · Added: 2026-09-01 · Closed: 2026-09-05"))
    fix(repo)
    archive = (repo / "docs/backlog-archive.md").read_text(encoding="utf-8")
    assert archive.index("## B00. Older") < archive.index("## B01. Last")
    assert "Closed: 2026-09-05" in archive and "2026-09-30" not in archive
    assert (repo / "docs/backlog.md").read_text(encoding="utf-8").endswith("# Backlog\n")


def test_fix_adds_frontmatter_to_new_spec_and_plan(repo):
    write(repo, SPEC, "# Rising parts: design\n\nBody.\n")
    write(repo, PLAN, "# Rising parts Implementation Plan\n\n**Spec:** `docs/superpowers/specs/2026-09-01-x-design.md`\n")
    fixed, touched = fix(repo)
    assert set(touched) == {SPEC, PLAN}
    spec_meta = pmdocs.split_frontmatter(pmdocs.read_text(repo / SPEC))[0]
    plan_meta = pmdocs.split_frontmatter(pmdocs.read_text(repo / PLAN))[0]
    assert spec_meta == {"title": "Rising parts: design", "status": "draft"}
    assert plan_meta == {"title": "Rising parts Implementation Plan", "status": "draft",
                         "spec": "superpowers/specs/2026-09-01-x-design.md"}


def test_empty_frontmatter_reports_no_title_and_is_not_double_fixed(repo):
    write(repo, SPEC, "---\n---\n# New\n")
    cfg = pmdocs.load_config(repo)
    assert has(pmdocs.validate(pmdocs.load_model(cfg)), "ERROR", "frontmatter has no title")
    fixed, touched = fix(repo)
    assert touched == [] and pmdocs.read_text(repo / SPEC) == "---\n---\n# New\n"


def test_fix_respects_blocked_files(repo):
    write(repo, "docs/backlog.md", CLOSED)
    write(repo, SPEC, "# New\n")
    fixed, touched = fix(repo, blocked=frozenset({"docs/backlog.md", SPEC}))
    assert fixed == [] and touched == []


def test_check_cli_clean(repo):
    commit_all(repo)
    r = run_cli(repo, "check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no errors or warnings" in r.stdout


def test_check_cli_error_exits_1(repo):
    write(repo, "docs/architecture.md", "# no frontmatter\n")
    r = run_cli(repo, "check")
    assert r.returncode == 1
    assert "ERROR docs/architecture.md: missing frontmatter" in r.stdout


def test_check_cli_fix(repo):
    write(repo, "docs/backlog.md", CLOSED)
    r = run_cli(repo, "check", "--fix")
    assert r.returncode == 0, r.stdout
    assert "FIXED docs/backlog.md: moved B01" in r.stdout
    assert (repo / "docs/backlog-archive.md").is_file()


def test_check_cli_reports_inbox(repo):
    write(repo, "TODO.md", "- one\n- two\n")
    r = run_cli(repo, "check")
    assert "INFO TODO.md: 2 inbox item(s) awaiting triage" in r.stdout


def test_check_cli_outside_project(tmp_path):
    r = run_cli(tmp_path, "check")
    assert r.returncode == 2 and "no docs/pmdocs.toml found" in r.stderr
