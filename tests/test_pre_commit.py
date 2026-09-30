import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import pmdocs
from conftest import INDEX
from helpers import HOOK, TOOL, commit_all, git, run_cli, write
from test_check import CLOSED
from test_drift import mapped
from test_model import SPEC


def staged(repo):
    return set(git(repo, "diff", "--cached", "--name-only").split())


def test_pre_commit_builds_and_stages_site(repo):
    # unborn branch: this is the init workflow's first commit
    git(repo, "add", "-A")
    assert pmdocs.hook_pre_commit(repo) == 0
    assert {"docs/site/index.html", "docs/roadmap.md", "docs/site/roadmap.html"} <= staged(repo)


def test_pre_commit_builds_from_index_not_worktree(repo):
    write(repo, "docs/index.md", INDEX.replace("Hello.", "Alpha."))
    git(repo, "add", "-A")
    write(repo, "docs/index.md", INDEX.replace("Hello.", "Beta."))
    assert pmdocs.hook_pre_commit(repo) == 0
    html = git(repo, "show", ":docs/site/index.html")
    assert "Alpha." in html and "Beta." not in html


def test_pre_commit_blocks_on_error(repo, capsys):
    write(repo, "docs/architecture.md", "# no frontmatter\n")
    git(repo, "add", "-A")
    assert pmdocs.hook_pre_commit(repo) == pmdocs.BLOCK_EXIT
    err = capsys.readouterr().err
    assert "missing frontmatter" in err and "PMDOCS_SKIP=1" in err
    assert "docs/site/index.html" not in staged(repo)


def test_pre_commit_error_only_in_worktree_does_not_block(repo):
    git(repo, "add", "-A")
    write(repo, "docs/architecture.md", "# no frontmatter\n")  # untracked, not part of the commit
    assert pmdocs.hook_pre_commit(repo) == 0
    assert "docs/architecture.md" not in staged(repo)


def test_pre_commit_keeps_untracked_files_in_site(repo):
    write(repo, "docs/site/scratch.txt", "mine\n")
    git(repo, "add", "docs")
    git(repo, "rm", "-q", "--cached", "docs/site/scratch.txt")
    assert pmdocs.hook_pre_commit(repo) == 0
    assert (repo / "docs/site/scratch.txt").read_text(encoding="utf-8") == "mine\n"
    assert "docs/site/scratch.txt" not in staged(repo)


ROOT_PAGE_MAP = ('[site]\ntitle = "demo"\n\n[[map]]\npaths = ["corpus/**"]\n'
                 'pages = ["CORPUS-LICENSES.md"]\n')


def test_pre_commit_accepts_a_map_page_outside_docs(repo, capsys):
    # the hook validates an export of docs/ only; a [[map]] page at the repo root must
    # still resolve (it did in `check`, which sees the whole repo)
    write(repo, "docs/pmdocs.toml", ROOT_PAGE_MAP)
    write(repo, "CORPUS-LICENSES.md", "# Licenses\n")
    git(repo, "add", "-A")
    assert pmdocs.hook_pre_commit(repo) == 0, capsys.readouterr().err


def error_lines(text):
    return sorted(line for line in text.splitlines() if line.startswith("ERROR "))


def test_check_and_hook_report_the_same_errors(repo, capsys):
    # parity across the two roots validate() runs against: the whole repo (check) and
    # the index export (hook). Mixes a root-level map page, a broken map page and a
    # broken page, so any root-sensitive check shows up as a difference.
    write(repo, "docs/pmdocs.toml", ROOT_PAGE_MAP.replace('["CORPUS-LICENSES.md"]',
                                                          '["CORPUS-LICENSES.md", "MISSING.md"]'))
    write(repo, "CORPUS-LICENSES.md", "# Licenses\n")
    write(repo, "docs/architecture.md", "# no frontmatter\n")
    git(repo, "add", "-A")
    check = run_cli(repo, "check")
    assert pmdocs.hook_pre_commit(repo) == pmdocs.BLOCK_EXIT
    hook = capsys.readouterr().err
    assert error_lines(check.stdout) == error_lines(hook)
    assert any("MISSING.md" in line for line in error_lines(hook))
    assert not any("CORPUS-LICENSES.md" in line for line in error_lines(hook))


def test_pre_commit_warns_but_passes(repo, capsys):
    mapped(repo)
    commit_all(repo)
    write(repo, "src/a.py", "1\n")
    git(repo, "add", "src/a.py")
    assert pmdocs.hook_pre_commit(repo) == 0
    assert "WARN src/a.py: changed, but none of its docs did" in capsys.readouterr().err


def test_pre_commit_skip_env(repo, monkeypatch):
    monkeypatch.setenv("PMDOCS_SKIP", "1")
    git(repo, "add", "-A")
    assert pmdocs.hook_pre_commit(repo) == 0
    assert "docs/site/index.html" not in staged(repo)


def test_pre_commit_skips_during_merge(repo):
    git(repo, "add", "-A")
    (repo / ".git" / "MERGE_HEAD").write_text("0" * 40, encoding="utf-8")
    assert pmdocs.hook_pre_commit(repo) == 0
    assert "docs/site/index.html" not in staged(repo)


def test_pre_commit_without_committed_config_is_a_no_op(repo, capsys):
    git(repo, "add", "docs/index.md")  # pmdocs.toml not staged yet
    assert pmdocs.hook_pre_commit(repo) == 0
    assert "not in the index" in capsys.readouterr().err


def test_pre_commit_fixes_clean_backlog(repo):
    write(repo, "docs/backlog.md", CLOSED)
    git(repo, "add", "-A")
    assert pmdocs.hook_pre_commit(repo, today="2026-09-30") == 0
    assert "docs/backlog-archive.md" in staged(repo)
    assert "B01" not in git(repo, "show", ":docs/backlog.md")


def test_pre_commit_leaves_dirty_backlog_alone(repo, capsys):
    write(repo, "docs/backlog.md", CLOSED)
    git(repo, "add", "-A")
    write(repo, "docs/backlog.md", CLOSED + "\nunstaged note\n")
    assert pmdocs.hook_pre_commit(repo) == 0
    assert "docs/backlog-archive.md" not in staged(repo)
    assert "unstaged note" not in git(repo, "show", ":docs/backlog.md")
    assert "check --fix moves it" in capsys.readouterr().err


def test_pre_commit_fixes_new_spec_frontmatter(repo):
    write(repo, SPEC, "# New thing\n")
    git(repo, "add", "-A")
    assert pmdocs.hook_pre_commit(repo) == 0
    assert git(repo, "show", f":{SPEC}").startswith("---\ntitle: New thing\nstatus: draft\n---")


# --- the real sh hook, driven through `git commit` ---------------------------

SH = shutil.which("sh")
PY = Path(sys.executable).as_posix()
needs_sh = pytest.mark.skipif(SH is None, reason="needs a POSIX sh (Git for Windows provides one)")


def vendor(repo):
    write(repo, "scripts/pmdocs.py", TOOL.read_text(encoding="utf-8"))
    hook = repo / "scripts" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_bytes(HOOK.read_bytes())
    hook.chmod(0o755)
    git(repo, "config", "core.hooksPath", "scripts/hooks")


def fake_uv(tmp_path, body):
    """A `uv` on PATH that runs `uv run --quiet X args` as `python X args` (or does `body`)."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    p = d / "uv"
    p.write_bytes(f"#!/bin/sh\n{body}\n".encode())
    p.chmod(0o755)
    return {**os.environ, "PATH": str(d) + os.pathsep + os.environ["PATH"]}


def commit(repo, env):
    return subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", env=env)


def test_hook_script_is_lf_and_executable_sh():
    data = HOOK.read_bytes()
    assert data.startswith(b"#!/bin/sh\n") and b"\r" not in data


@needs_sh
def test_git_hook_blocks_on_doc_error(repo, tmp_path):
    vendor(repo)
    env = fake_uv(tmp_path, f'shift; shift; exec "{PY}" "$@"')
    write(repo, "docs/architecture.md", "# no frontmatter\n")
    git(repo, "add", "-A")
    r = commit(repo, env)
    assert r.returncode != 0 and "missing frontmatter" in r.stderr


@needs_sh
def test_git_hook_passes_and_commits_site(repo, tmp_path):
    vendor(repo)
    env = fake_uv(tmp_path, f'shift; shift; exec "{PY}" "$@"')
    git(repo, "add", "-A")
    r = commit(repo, env)
    assert r.returncode == 0, r.stderr
    assert "docs/site/index.html" in git(repo, "show", "--name-only", "--format=", "HEAD")


@needs_sh
def test_git_hook_commit_with_paths_commits_matching_site(repo, tmp_path):
    vendor(repo)
    env = fake_uv(tmp_path, f'shift; shift; exec "{PY}" "$@"')
    git(repo, "add", "-A")
    assert commit(repo, env).returncode == 0
    write(repo, "docs/index.md", INDEX.replace("Hello.", "Committed."))
    write(repo, "docs/other.md", "---\ntitle: Other\n---\n\nnot part of this commit\n")
    git(repo, "add", "docs/other.md")
    r = subprocess.run(["git", "commit", "-q", "-m", "paths", "docs/index.md"], cwd=repo,
                       capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode == 0, r.stderr
    committed = git(repo, "show", "HEAD:docs/site/index.html")
    assert "Committed." in committed
    names = git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert "docs/other.md" not in names and "docs/site/other.html" not in names


@needs_sh
def test_git_hook_under_autocrlf_with_crlf_and_bom(repo, tmp_path):
    # Review Focus 1, end to end: a Windows-style checkout (autocrlf=true, CRLF + BOM in
    # the Markdown and the config) commits cleanly through the real hook, and afterwards
    # the working tree's site is not reported stale.
    git(repo, "config", "core.autocrlf", "true")
    vendor(repo)
    env = fake_uv(tmp_path, f'shift; shift; exec "{PY}" "$@"')

    def crlf_bom(rel, text):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

    crlf_bom("docs/pmdocs.toml", '[site]\ntitle = "demo"\n')
    crlf_bom("docs/index.md", INDEX + "\n## Section\n\n[arch](architecture.md#data-flow)\n")
    crlf_bom("docs/architecture.md", "---\ntitle: Arch\n---\n\n# Arch\n\n## Data flow\n\ntext\n")
    git(repo, "add", "-A")
    r = commit(repo, env)
    assert r.returncode == 0, r.stderr
    assert "docs/site/architecture.html" in git(repo, "show", "--name-only", "--format=", "HEAD")
    assert run_cli(repo, "build", "--check").returncode == 0
    check = run_cli(repo, "check")
    assert check.returncode == 0, check.stdout


@needs_sh
def test_git_hook_tool_crash_allows_commit(repo, tmp_path):
    vendor(repo)
    env = fake_uv(tmp_path, "exit 3")
    write(repo, "docs/architecture.md", "# no frontmatter\n")
    git(repo, "add", "-A")
    r = commit(repo, env)
    assert r.returncode == 0 and "commit allowed" in r.stderr
