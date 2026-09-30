import json

import pytest

import pmdocs
from helpers import HOOK, git, run_cli, write


def vendored(repo):
    hook = repo / "scripts" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_bytes(HOOK.read_bytes())
    return repo


def settings(repo):
    return json.loads((repo / ".claude/settings.json").read_text(encoding="utf-8"))


def commands(data, event):
    return [h["command"] for g in data.get("hooks", {}).get(event, []) for h in g["hooks"]]


def test_install_fresh(repo):
    msgs = pmdocs.install_hooks(vendored(repo))
    assert git(repo, "config", "--get", "core.hooksPath").strip() == "scripts/hooks"
    assert git(repo, "ls-files", "-s", "scripts/hooks/pre-commit").startswith("100755")
    data = settings(repo)
    assert data["hooks"]["PostToolUse"][0]["matcher"] == "Edit|Write|MultiEdit"
    assert any("hook post-edit" in c for c in commands(data, "PostToolUse"))
    assert any("hook stop" in c for c in commands(data, "Stop"))
    assert any("core.hooksPath" in m for m in msgs)


def test_install_is_idempotent(repo):
    vendored(repo)
    pmdocs.install_hooks(repo)
    pmdocs.install_hooks(repo)
    data = settings(repo)
    assert len(commands(data, "PostToolUse")) == 1 and len(commands(data, "Stop")) == 1


def test_install_preserves_existing_settings(repo):
    vendored(repo)
    existing = {"permissions": {"allow": ["Bash(ls)"]},
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
    write(repo, ".claude/settings.json", json.dumps(existing))
    pmdocs.install_hooks(repo)
    data = settings(repo)
    assert data["permissions"] == {"allow": ["Bash(ls)"]}
    assert "echo mine" in commands(data, "Stop") and len(commands(data, "Stop")) == 2


def test_install_treats_empty_settings_file_as_empty(repo):
    vendored(repo)
    write(repo, ".claude/settings.json", "  \n")
    pmdocs.install_hooks(repo)
    assert any("hook stop" in c for c in commands(settings(repo), "Stop"))


def test_install_still_refuses_malformed_settings(repo):
    vendored(repo)
    write(repo, ".claude/settings.json", "{not json")
    with pytest.raises(pmdocs.PmdocsError, match="not valid JSON"):
        pmdocs.install_hooks(repo)


def test_install_warns_when_settings_are_gitignored(repo):
    vendored(repo)
    write(repo, ".gitignore", ".claude/\n")
    msgs = pmdocs.install_hooks(repo)
    assert any("gitignored" in m and ".claude/settings.json" in m for m in msgs)
    assert any("gitignored" in line for line in pmdocs.hooks_status(repo))


def test_no_warning_when_settings_are_re_included(repo):
    # `.claude/*` + `!.claude/settings.json` shares the file; `check-ignore -v` would still
    # print the negation pattern, so only the exit status of `check-ignore -q` is trusted
    vendored(repo)
    write(repo, ".gitignore", ".claude/*\n!.claude/settings.json\n")
    msgs = pmdocs.install_hooks(repo)
    assert not any("gitignored" in m for m in msgs)
    assert not any("gitignored" in line for line in pmdocs.hooks_status(repo))


def test_refuses_other_hooks_path(repo):
    vendored(repo)
    git(repo, "config", "core.hooksPath", ".githooks")
    with pytest.raises(pmdocs.PmdocsError, match="core.hooksPath is already"):
        pmdocs.install_hooks(repo)


def test_refuses_active_git_hooks(repo):
    vendored(repo)
    (repo / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    with pytest.raises(pmdocs.PmdocsError, match="active hooks"):
        pmdocs.install_hooks(repo)


def test_requires_vendored_hook(repo):
    with pytest.raises(pmdocs.PmdocsError, match="pre-commit is missing"):
        pmdocs.install_hooks(repo)


def test_uninstall_reverses(repo):
    vendored(repo)
    write(repo, ".claude/settings.json", json.dumps({"permissions": {"allow": []}}))
    pmdocs.install_hooks(repo)
    pmdocs.uninstall_hooks(repo)
    r = run_cli(repo, "install-hooks", "--status")
    assert "core.hooksPath: (unset)" in r.stdout
    assert settings(repo) == {"permissions": {"allow": []}}


def test_status(repo):
    pmdocs.install_hooks(vendored(repo))
    lines = pmdocs.hooks_status(repo)
    assert "core.hooksPath: scripts/hooks" in lines
    assert "scripts/hooks/pre-commit: executable in git" in lines
    assert "Claude Code hooks: installed" in lines


def test_cli_install(repo):
    vendored(repo)
    r = run_cli(repo, "install-hooks")
    assert r.returncode == 0, r.stderr
    assert "core.hooksPath -> scripts/hooks" in r.stdout
