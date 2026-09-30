from datetime import datetime, timezone

import pmdocs
from helpers import commit_all, git, has, write
from test_model import PLAN, SPEC, backlog_text, model, plan_text, spec_text

MAPPED = ('[site]\ntitle = "demo"\n\n[[map]]\npaths = ["src/**"]\npages = ["docs/architecture.md"]\n\n'
          '[coverage]\ninclude = ["src/**", "lib/**"]\n')
ARCH = "---\ntitle: Architecture\norder: 20\n---\n\n# Architecture\n"


def mapped(repo):
    write(repo, "docs/pmdocs.toml", MAPPED)
    write(repo, "docs/architecture.md", ARCH)
    return pmdocs.load_config(repo)


def test_plan_moving_while_spec_is_draft(repo):
    write(repo, SPEC, spec_text("draft"))
    write(repo, PLAN, plan_text("in-progress"))
    assert has(pmdocs.drift_static(model(repo)), "WARN", f"still draft, but plan {PLAN} is in-progress")


def test_plan_shipped_but_spec_not(repo):
    write(repo, SPEC, spec_text("approved"))
    write(repo, PLAN, plan_text("shipped"))
    assert has(pmdocs.drift_static(model(repo)), "WARN", f"shipped, but its spec {SPEC} is approved")


def test_spec_shipped_but_backlog_open(repo):
    write(repo, SPEC, spec_text("shipped", "backlog: [B01]\n"))
    write(repo, "docs/backlog.md", backlog_text("## B01. X\nStatus: open · Added: 2026-09-01"))
    assert has(pmdocs.drift_static(model(repo)), "WARN", "shipped, but B01 is still open")


def test_consistent_statuses_have_no_drift(repo):
    write(repo, SPEC, spec_text("shipped", "backlog: [B01]\n"))
    write(repo, PLAN, plan_text("shipped"))
    write(repo, "docs/backlog-archive.md",
          backlog_text("## B01. X\nStatus: done · Added: 2026-09-01", title="Backlog archive"))
    assert pmdocs.drift_static(model(repo)) == []


def test_in_progress_item_untouched(repo):
    write(repo, "docs/backlog.md", backlog_text("## B01. Slow\nStatus: in-progress · Added: 2026-01-01"))
    stamp = "2026-01-01T12:00:00+00:00"
    commit_all(repo, env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
    jan1 = datetime(2026, 1, 1, 12, tzinfo=timezone.utc).timestamp()
    m = model(repo)
    assert pmdocs.drift_stale_progress(m, jan1 + 10 * 86400) == []
    assert has(pmdocs.drift_stale_progress(m, jan1 + 40 * 86400), "WARN", "B01 is in-progress but untouched for 40 days")


def test_stale_progress_outside_git_is_silent(tmp_path):
    root = tmp_path / "nogit"
    write(root, "docs/pmdocs.toml", "")
    write(root, "docs/backlog.md", backlog_text("## B01. X\nStatus: in-progress · Added: 2026-01-01"))
    m = pmdocs.load_model(pmdocs.load_config(root))
    assert pmdocs.drift_stale_progress(m, 9e9) == []


def test_changed_files_worktree_and_staged(repo):
    commit_all(repo)
    write(repo, "src/a.py", "1\n")
    write(repo, "docs/index.md", "---\ntitle: D\n---\n")
    assert pmdocs.changed_files(repo, staged=False) == {"src/a.py", "docs/index.md"}
    assert pmdocs.changed_files(repo, staged=True) == set()
    git(repo, "add", "src/a.py")
    assert pmdocs.changed_files(repo, staged=True) == {"src/a.py"}


def test_changed_files_unborn_branch(repo):
    git(repo, "add", "docs/index.md")
    assert pmdocs.changed_files(repo, staged=True) == {"docs/index.md"}
    assert pmdocs.changed_files(repo, staged=False) == {"docs/index.md", "docs/pmdocs.toml"}


def test_changed_files_odd_names(repo):
    commit_all(repo)
    write(repo, "src/my file ü.py", "1\n")
    assert pmdocs.changed_files(repo, staged=False) == {"src/my file ü.py"}


def test_staleness(repo):
    cfg = mapped(repo)
    assert has(pmdocs.staleness(cfg, {"src/a.py"}), "WARN", "none of its docs did: docs/architecture.md")
    assert pmdocs.staleness(cfg, {"src/a.py", "docs/architecture.md"}) == []
    assert pmdocs.staleness(cfg, {"README.md"}) == []


def test_staleness_ignores_the_vendored_tool(repo):
    write(repo, "docs/pmdocs.toml", MAPPED.replace('"src/**"]\npages', '"src/**", "scripts/**"]\npages', 1))
    write(repo, "docs/architecture.md", ARCH)
    cfg = pmdocs.load_config(repo)
    assert pmdocs.staleness(cfg, {"scripts/pmdocs.py", "scripts/hooks/pre-commit"}) == []
    assert has(pmdocs.staleness(cfg, {"scripts/other.py"}), "WARN", "docs/architecture.md")


def test_coverage_ignores_the_vendored_tool(repo):
    write(repo, "docs/pmdocs.toml", '[coverage]\ninclude = ["scripts/**"]\n')
    write(repo, "scripts/pmdocs.py", "x = 1\n")
    write(repo, "scripts/hooks/pre-commit", "#!/bin/sh\n")
    write(repo, "scripts/other.py", "x = 1\n")
    git(repo, "add", "-A")
    assert [f.where for f in pmdocs.coverage(pmdocs.load_config(repo))] == ["scripts/other.py"]


def test_pages_for(repo):
    cfg = mapped(repo)
    assert pmdocs.pages_for(cfg, "src\\x\\a.py") == ["docs/architecture.md"]
    assert pmdocs.pages_for(cfg, "README.md") == []


def test_coverage(repo):
    cfg = mapped(repo)
    write(repo, "src/a.py", "1\n")
    write(repo, "lib/b.py", "1\n")
    git(repo, "add", "-A")
    assert [f.where for f in pmdocs.coverage(cfg)] == ["lib/b.py"]
