import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tool" / "pmdocs.py"
HOOK = REPO / "tool" / "hooks" / "pre-commit"


def git(repo, *args, input=None, env=None):
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                       encoding="utf-8", input=input, env=e)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout


def write(repo, rel, text):
    p = Path(repo) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def commit_all(repo, msg="c", env=None):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg, env=env)


def run_cli(cwd, *args, input=None, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, str(TOOL), *args], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", input=input, env=e)


def has(findings, level, text):
    return any(f.level == level and text in f.msg for f in findings)
