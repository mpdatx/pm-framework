import json

from helpers import commit_all, run_cli, write
from test_drift import mapped


def post_edit(cwd, file_path, payload_cwd=None):
    payload = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Edit",
                          "cwd": str(payload_cwd or cwd), "tool_input": {"file_path": str(file_path)}})
    return run_cli(cwd, "hook", "post-edit", input=payload)


def test_post_edit_mapped(repo):
    mapped(repo)
    r = post_edit(repo, repo / "src" / "a.py")
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse"
    assert "src/a.py is documented in docs/architecture.md" in out["additionalContext"]


def test_post_edit_relative_path_from_subdir(repo):
    mapped(repo)
    (repo / "src").mkdir()
    r = post_edit(repo / "src", "a.py")
    assert "src/a.py is documented in" in r.stdout


def test_post_edit_unmapped_is_silent(repo):
    mapped(repo)
    r = post_edit(repo, repo / "README.md")
    assert r.returncode == 0 and r.stdout == ""


def test_post_edit_garbage_is_silent(repo):
    r = run_cli(repo, "hook", "post-edit", input="not json")
    assert r.returncode == 0 and r.stdout == ""


def test_post_edit_outside_project_is_silent(repo, tmp_path):
    r = post_edit(tmp_path, tmp_path / "elsewhere.py")
    assert r.returncode == 0 and r.stdout == ""


def test_stop_reports_stale_and_inbox(repo):
    mapped(repo)
    commit_all(repo)
    write(repo, "src/a.py", "1\n")
    write(repo, "TODO.md", "- x\n")
    r = run_cli(repo, "hook", "stop", input=json.dumps({"cwd": str(repo)}))
    assert r.returncode == 0
    out = json.loads(r.stdout)
    msg = out["systemMessage"]
    assert "src/a.py -> docs/architecture.md" in msg
    assert "1 inbox item(s) in TODO.md awaiting triage" in msg
    # the agent sees the stale pages (not the inbox count), once — and it never blocks
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "Stop"
    assert "src/a.py -> docs/architecture.md" in ctx and "inbox" not in ctx
    assert "decision" not in out


def test_stop_inbox_alone_is_shown_to_user_only(repo):
    # a non-empty inbox is not something the agent must act on; pushing it to the agent
    # would re-invoke it at every stop
    mapped(repo)
    commit_all(repo)
    write(repo, "TODO.md", "- x\n")
    out = json.loads(run_cli(repo, "hook", "stop", input=json.dumps({"cwd": str(repo)})).stdout)
    assert "1 inbox item(s)" in out["systemMessage"]
    assert "hookSpecificOutput" not in out


def test_stop_does_not_reinvoke_agent_when_already_continuing(repo):
    mapped(repo)
    commit_all(repo)
    write(repo, "src/a.py", "1\n")
    payload = json.dumps({"cwd": str(repo), "stop_hook_active": True})
    out = json.loads(run_cli(repo, "hook", "stop", input=payload).stdout)
    assert "src/a.py" in out["systemMessage"]
    assert "hookSpecificOutput" not in out


def test_stop_silent_when_clean(repo):
    mapped(repo)
    commit_all(repo)
    r = run_cli(repo, "hook", "stop", input=json.dumps({"cwd": str(repo)}))
    assert r.returncode == 0 and r.stdout == ""


def test_stop_empty_stdin_uses_cwd(repo):
    mapped(repo)
    commit_all(repo)
    write(repo, "src/a.py", "1\n")
    r = run_cli(repo, "hook", "stop", input="")
    assert "src/a.py" in json.loads(r.stdout)["systemMessage"]
