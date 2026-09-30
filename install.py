"""Install the project-docs skill into ~/.claude/skills/project-docs.

    uv run install.py              # link the latest release (.release/, made by scripts/release.py)
    uv run install.py --dev        # link this working tree instead: edits are live immediately
    uv run install.py --copy       # plain copy (re-run to refresh)
    uv run install.py --uninstall
    uv run install.py --dest PATH  # somewhere else

Links are symlinks on Linux/macOS and junctions on Windows without symlink privilege.
Standard library only. Linking the release (the default) means other projects only ever
vendor tagged, tested versions — never work in progress on master.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
DEV_SRC = REPO / "skill" / "project-docs"
RELEASE_SRC = REPO / ".release" / "skill" / "project-docs"  # kept current by scripts/release.py
COPY_MARK = ".installed-copy"


def default_dest() -> Path:
    return Path.home() / ".claude" / "skills" / "project-docs"


def is_link(p: Path) -> bool:
    if p.is_symlink():
        return True
    is_junction = getattr(p, "is_junction", None)  # Python 3.12+
    if is_junction is not None:
        return is_junction()
    try:
        os.readlink(p)  # junctions are readable as links on Windows
        return True
    except (OSError, ValueError):
        return False


def _remove_link(p: Path) -> None:
    if p.is_symlink() and not p.is_dir():
        p.unlink()
    else:
        try:
            p.unlink()  # directory symlink on POSIX
        except (IsADirectoryError, PermissionError, OSError):
            os.rmdir(p)  # Windows junction or directory symlink


def _link(src: Path, dest: Path) -> str:
    try:
        os.symlink(src, dest, target_is_directory=True)
        return "symlink"
    except OSError:
        if os.name != "nt":
            raise
    # A junction needs no privilege. Create it through the Win32 API rather than
    # `cmd /c mklink`, so no shell ever parses the path (&, ^, % are legal in paths).
    import _winapi
    _winapi.CreateJunction(str(src), str(dest))
    return "junction"


def maintainer_clone(repo: Path) -> bool:
    """True where releases are cut: a local `release` branch exists. Only release.py creates
    it and it is never pushed, so a user's clone of the published repository — whose
    checkout is already a released version — never has one. Version tags are NOT a signal:
    they are published, and arrive with every clone."""
    try:
        r = subprocess.run(["git", "branch", "--list", "release"], cwd=repo,
                           capture_output=True, text=True)
    except OSError:  # no git, or repo missing
        return False
    return r.returncode == 0 and bool(r.stdout.strip())


def install(dest: Path, copy: bool = False, dev: bool = False) -> str:
    dest = Path(dest)
    if dev:
        src, label = DEV_SRC, "dev working tree"
    elif (RELEASE_SRC / "SKILL.md").is_file():
        src, label = RELEASE_SRC, "release"
    elif not maintainer_clone(REPO):
        src, label = DEV_SRC, "checkout"  # a published clone: the checkout is the release
    else:
        sys.exit(f"no release at {RELEASE_SRC.parent.parent}: run `uv run scripts/release.py` first "
                 "(or `install.py --dev` to link the working tree)")
    if dest.exists() or dest.is_symlink():
        if is_link(dest):
            _remove_link(dest)
        elif (dest / COPY_MARK).is_file():
            shutil.rmtree(dest)
        else:
            sys.exit(f"refusing to replace {dest}: it is not a link or a copy made by this installer")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        shutil.copytree(src, dest)
        (dest / COPY_MARK).write_text("installed by pm-framework/install.py\n", encoding="utf-8")
        kind = "copy"
    else:
        kind = _link(src, dest)
    return f"installed project-docs ({label}, {kind}) at {dest}"


def uninstall(dest: Path) -> str:
    dest = Path(dest)
    if is_link(dest):
        _remove_link(dest)
    elif (dest / COPY_MARK).is_file():
        shutil.rmtree(dest)
    elif dest.exists():
        sys.exit(f"refusing to remove {dest}: it was not installed by this installer")
    else:
        return f"nothing installed at {dest}"
    return f"removed {dest}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--copy", action="store_true", help="copy instead of linking")
    p.add_argument("--dev", action="store_true", help="use this working tree, not the release")
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--dest", type=Path, default=default_dest())
    args = p.parse_args()
    print(uninstall(args.dest) if args.uninstall else install(args.dest, args.copy, args.dev))


if __name__ == "__main__":
    main()
