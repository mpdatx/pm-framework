import importlib.util
import shutil

import pytest

from helpers import REPO, commit_all, git, write


def load_release():
    spec = importlib.util.spec_from_file_location("release", REPO / "scripts" / "release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TOOL = 'VERSION = "{v}"\n'
PAIRS = ["skill/project-docs/assets/pmdocs.py", "scripts/pmdocs.py"]


def set_version(repo, v):
    for rel in ["tool/pmdocs.py", *PAIRS]:
        write(repo, rel, TOOL.format(v=v))


@pytest.fixture
def proj(tmp_path):
    """A miniature pm-framework: tool, synced copies, sync script, .release/ ignored."""
    r = tmp_path / "pmf"
    r.mkdir()
    git(r, "init", "-q", "-b", "master")
    for key, value in [("user.email", "t@example.com"), ("user.name", "Test"),
                       ("core.autocrlf", "false"), ("commit.gpgsign", "false")]:
        git(r, "config", key, value)
    set_version(r, "0.1.0")
    write(r, "tool/hooks/pre-commit", "#!/bin/sh\n")
    write(r, "skill/project-docs/assets/hooks/pre-commit", "#!/bin/sh\n")
    write(r, "scripts/hooks/pre-commit", "#!/bin/sh\n")
    write(r, "skill/project-docs/SKILL.md", "---\nname: project-docs\n---\n")
    shutil.copyfile(REPO / "scripts" / "sync_assets.py", r / "scripts" / "sync_assets.py")
    write(r, ".gitignore", ".release/\n")
    commit_all(r)
    return r


def passing(root):
    return True


def failing(root):
    return False


def test_first_release_tags_and_creates_the_release_worktree(proj):
    rel = load_release()
    assert rel.release(proj, run_tests=passing) == "v0.1.0"
    assert git(proj, "tag", "--list").split() == ["v0.1.0"]
    wt = proj / ".release"
    assert (wt / "skill" / "project-docs" / "SKILL.md").is_file()
    assert git(wt, "rev-parse", "HEAD") == git(proj, "rev-parse", "v0.1.0^{commit}")
    assert git(wt, "branch", "--show-current").strip() == "release"
    assert git(proj, "status", "--porcelain") == ""  # the worktree is ignored


def test_next_release_fast_forwards_the_worktree(proj):
    rel = load_release()
    rel.release(proj, run_tests=passing)
    set_version(proj, "0.1.1")
    commit_all(proj, "bump")
    assert rel.release(proj, run_tests=passing) == "v0.1.1"
    assert (proj / ".release" / "tool" / "pmdocs.py").read_text(encoding="utf-8") == 'VERSION = "0.1.1"\n'


def test_unreleased_work_never_reaches_the_worktree(proj):
    rel = load_release()
    rel.release(proj, run_tests=passing)
    set_version(proj, "0.2.0")  # uncommitted development
    assert (proj / ".release" / "tool" / "pmdocs.py").read_text(encoding="utf-8") == 'VERSION = "0.1.0"\n'


def test_refuses_dirty_tree(proj):
    write(proj, "notes.txt", "wip\n")
    rel = load_release()
    with pytest.raises(rel.ReleaseError, match="uncommitted"):
        rel.release(proj, run_tests=passing)


def test_refuses_other_branch(proj):
    git(proj, "switch", "-q", "-c", "feature")
    rel = load_release()
    with pytest.raises(rel.ReleaseError, match="master"):
        rel.release(proj, run_tests=passing)


def test_refuses_stale_assets(proj):
    write(proj, "tool/pmdocs.py", 'VERSION = "0.1.0"\n# changed, not synced\n')
    commit_all(proj)
    rel = load_release()
    with pytest.raises(rel.ReleaseError, match="sync_assets"):
        rel.release(proj, run_tests=passing)


def test_refuses_unbumped_version(proj):
    rel = load_release()
    rel.release(proj, run_tests=passing)
    write(proj, "README.md", "x\n")
    commit_all(proj)
    with pytest.raises(rel.ReleaseError, match="not higher than the last release v0.1.0"):
        rel.release(proj, run_tests=passing)


def test_refuses_failing_tests(proj):
    rel = load_release()
    with pytest.raises(rel.ReleaseError, match="tests"):
        rel.release(proj, run_tests=failing)
    assert git(proj, "tag", "--list") == ""


def test_dry_run_changes_nothing(proj):
    assert load_release().release(proj, run_tests=passing, dry_run=True) == "v0.1.0"
    assert git(proj, "tag", "--list") == "" and not (proj / ".release").exists()
