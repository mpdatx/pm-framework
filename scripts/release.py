"""Cut a release: tag v<VERSION> on master and fast-forward the release worktree to it.

    uv run scripts/release.py            # check, tag, publish
    uv run scripts/release.py --dry-run  # checks only

The installed skill links to the release worktree (.release/, gitignored), so other
projects' init/adopt/update only ever copy a tagged, tested version — never work in
progress on master. Refuses unless: on master, the tree is clean, the vendored copies
match tool/ (sync_assets), VERSION is higher than the last release tag, and the tests pass.
"""
import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV_BRANCH = "master"
RELEASE_BRANCH = "release"
RELEASE_DIR = ".release"
VERSION_RE = re.compile(r'^VERSION = "(\d+)\.(\d+)\.(\d+)"$', re.M)
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


class ReleaseError(Exception):
    pass


def git(root: Path, *args) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def read_version(root: Path) -> tuple:
    m = VERSION_RE.search((root / "tool" / "pmdocs.py").read_text(encoding="utf-8"))
    if not m:
        raise ReleaseError("no VERSION line found in tool/pmdocs.py")
    return tuple(int(x) for x in m.groups())


def latest_release(root: Path):
    versions = [tuple(int(x) for x in m.groups())
                for t in git(root, "tag", "--list", "v*").split() if (m := TAG_RE.match(t))]
    return max(versions) if versions else None


def assets_in_sync(root: Path) -> list:
    spec = importlib.util.spec_from_file_location("sync_assets", root / "scripts" / "sync_assets.py")
    mod = importlib.util.module_from_spec(spec)
    dont_write = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # a __pycache__ here would dirty the tree being checked
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = dont_write
    return mod.sync(check=True)


def run_tests(root: Path) -> bool:
    return subprocess.run(["uv", "run", "pytest", "-q"], cwd=root).returncode == 0


def release(root: Path, run_tests=run_tests, dry_run: bool = False) -> str:
    root = Path(root)
    branch = git(root, "branch", "--show-current").strip()
    if branch != DEV_BRANCH:
        raise ReleaseError(f"releases are cut from {DEV_BRANCH}; you are on {branch or 'a detached HEAD'}")
    if git(root, "status", "--porcelain").strip():
        raise ReleaseError("the tree has uncommitted changes; commit or stash them first")
    stale = assets_in_sync(root)
    if stale:
        raise ReleaseError(f"vendored copies differ from tool/: {', '.join(stale)}; run scripts/sync_assets.py")
    version, last = read_version(root), latest_release(root)
    tag = "v" + ".".join(map(str, version))
    if last is not None and version <= last:
        raise ReleaseError(f"VERSION {tag[1:]} is not higher than the last release v{'.'.join(map(str, last))}; "
                           "bump VERSION in tool/pmdocs.py")
    if not run_tests(root):
        raise ReleaseError("the tests failed; nothing was released")
    if dry_run:
        return tag
    git(root, "tag", "-a", tag, "-m", f"pmdocs {tag[1:]}")
    worktree = root / RELEASE_DIR
    if not worktree.exists():
        if git(root, "branch", "--list", RELEASE_BRANCH).strip():
            git(root, "worktree", "add", RELEASE_DIR, RELEASE_BRANCH)
        else:
            git(root, "worktree", "add", "-b", RELEASE_BRANCH, RELEASE_DIR, tag)
    # Releases only ever move forward along master, so this is always a fast-forward.
    git(worktree, "merge", "--ff-only", "-q", tag)
    return tag


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="run the checks, change nothing")
    args = p.parse_args()
    try:
        tag = release(ROOT, dry_run=args.dry_run)
    except ReleaseError as e:
        print(f"release: {e}", file=sys.stderr)
        return 1
    print(f"release: {tag} {'would be released' if args.dry_run else f'released to {RELEASE_DIR}/'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
