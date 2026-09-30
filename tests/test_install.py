import importlib.util

import pytest

from helpers import REPO, git


def load():
    spec = importlib.util.spec_from_file_location("install", REPO / "install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_link_install_and_reinstall(tmp_path):
    inst = load()
    dest = tmp_path / "skills" / "project-docs"
    inst.install(dest, dev=True)
    assert inst.is_link(dest)
    assert (dest / "SKILL.md").read_bytes() == (inst.DEV_SRC / "SKILL.md").read_bytes()
    inst.install(dest, dev=True)  # idempotent
    assert inst.is_link(dest)


def test_copy_install_and_uninstall(tmp_path):
    inst = load()
    dest = tmp_path / "project-docs"
    inst.install(dest, copy=True, dev=True)
    assert not inst.is_link(dest) and (dest / ".installed-copy").is_file()
    assert (dest / "assets" / "pmdocs.py").is_file()
    inst.install(dest, copy=True, dev=True)  # refreshes the copy
    inst.uninstall(dest)
    assert not dest.exists()


def test_refuses_foreign_directory(tmp_path):
    inst = load()
    dest = tmp_path / "project-docs"
    dest.mkdir()
    (dest / "mine.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        inst.install(dest, dev=True)
    with pytest.raises(SystemExit):
        inst.uninstall(dest)
    assert (dest / "mine.txt").exists()


def test_uninstall_link_keeps_source(tmp_path):
    inst = load()
    dest = tmp_path / "project-docs"
    inst.install(dest, dev=True)
    inst.uninstall(dest)
    assert not dest.exists() and (inst.DEV_SRC / "SKILL.md").is_file()


@pytest.mark.skipif(__import__("os").name != "nt", reason="junction fallback is Windows-only")
def test_junction_fallback_when_symlinks_are_denied(tmp_path, monkeypatch):
    inst = load()

    def denied(*args, **kwargs):
        raise OSError("symlink privilege not held")

    monkeypatch.setattr(inst.os, "symlink", denied)
    dest = tmp_path / "project-docs"
    assert ", junction)" in inst.install(dest, dev=True)
    assert inst.is_link(dest) and (dest / "SKILL.md").is_file()
    inst.uninstall(dest)
    assert not dest.exists() and (inst.DEV_SRC / "SKILL.md").is_file()


@pytest.mark.skipif(__import__("os").name != "nt", reason="junction fallback is Windows-only")
def test_junction_fallback_with_shell_metacharacters_in_path(tmp_path, monkeypatch):
    inst = load()

    def denied(*args, **kwargs):
        raise OSError("symlink privilege not held")

    monkeypatch.setattr(inst.os, "symlink", denied)
    dest = tmp_path / "a&b^c%PATH%" / "project-docs"
    assert ", junction)" in inst.install(dest, dev=True)
    assert (dest / "SKILL.md").is_file()
    inst.uninstall(dest)
    assert not dest.exists()


def test_default_install_links_the_release_worktree(tmp_path, monkeypatch):
    inst = load()
    released = tmp_path / "release" / "skill" / "project-docs"
    released.mkdir(parents=True)
    (released / "SKILL.md").write_text("released\n", encoding="utf-8")
    monkeypatch.setattr(inst, "RELEASE_SRC", released)
    dest = tmp_path / "project-docs"
    assert "(release," in inst.install(dest)
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == "released\n"


def test_default_install_without_a_release_explains(tmp_path, monkeypatch):
    inst = load()
    monkeypatch.setattr(inst, "RELEASE_SRC", tmp_path / "nope")
    monkeypatch.setattr(inst, "maintainer_clone", lambda repo: True)
    with pytest.raises(SystemExit, match="scripts/release.py"):
        inst.install(tmp_path / "project-docs")


def test_fresh_clone_without_release_links_the_checkout(tmp_path, monkeypatch):
    # a user's clone of the public repo: no .release/, no release branch, no v* tags —
    # the checkout itself is the published version
    inst = load()
    monkeypatch.setattr(inst, "RELEASE_SRC", tmp_path / "nope")
    monkeypatch.setattr(inst, "maintainer_clone", lambda repo: False)
    dest = tmp_path / "project-docs"
    msg = inst.install(dest)
    assert "(checkout," in msg
    assert (dest / "SKILL.md").read_bytes() == (inst.DEV_SRC / "SKILL.md").read_bytes()


def test_maintainer_clone_detection(tmp_path):
    inst = load()
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "master")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "T")
    (r / "a").write_text("a", encoding="utf-8")
    git(r, "add", "a")
    git(r, "commit", "-q", "-m", "c")
    assert inst.maintainer_clone(r) is False
    git(r, "tag", "v0.1.0")
    assert inst.maintainer_clone(r) is True
    git(r, "tag", "-d", "v0.1.0")
    git(r, "branch", "release")
    assert inst.maintainer_clone(r) is True
    assert inst.maintainer_clone(tmp_path / "not-a-repo") is False


def test_dev_install_says_so(tmp_path):
    inst = load()
    assert "(dev" in inst.install(tmp_path / "project-docs", dev=True)


def test_default_dest():
    inst = load()
    assert inst.default_dest().parts[-3:] == (".claude", "skills", "project-docs")
