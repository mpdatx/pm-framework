import pmdocs
from helpers import TOOL, run_cli


def test_version_cli(tmp_path):
    r = run_cli(tmp_path, "version")
    assert r.returncode == 0
    assert r.stdout == f"pmdocs {pmdocs.VERSION}\n"


def test_header_marks_file_as_vendored():
    head = TOOL.read_text(encoding="utf-8")[:600]
    assert "# /// script" in head
    assert "vendored from pm-framework; do not edit" in head


def test_pmdocs_error_exits_2(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def boom(args):
        raise pmdocs.PmdocsError("nope")

    monkeypatch.setitem(pmdocs.__dict__, "cmd_version", boom)
    assert pmdocs.main(["version"]) == 2


def test_unexpected_exception_exits_2(tmp_path, monkeypatch):
    def boom(args):
        raise RuntimeError("bug")

    monkeypatch.setitem(pmdocs.__dict__, "cmd_version", boom)
    assert pmdocs.main(["version"]) == 2
