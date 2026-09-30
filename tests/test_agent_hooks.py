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


GATES = ("---\ntitle: Waiting on you\n---\n\n# Waiting on you\n\n"
         "## G04. Pass 8: does Dry/Wet alone explain it?\n"
         "Status: waiting · Asked: 2026-09-28 · Needs: Live running\n")
BACKLOG = ("---\ntitle: Backlog\n---\n\n# Backlog\n\n"
           "## B03. Decide the patch\nStatus: blocked · Added: 2026-09-27 · Gate: G04\n\n"
           "## B05. Capture drones\nStatus: in-progress · Added: 2026-09-27\n\n"
           "## B06. Someday\nStatus: open · Added: 2026-09-27\n")


def test_session_start_tells_the_agent_what_is_in_flight(repo):
    write(repo, "docs/gates.md", GATES)
    write(repo, "docs/backlog.md", BACKLOG)
    write(repo, "TODO.md", "- an idea\n")
    r = run_cli(repo, "hook", "session-start", input=json.dumps({"cwd": str(repo), "source": "startup"}))
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    ctx = out["additionalContext"]
    assert "G04 Pass 8: does Dry/Wet alone explain it? (needs: Live running; asked 2026-09-28)" in ctx
    assert "B05 Capture drones (in-progress)" in ctx and "B03 Decide the patch (blocked on G04)" in ctx
    assert "B06" not in ctx
    assert "1 inbox item(s) in TODO.md" in ctx
    assert "record their words" in ctx  # the duty travels with the list


def test_session_start_silent_when_nothing_is_in_flight(repo):
    r = run_cli(repo, "hook", "session-start", input=json.dumps({"cwd": str(repo)}))
    assert r.returncode == 0 and r.stdout == ""


def test_session_start_outside_project_is_silent(tmp_path):
    r = run_cli(tmp_path, "hook", "session-start", input="{}")
    assert r.returncode == 0 and r.stdout == ""


def test_stop_tells_the_user_about_waiting_gates(repo):
    write(repo, "docs/gates.md", GATES)
    commit_all(repo)
    out = json.loads(run_cli(repo, "hook", "stop", input=json.dumps({"cwd": str(repo)})).stdout)
    assert "1 gate(s) waiting on you" in out["systemMessage"]
    assert "hookSpecificOutput" not in out  # not re-invoking the agent over it


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
