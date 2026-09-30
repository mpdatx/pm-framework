import pytest

from helpers import git, write

MIN_CONFIG = '[site]\ntitle = "demo"\n'
INDEX = "---\ntitle: Demo\nsummary: Demo project.\norder: 1\n---\n\n# Demo\n\nHello.\n"


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "demo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    for key, value in [("user.email", "t@example.com"), ("user.name", "Test"),
                       ("core.autocrlf", "false"), ("commit.gpgsign", "false")]:
        git(r, "config", key, value)
    write(r, "docs/pmdocs.toml", MIN_CONFIG)
    write(r, "docs/index.md", INDEX)
    return r
