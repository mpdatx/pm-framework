import pytest

import pmdocs
from helpers import write


def test_norm_converts_backslashes_and_strips_dot():
    assert pmdocs.norm(".\\src\\a.py") == "src/a.py"
    assert pmdocs.norm("./docs/x.md") == "docs/x.md"


@pytest.mark.parametrize("path,pattern,ok", [
    ("src/a.py", "src/**", True),
    ("src/x/y/a.py", "src/**", True),
    ("src/a.py", "src/*.py", True),
    ("src/x/a.py", "src/*.py", False),
    ("a.py", "**/a.py", True),
    ("lib/x/a.py", "**/a.py", True),
    ("srcx/a.py", "src/**", False),
    ("src\\win\\a.py", "src/**", True),
    ("docs/a.md", "docs/?.md", True),
])
def test_glob_match(path, pattern, ok):
    assert pmdocs.glob_match(path, pattern) is ok


def test_find_root_walks_up(repo):
    sub = repo / "src" / "deep"
    sub.mkdir(parents=True)
    assert pmdocs.find_root(sub) == repo.resolve()


def test_find_root_missing(tmp_path):
    with pytest.raises(pmdocs.PmdocsError):
        pmdocs.find_root(tmp_path)


def test_load_config_defaults(repo):
    cfg = pmdocs.load_config(repo)
    assert cfg.title == "demo"
    assert cfg.specs == "docs/superpowers/specs"
    assert cfg.plans == "docs/superpowers/plans"
    assert cfg.maps == [] and cfg.exclude == []
    assert cfg.coverage_include == [] and cfg.coverage_exclude == []
    assert cfg.outside_root == repo


def test_load_config_normalizes_paths(repo):
    write(repo, "docs/pmdocs.toml",
          '[paths]\nexclude = ["docs\\\\course\\\\**"]\n\n'
          '[[map]]\npaths = ["src\\\\core\\\\**"]\npages = ["docs/architecture.md"]\n')
    cfg = pmdocs.load_config(repo)
    assert cfg.title == "demo"  # falls back to the directory name
    assert cfg.maps == [pmdocs.MapEntry(["src/core/**"], ["docs/architecture.md"])]
    assert cfg.exclude == ["docs/course/**"]


def test_load_config_invalid(repo):
    write(repo, "docs/pmdocs.toml", "[site\n")
    with pytest.raises(pmdocs.PmdocsError):
        pmdocs.load_config(repo)


def test_frontmatter_parsed_and_dates_stringified():
    meta, body, err = pmdocs.split_frontmatter("---\ntitle: X\ncreated: 2026-09-30\n---\n# X\n")
    assert err is None
    assert meta == {"title": "X", "created": "2026-09-30"}
    assert body == "# X\n"


def test_empty_frontmatter_block_is_frontmatter():
    assert pmdocs.split_frontmatter("---\n---\n# X\n") == ({}, "# X\n", None)


def test_frontmatter_absent():
    assert pmdocs.split_frontmatter("# X\n") == (None, "# X\n", None)


def test_frontmatter_invalid_yaml():
    meta, body, err = pmdocs.split_frontmatter("---\ntitle: [x\n---\nbody\n")
    assert meta is None and body == "body\n"
    assert "invalid YAML" in err


def test_frontmatter_not_a_mapping():
    meta, _, err = pmdocs.split_frontmatter("---\n- a\n---\n")
    assert meta is None and err == "frontmatter is not a mapping"


def test_read_text_normalizes_crlf_and_bom(tmp_path):
    p = tmp_path / "a.md"
    p.write_bytes("﻿---\r\ntitle: X\r\n---\r\nhi\r\n".encode("utf-8"))
    text = pmdocs.read_text(p)
    assert text == "---\ntitle: X\n---\nhi\n"
    assert pmdocs.split_frontmatter(text)[0] == {"title": "X"}


def test_write_text_uses_lf(tmp_path):
    p = tmp_path / "sub" / "a.txt"
    pmdocs.write_text(p, "a\nb\n")
    assert p.read_bytes() == b"a\nb\n"
