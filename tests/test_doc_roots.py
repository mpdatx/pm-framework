"""Doc roots below the repository top, siblings, and nesting (B09)."""
import os
import subprocess
import sys

import pytest

import pmdocs
from helpers import HOOK, TOOL, commit_all, git, has, run_cli, write

ARCH = "---\ntitle: Architecture\n---\n\n# Architecture\n"


def doc_root(repo, rel, title, maps='[[map]]\npaths = ["src/**"]\npages = ["docs/architecture.md"]\n'):
    """Create a doc root at repo/rel (rel '' = the repo top) with a src/** -> architecture map."""
    root = repo / rel if rel else repo
    write(root, "docs/pmdocs.toml", f'[site]\ntitle = "{title}"\nreadme = false\n\n{maps}\n'
                                    '[coverage]\ninclude = ["**/*.py"]\n')
    write(root, "docs/index.md", f"---\ntitle: {title}\n---\n\n# {title}\n")
    write(root, "docs/architecture.md", ARCH)
    return root


def vendor(root):
    """Copy the tool and hook into a doc root, as the skill's init does."""
    write(root, "scripts/pmdocs.py", TOOL.read_text(encoding="utf-8"))
    hook = root / "scripts" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_bytes(HOOK.read_bytes())
    hook.chmod(0o755)


@pytest.fixture
def mono(tmp_path):
    r = tmp_path / "mono"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    for key, value in [("user.email", "t@example.com"), ("user.name", "Test"),
                       ("core.autocrlf", "false"), ("commit.gpgsign", "false")]:
        git(r, "config", key, value)
    return r


# --- a single doc root in a subfolder -------------------------------------------------

def test_changed_files_are_doc_root_relative_and_confined(mono):
    foo = doc_root(mono, "apps/foo", "foo")
    write(foo, "src/a.py", "x = 1\n")
    write(mono, "other/x.py", "y = 1\n")
    commit_all(mono)
    write(foo, "src/a.py", "x = 2\n")
    write(mono, "other/x.py", "y = 2\n")
    write(foo, "src/new.py", "z = 1\n")
    assert pmdocs.changed_files(foo, staged=False) == {"src/a.py", "src/new.py"}
    git(mono, "add", "-A")
    assert pmdocs.changed_files(foo, staged=True) == {"src/a.py", "src/new.py"}


def test_staleness_fires_in_a_subfolder_doc_root(mono):
    foo = doc_root(mono, "apps/foo", "foo")
    write(foo, "src/a.py", "x = 1\n")
    commit_all(mono)
    write(foo, "src/a.py", "x = 2\n")
    r = run_cli(foo, "check")
    assert r.returncode == 0, r.stdout
    assert "WARN src/a.py: changed, but none of its docs did: docs/architecture.md" in r.stdout


def test_paths_may_not_leave_the_doc_root(mono):
    foo = doc_root(mono, "apps/foo", "foo",
                   maps='[[map]]\npaths = ["../shared/**"]\npages = ["../README.md"]\n')
    write(foo, "docs/pmdocs.toml", (foo / "docs/pmdocs.toml").read_text(encoding="utf-8")
          + '\n[[site.extra]]\ngroup = "X"\npaths = ["../notes/*.md"]\n')
    f = pmdocs.validate(pmdocs.load_model(pmdocs.load_config(foo)))
    assert has(f, "ERROR", "[[map]] path ../shared/** leaves the doc root")
    assert has(f, "ERROR", "[[map]] page ../README.md leaves the doc root")
    assert has(f, "ERROR", "[[site.extra]] path ../notes/*.md leaves the doc root")


def test_vendored_tool_finds_its_own_doc_root_from_anywhere(mono):
    foo = doc_root(mono, "apps/foo", "foo")
    vendor(foo)
    write(foo, "src/a.py", "x = 1\n")
    commit_all(mono)
    write(foo, "src/a.py", "x = 2\n")
    # run from the repo top, which has no docs/pmdocs.toml of its own
    r = subprocess.run([sys.executable, str(foo / "scripts" / "pmdocs.py"), "check"], cwd=mono,
                       capture_output=True, text=True, encoding="utf-8")
    assert "WARN src/a.py" in r.stdout, r.stdout + r.stderr


# --- nesting: an umbrella doc root at the top, a package doc root inside it --------------

def nested(mono):
    top = doc_root(mono, "", "umbrella",
                   maps='[[map]]\npaths = ["**/*.py"]\npages = ["docs/architecture.md"]\n')
    pkg = doc_root(mono, "packages/a", "pkg-a")
    write(mono, "tools/t.py", "t = 1\n")
    write(pkg, "src/b.py", "b = 1\n")
    write(pkg, "README.md", "# Package A\n")
    commit_all(mono)
    return top, pkg


def test_nested_root_files_are_outside_the_outer_territory(mono):
    top, pkg = nested(mono)
    write(pkg, "src/b.py", "b = 2\n")
    write(mono, "tools/t.py", "t = 2\n")
    cfg = pmdocs.load_config(top)
    assert pmdocs.changed_files(top, staged=False, nested=cfg.nested) == {"tools/t.py"}
    assert [f.where for f in pmdocs.staleness(cfg, pmdocs.changed_files(top, False, cfg.nested))] == ["tools/t.py"]


def test_nested_root_is_discovered(mono):
    top, pkg = nested(mono)
    assert pmdocs.load_config(top).nested == ["packages/a"]
    assert pmdocs.load_config(pkg).nested == []


def test_coverage_and_extras_skip_the_nested_tree(mono):
    top, pkg = nested(mono)
    write(top, "docs/pmdocs.toml", '[site]\ntitle = "umbrella"\nreadme = false\nextra = ["**/README.md"]\n\n'
                                   '[coverage]\ninclude = ["**/*.py"]\n')
    write(mono, "README.md", "# Umbrella\n")
    git(mono, "add", "-A")
    cfg = pmdocs.load_config(top)
    assert [f.where for f in pmdocs.coverage(cfg)] == ["tools/t.py"]
    assert pmdocs.extra_files(cfg) == ["README.md"]


def test_inner_root_sees_only_its_own_tree(mono):
    top, pkg = nested(mono)
    write(pkg, "src/b.py", "b = 2\n")
    write(mono, "tools/t.py", "t = 2\n")
    assert pmdocs.changed_files(pkg, staged=False) == {"src/b.py"}


# --- the pre-commit hook in a subfolder, and the dispatcher -----------------------------

def staged(repo):
    return set(git(repo, "diff", "--cached", "--name-only").split())


def test_pre_commit_in_a_subfolder_builds_and_stages_its_site(mono, capsys):
    foo = doc_root(mono, "apps/foo", "foo")
    git(mono, "add", "-A")
    assert pmdocs.hook_pre_commit(foo) == 0, capsys.readouterr().err
    assert {"apps/foo/docs/site/index.html", "apps/foo/docs/roadmap.md"} <= staged(mono)


def test_pre_commit_in_a_subfolder_blocks_on_its_errors(mono, capsys):
    foo = doc_root(mono, "apps/foo", "foo")
    write(foo, "docs/broken.md", "# no frontmatter\n")
    git(mono, "add", "-A")
    assert pmdocs.hook_pre_commit(foo) == pmdocs.BLOCK_EXIT
    assert "docs/broken.md: missing frontmatter" in capsys.readouterr().err


from test_pre_commit import PY, fake_uv, needs_sh  # noqa: E402  (shared sh-hook helpers)


def commit(repo, env, *paths):
    return subprocess.run(["git", "commit", "-q", "-m", "x", *paths], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", env=env)


def two_siblings(mono, tmp_path):
    foo, bar = doc_root(mono, "apps/foo", "foo"), doc_root(mono, "apps/bar", "bar")
    vendor(foo)
    vendor(bar)
    git(mono, "add", "-A")
    pmdocs.install_hooks(foo)
    pmdocs.install_hooks(bar)
    return foo, bar, fake_uv(tmp_path, f'shift; shift; exec "{PY}" "$@"')


@needs_sh
def test_dispatcher_runs_every_affected_doc_root(mono, tmp_path):
    foo, bar, env = two_siblings(mono, tmp_path)
    r = commit(mono, env)
    assert r.returncode == 0, r.stderr
    names = git(mono, "show", "--name-only", "--format=", "HEAD").split()
    assert "apps/foo/docs/site/index.html" in names and "apps/bar/docs/site/index.html" in names


@needs_sh
def test_dispatcher_blocks_on_any_doc_root(mono, tmp_path):
    foo, bar, env = two_siblings(mono, tmp_path)
    assert commit(mono, env).returncode == 0
    write(bar, "docs/broken.md", "# no frontmatter\n")
    git(mono, "add", "-A")
    r = commit(mono, env)
    assert r.returncode != 0 and "missing frontmatter" in r.stderr


@needs_sh
def test_dispatcher_skips_untouched_doc_roots(mono, tmp_path):
    foo, bar, env = two_siblings(mono, tmp_path)
    assert commit(mono, env).returncode == 0
    write(foo, "docs/architecture.md", ARCH + "\nMore.\n")
    git(mono, "add", "-A")
    assert commit(mono, env).returncode == 0
    names = git(mono, "show", "--name-only", "--format=", "HEAD").split()
    assert "apps/foo/docs/site/architecture.html" in names
    assert not any(n.startswith("apps/bar/") for n in names)


@needs_sh
def test_dispatcher_with_nested_roots(mono, tmp_path):
    top, pkg = nested(mono)
    vendor(top)
    vendor(pkg)
    git(mono, "add", "-A")
    pmdocs.install_hooks(top)
    pmdocs.install_hooks(pkg)
    env = fake_uv(tmp_path, f'shift; shift; exec "{PY}" "$@"')
    assert commit(mono, env).returncode == 0
    write(pkg, "docs/broken.md", "# no frontmatter\n")   # the package's error, not the umbrella's
    git(mono, "add", "-A")
    r = commit(mono, env)
    assert r.returncode != 0 and "docs/broken.md: missing frontmatter" in r.stderr
    assert "umbrella" not in r.stderr or "docs/broken.md" not in r.stderr.split("umbrella")[0]


@needs_sh
def test_dispatcher_checks_a_doc_root_with_a_non_ascii_path(mono, tmp_path):
    # review finding: with core.quotePath on, `ls-files` printed "apps/caf\303\251/…",
    # the dispatcher's `case` didn't match, and the root was silently never checked
    foo = doc_root(mono, "apps/foo", "foo")
    cafe = doc_root(mono, "apps/café", "café")
    vendor(foo)
    vendor(cafe)
    git(mono, "add", "-A")
    pmdocs.install_hooks(foo)
    git(mono, "add", "-A")  # install-hooks wrote .claude/settings.json
    env = fake_uv(tmp_path, f'shift; shift; exec "{PY}" "$@"')
    assert commit(mono, env).returncode == 0
    # café's site was built and committed (checked without decoding git's path output,
    # whose encoding varies by platform)
    assert (cafe / "docs" / "site" / "index.html").is_file()
    assert git(mono, "status", "--porcelain") == ""
    write(cafe, "docs/broken.md", "# no frontmatter\n")
    git(mono, "add", "-A")
    r = commit(mono, env)
    assert r.returncode != 0 and "missing frontmatter" in r.stderr


def test_nested_root_inside_the_outer_docs_folder_is_not_outer_pages(mono):
    # review finding: doc_files and the asset walk ignored the territory
    top = doc_root(mono, "", "umbrella")
    sub = doc_root(mono, "docs/sub", "sub")
    write(sub, "docs/broken.md", "# no frontmatter\n")   # the inner root's problem only
    (sub / "docs" / "pic.png").write_bytes(b"PNG")
    cfg = pmdocs.load_config(top)
    assert cfg.nested == ["docs/sub"]
    model = pmdocs.load_model(cfg)
    assert not any(rel.startswith("docs/sub/") for rel in model.pages)
    assert [f for f in pmdocs.validate(model) if f.level == "ERROR"] == []
    pmdocs.build(cfg)
    assert not (top / "docs/site/sub").exists()


# --- install-hooks ---------------------------------------------------------------------

def test_install_names_the_doc_root_to_update_when_its_hook_predates_the_dispatcher(mono):
    # review finding: a 0.3.x root at the top + a new 0.4.0 root gave advice to hand-edit
    # a vendored hook; the right action is to update the old doc root first
    top = doc_root(mono, "", "umbrella")
    vendor(top)
    old_hook = top / "scripts" / "hooks" / "pre-commit"
    old_hook.write_text("#!/bin/sh\n# pmdocs pre-commit hook — vendored from pm-framework; do not edit.\n"
                        "uv run --quiet scripts/pmdocs.py hook pre-commit\n", encoding="utf-8")
    git(mono, "config", "core.hooksPath", "scripts/hooks")
    pkg = doc_root(mono, "packages/a", "pkg-a")
    vendor(pkg)
    git(mono, "add", "-A")
    with pytest.raises(pmdocs.PmdocsError, match=r"(?i)update the doc root at \. to pmdocs 0\.4"):
        pmdocs.install_hooks(pkg)


def test_install_warns_when_its_own_hook_predates_the_dispatcher(repo):
    from test_install_hooks import vendored
    vendored(repo)
    (repo / "scripts/hooks/pre-commit").write_text(
        "#!/bin/sh\n# pmdocs pre-commit hook — vendored from pm-framework; do not edit.\n", encoding="utf-8")
    msgs = pmdocs.install_hooks(repo)
    assert any("predates" in m and "scripts/hooks/pre-commit" in m for m in msgs)

def test_install_hooks_from_a_subfolder(mono):
    foo = doc_root(mono, "apps/foo", "foo")
    vendor(foo)
    git(mono, "add", "-A")
    msgs = pmdocs.install_hooks(foo)
    assert git(mono, "config", "--get", "core.hooksPath").strip() == "apps/foo/scripts/hooks"
    import json
    data = json.loads((mono / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmds = [h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]]
    assert cmds == ['uv run --quiet "$(git rev-parse --show-toplevel)/apps/foo/scripts/pmdocs.py" hook stop']
    assert any("core.hooksPath -> apps/foo/scripts/hooks" in m for m in msgs)


def test_second_doc_root_reuses_the_dispatcher(mono):
    foo, bar = doc_root(mono, "apps/foo", "foo"), doc_root(mono, "apps/bar", "bar")
    vendor(foo)
    vendor(bar)
    git(mono, "add", "-A")
    pmdocs.install_hooks(foo)
    msgs = pmdocs.install_hooks(bar)
    assert git(mono, "config", "--get", "core.hooksPath").strip() == "apps/foo/scripts/hooks"
    assert any("dispatches to every doc root" in m for m in msgs)
    import json
    data = json.loads((mono / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmds = [h["command"] for g in data["hooks"]["SessionStart"] for h in g["hooks"]]
    assert len(cmds) == 2 and any("/apps/bar/scripts/pmdocs.py" in c for c in cmds)
    status = pmdocs.hooks_status(bar)
    assert any("apps/bar" in line and "apps/foo" in line for line in status if line.startswith("pre-commit covers"))


def test_install_hooks_rewrites_old_claude_commands(repo):
    from test_install_hooks import vendored
    import json
    vendored(repo)
    old = {"hooks": {"Stop": [{"hooks": [{"type": "command",
           "command": 'uv run --quiet "$CLAUDE_PROJECT_DIR/scripts/pmdocs.py" hook stop'}]}]}}
    write(repo, ".claude/settings.json", json.dumps(old))
    pmdocs.install_hooks(repo)
    data = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert [h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]] == [
        'uv run --quiet "$(git rev-parse --show-toplevel)/scripts/pmdocs.py" hook stop']


# --- Claude Code hooks via the vendored copy -------------------------------------------

def run_vendored(root, cwd, *args, payload=None):
    import json
    return subprocess.run([sys.executable, str(root / "scripts" / "pmdocs.py"), *args], cwd=cwd,
                          input=json.dumps(payload or {"cwd": str(cwd)}), capture_output=True,
                          text=True, encoding="utf-8")


def test_post_edit_is_scoped_to_its_doc_root(mono):
    import json
    foo, bar = doc_root(mono, "apps/foo", "foo"), doc_root(mono, "apps/bar", "bar")
    vendor(foo)
    payload = lambda p: {"cwd": str(mono), "tool_input": {"file_path": str(p)}}
    inside = run_vendored(foo, mono, "hook", "post-edit", payload=payload(foo / "src" / "a.py"))
    assert "src/a.py is documented in docs/architecture.md" in json.loads(inside.stdout)["hookSpecificOutput"]["additionalContext"]
    outside = run_vendored(foo, mono, "hook", "post-edit", payload=payload(bar / "src" / "a.py"))
    assert outside.stdout == ""


def test_stop_and_session_start_name_the_project_when_there_are_several(mono):
    import json
    foo, bar = doc_root(mono, "apps/foo", "foo"), doc_root(mono, "apps/bar", "bar")
    vendor(foo)
    write(foo, "TODO.md", "- an idea\n")
    commit_all(mono)
    write(foo, "src/a.py", "x = 1\n")
    stop = json.loads(run_vendored(foo, mono, "hook", "stop").stdout)
    assert stop["systemMessage"].startswith("pmdocs [foo]:")
    start = json.loads(run_vendored(foo, mono, "hook", "session-start").stdout)
    assert "[foo]" in start["hookSpecificOutput"]["additionalContext"]


def test_single_root_messages_are_unprefixed(repo):
    import json
    vendor(repo)
    write(repo, "TODO.md", "- an idea\n")
    stop = json.loads(run_vendored(repo, repo, "hook", "stop").stdout)
    assert stop["systemMessage"].startswith("pmdocs: ")
