import importlib.util
import shutil

import pmdocs
from helpers import REPO, git, has, write

SKILL = REPO / "skill" / "project-docs"
TEMPLATES = SKILL / "assets" / "templates"


def load_sync():
    spec = importlib.util.spec_from_file_location("sync_assets", REPO / "scripts" / "sync_assets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_assets_in_sync():
    assert load_sync().sync(check=True) == []


def test_vendored_files_are_lf():
    for rel in ("assets/pmdocs.py", "assets/hooks/pre-commit"):
        assert b"\r" not in (SKILL / rel).read_bytes(), rel


def test_skill_frontmatter():
    meta, body, err = pmdocs.split_frontmatter(pmdocs.read_text(SKILL / "SKILL.md"))
    assert err is None
    assert meta["name"] == "project-docs"
    assert meta["description"].startswith("Use when") and len(meta["description"]) <= 1024
    for heading in ("## init", "## adopt", "## triage", "## update", "## Everyday duties"):
        assert heading in body


def test_adopt_creates_config_and_doc_map_before_installing_hooks():
    # install-hooks, build and check all need docs/pmdocs.toml; adopt must create it (init
    # step 4) and write the doc-map (init step 6) before running init step 8.
    body = pmdocs.read_text(SKILL / "SKILL.md")
    adopt = body.split("## adopt", 1)[1].split("\n## ", 1)[0]
    assert "Run init steps 2, 3, 4, 6, 7 and 8" in adopt


def test_init_and_adopt_surface_markdown_outside_docs():
    body = pmdocs.read_text(SKILL / "SKILL.md")
    for workflow in ("## init", "## adopt"):
        section = body.split(workflow, 1)[1].split("\n## ", 1)[0]
        assert "outside `docs/`" in section and "[[site.extra]]" in section, workflow


def test_templates_pass_check(tmp_path):
    repo = tmp_path / "newproj"
    (repo / "docs").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    for name in ("index.md", "product.md", "architecture.md", "decisions.md", "backlog.md", "backlog-archive.md"):
        shutil.copyfile(TEMPLATES / name, repo / "docs" / name)
    shutil.copyfile(TEMPLATES / "TODO.md", repo / "TODO.md")
    write(repo, "docs/pmdocs.toml", (TEMPLATES / "pmdocs.toml").read_text(encoding="utf-8").replace("PROJECT", "newproj"))
    write(repo, "src/a.py", "x = 1\n")
    model = pmdocs.load_model(pmdocs.load_config(repo))
    findings = pmdocs.doc_findings(model)
    assert [f for f in findings if f.level == "ERROR"] == []
    assert has(findings, "WARN", "pmdocs:fill")
    assert model.inbox == 0
    assert pmdocs.build(pmdocs.load_config(repo))  # renders without error


def test_snippet_and_gitattributes_exist():
    snippet = (SKILL / "assets" / "claude-md-snippet.md").read_text(encoding="utf-8")
    assert "TODO.md" in snippet and "same commit" in snippet
    attrs = (SKILL / "assets" / "gitattributes").read_text(encoding="utf-8")
    for line in ("docs/site/**/*.html text eol=lf", "docs/roadmap.md text eol=lf",
                 "scripts/pmdocs.py text eol=lf", "scripts/hooks/* text eol=lf"):
        assert line in attrs
