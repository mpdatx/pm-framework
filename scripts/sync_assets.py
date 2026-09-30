"""Copy the tool and git hook from tool/ into the skill's assets and into this repo's scripts/.

The skill vendors assets/ into adopting projects; this repo dogfoods its own copy in
scripts/. Run after every change to tool/: `uv run scripts/sync_assets.py`.
`--check` exits 1 if any copy differs (the test suite runs the same check).
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = [
    ("tool/pmdocs.py", "skill/project-docs/assets/pmdocs.py"),
    ("tool/hooks/pre-commit", "skill/project-docs/assets/hooks/pre-commit"),
    ("tool/pmdocs.py", "scripts/pmdocs.py"),
    ("tool/hooks/pre-commit", "scripts/hooks/pre-commit"),
]


def sync(check: bool) -> list:
    stale = []
    for src, dst in PAIRS:
        s, d = ROOT / src, ROOT / dst
        if d.is_file() and d.read_bytes() == s.read_bytes():
            continue
        stale.append(dst)
        if not check:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(s, d)
    return stale


if __name__ == "__main__":
    check = "--check" in sys.argv[1:]
    stale = sync(check)
    for path in stale:
        print(("stale: " if check else "updated: ") + path)
    sys.exit(1 if check and stale else 0)
