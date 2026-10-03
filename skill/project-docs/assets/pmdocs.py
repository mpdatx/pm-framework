# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown-it-py>=3.0", "pyyaml>=6.0"]
# ///
# SPDX-License-Identifier: MIT — Copyright (c) 2026 Matthew Daniels — https://github.com/mpdatx/pm-framework
"""pmdocs 0.4.0 — vendored from pm-framework; do not edit, re-run the project-docs skill to update.

Keeps a project's docs and work status current: renders docs/ to docs/site/, generates
docs/roadmap.md, validates frontmatter/backlog/links, detects drift and staleness, and
provides the git and Claude Code hook entry points. Run as `uv run scripts/pmdocs.py`.
"""
from __future__ import annotations

import argparse
import functools
import html
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from string import Template
from urllib.parse import quote, unquote

import yaml
from markdown_it import MarkdownIt

VERSION = "0.4.0"


class PmdocsError(Exception):
    """A problem the user must fix (bad config, not a repo). The CLI exits 2."""


# === core ===

CONFIG_REL = "docs/pmdocs.toml"


def norm(path: str) -> str:
    """Repo-relative POSIX form: forward slashes, no leading './'."""
    p = str(path).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


@functools.lru_cache(maxsize=None)
def _glob_regex(pattern: str) -> re.Pattern:
    pat, i, out = norm(pattern), 0, []
    while i < len(pat):
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif pat[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pat[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pat[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def glob_match(path: str, pattern: str) -> bool:
    """`*` stays within a directory, `**` crosses directories, `**/` may match nothing."""
    return _glob_regex(pattern).match(norm(path)) is not None


def any_match(path: str, patterns) -> bool:
    return any(glob_match(path, p) for p in patterns)


def read_text(path: Path) -> str:
    """UTF-8 with any BOM stripped and CRLF normalized, so Windows checkouts read the same."""
    return Path(path).read_text(encoding="utf-8").lstrip("\ufeff").replace("\r\n", "\n")


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def find_root(start: Path) -> Path:
    start = Path(start).resolve()
    for p in (start, *start.parents):
        if (p / CONFIG_REL).is_file():
            return p
    raise PmdocsError(f"no {CONFIG_REL} found in {start} or any parent")


def own_root():
    """The doc root this copy is vendored into (`<root>/scripts/pmdocs.py`), or None.
    Hooks run from the repo top (git) or wherever Claude was launched, so a vendored copy
    must not depend on the current directory to know which project it serves."""
    here = Path(__file__).resolve()
    if here.parent.name == "scripts" and (here.parent.parent / CONFIG_REL).is_file():
        return here.parent.parent
    return None


def default_root() -> Path:
    return own_root() or find_root(Path.cwd())


@dataclass
class MapEntry:
    paths: list
    pages: list


@dataclass
class Config:
    root: Path
    title: str
    specs: str
    plans: str
    exclude: list
    maps: list
    coverage_include: list
    coverage_exclude: list
    # [site] nav: page paths and group names in sidebar order (optional, may be partial).
    nav: list
    # [site] extra: Markdown outside docs/ to render too, as ExtraGroups.
    extra: list
    # Where links that leave docs/ are resolved. Differs from root only when building
    # from an export of the index (the pre-commit hook).
    outside_root: Path
    # Doc roots nested inside this one, as doc-root-relative directories. Their trees are
    # outside this doc root's territory: its pages, coverage and staleness skip them.
    nested: list = field(default_factory=list)


@dataclass
class ExtraGroup:
    group: str   # sidebar heading
    about: str   # shown on each page of the group ("" for none)
    paths: list  # repo-relative globs


def parse_extra(raw) -> list:
    """[site] extra is a list of globs (one "Reference" group) or [[site.extra]] tables
    with group / about / paths. Plain globs and tables may be mixed."""
    groups, plain = [], []
    for item in raw:
        if isinstance(item, str):
            plain.append(norm(item))
        elif isinstance(item, dict):
            groups.append(ExtraGroup(str(item.get("group") or "Reference"), str(item.get("about") or ""),
                                     [norm(p) for p in item.get("paths", [])]))
        else:
            raise PmdocsError(f"[site] extra entries must be globs or tables, not {item!r}")
    if plain:
        groups.insert(0, ExtraGroup("Reference", "", plain))
    return groups


README_GROUP = ExtraGroup("Repository", "The repository's README — its front page on the code host.",
                          ["README.md"])


def with_readme(groups: list, enabled) -> list:
    """Convention: the root README joins the site unless `[site] readme = false` or a
    [[site.extra]] group already lists it (that group's name and text then win)."""
    if enabled is False or any(glob_match("README.md", p) for g in groups for p in g.paths):
        return groups
    return [*groups, README_GROUP]


def load_config(root: Path, outside_root: Path | None = None) -> Config:
    root = Path(root)
    try:
        data = tomllib.loads(read_text(root / CONFIG_REL))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise PmdocsError(f"cannot read {CONFIG_REL}: {e}") from e
    site, paths, cov = data.get("site", {}), data.get("paths", {}), data.get("coverage", {})
    return Config(
        root=root,
        title=site.get("title", root.name),
        specs=norm(paths.get("specs", "docs/superpowers/specs")).rstrip("/"),
        plans=norm(paths.get("plans", "docs/superpowers/plans")).rstrip("/"),
        exclude=[norm(p) for p in paths.get("exclude", [])],
        maps=[MapEntry([norm(p) for p in m.get("paths", [])], [norm(p) for p in m.get("pages", [])])
              for m in data.get("map", [])],
        coverage_include=[norm(p) for p in cov.get("include", [])],
        coverage_exclude=[norm(p) for p in cov.get("exclude", [])],
        nav=[norm(p) for p in site.get("nav", [])],
        extra=with_readme(parse_extra(site.get("extra", [])), site.get("readme", True)),
        outside_root=Path(outside_root) if outside_root else root,
        # an index export (outside_root given) is not a work tree; the hook copies `nested`
        # over from the real doc root's config
        nested=[] if outside_root else nested_doc_roots(root),
    )


def nested_doc_roots(root: Path) -> list:
    """Doc roots inside this one (tracked or not yet added), doc-root-relative, sorted."""
    if not in_work_tree(root):
        return []
    files = zsplit(git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    suffix = "/" + CONFIG_REL
    return sorted({f[:-len(suffix)] for f in files if f.endswith(suffix)})


def in_territory(rel: str, nested) -> bool:
    """True unless rel lies inside a nested doc root."""
    return not any(rel == n or rel.startswith(n + "/") for n in nested)


def leaves_root(path: str) -> bool:
    """A configured path that points outside the doc root (`..`, `../…` or absolute)."""
    p = norm(path)
    return p == ".." or p.startswith("../") or p.startswith("/") or bool(re.match(r"[A-Za-z]:", p))


FM_RE = re.compile(r"\A---\n(.*?)\n?---[ \t]*(?:\n|\Z)", re.S)  # `\n?`: an empty block is still a block


def split_frontmatter(text: str):
    """Return (meta, body, error). meta is None when there is no (valid) frontmatter block."""
    m = FM_RE.match(text)
    if not m:
        return None, text, None
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        return None, text[m.end():], f"invalid YAML frontmatter: {e}".replace("\n", " ")
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        return None, text[m.end():], "frontmatter is not a mapping"
    meta = {k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in meta.items()}
    return meta, text[m.end():], None

# === parsing ===

BACKLOG_STATUSES = ("open", "in-progress", "blocked", "done", "dropped")
CLOSED_STATUSES = ("done", "dropped")
SPEC_STATUSES = ("draft", "approved", "in-progress", "shipped", "superseded", "abandoned")
PLAN_STATUSES = ("draft", "approved", "in-progress", "shipped", "abandoned")

ITEM_HEAD = re.compile(r"^## (B)(\d+)\. (.+?)\s*$")
DECISION_HEAD = re.compile(r"^## (D)(\d+)\. (.+?)\s*$")
GATE_HEAD = re.compile(r"^## (G)(\d+)\. (.+?)\s*$")
GATE_STATUSES = ("waiting", "answered", "dropped")
VERDICT_LINE = re.compile(r"^- \d{4}-\d{2}-\d{2}\b", re.M)
META_LINE = re.compile(r"^[A-Z][A-Za-z-]*: ")
META_SPLIT = re.compile(r"\s+[·|]\s+")


def id_key(ident: str) -> str:
    """'B07' and 'B7' name the same item."""
    m = re.fullmatch(r"([BDG])0*(\d+)", ident.strip())
    return f"{m.group(1)}{int(m.group(2))}" if m else ident.strip()


@dataclass
class Item:
    id: str                 # as written, e.g. "B07"
    key: str                # normalized, e.g. "B7"
    num: int
    title: str
    fields: dict
    file: str               # repo-relative path
    start: int              # 0-based index of the heading line
    end: int                # 0-based index one past the block
    meta_line: int | None   # 0-based index of the metadata line

    @property
    def status(self) -> str | None:
        s = self.fields.get("Status")
        return s.lower() if s else None


def parse_meta_line(line: str) -> dict:
    fields = {}
    for part in META_SPLIT.split(line.strip()):
        if ":" in part:
            k, v = part.split(":", 1)
            fields[k.strip()] = v.strip()
    return fields


def parse_items(text: str, file: str, head: re.Pattern = ITEM_HEAD) -> list:
    """Items are H2 headings matching `head`; a block runs to the next H1/H2."""
    lines = text.split("\n")
    heads = [(i, m) for i, line in enumerate(lines) if (m := head.match(line))]
    items = []
    for n, (i, m) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        for j in range(i + 1, end):
            if lines[j].startswith("# ") or lines[j].startswith("## "):
                end = j
                break
        j = i + 1
        while j < end and not lines[j].strip():
            j += 1
        meta_line = j if j < end and META_LINE.match(lines[j]) else None
        fields = parse_meta_line(lines[meta_line]) if meta_line is not None else {}
        ident = m.group(1) + m.group(2)
        items.append(Item(ident, id_key(ident), int(m.group(2)), m.group(3), fields, file, i, end, meta_line))
    return items


def next_id(items, prefix: str = "B") -> str:
    nums = [it.num for it in items if it.key.startswith(prefix)]
    return f"{prefix}{(max(nums) + 1) if nums else 1:02d}"


def count_inbox(text: str) -> int:
    """Items in a free-form inbox, read the way Markdown reads it (so code blocks, comments,
    rules and setext underlines are never items).

    Top-level list items if there are any. Otherwise top-level paragraphs after the first
    *section* heading — the first heading after an `# H1` title, or the first heading if
    it isn't an H1. Anything before that is intro: text above the title, a description
    under it, `---` rules. A file with headings but no section yields 0; a file with no
    headings at all counts all its paragraphs (a prose-only inbox)."""
    tokens = markdown().parse(text.replace("\r\n", "\n"))
    items = sum(1 for t in tokens if t.type == "list_item_open" and t.level == 1)
    if items:
        return items
    heads = [i for i, t in enumerate(tokens) if t.type == "heading_open"]
    if heads:
        sections = heads[1:] if tokens[heads[0]].tag == "h1" else heads
        if not sections:
            return 0
        tokens = tokens[sections[0]:]
    return sum(1 for t in tokens if t.type == "paragraph_open" and t.level == 0)

# === model ===

ROADMAP_REL = "docs/roadmap.md"
GENERATED = (ROADMAP_REL,)
BACKLOG_REL = "docs/backlog.md"
ARCHIVE_REL = "docs/backlog-archive.md"
DECISIONS_REL = "docs/decisions.md"
GATES_REL = "docs/gates.md"                  # questions only the user can answer (D10)
GATES_ARCHIVE_REL = "docs/gates-archive.md"
INBOX_REL = "TODO.md"

# The fixed sidebar (D09). A project's own pages attach under a category with `parent:`.
PARENTS = ("overview", "product", "architecture", "decisions")
CATEGORY_PAGES = {"overview": "docs/index.md", "product": "docs/product.md",
                  "architecture": "docs/architecture.md", "decisions": DECISIONS_REL}
TOP_ORDER = ["docs/index.md", GATES_REL, ROADMAP_REL, BACKLOG_REL, "docs/product.md",
             "docs/architecture.md", DECISIONS_REL]
ARCHIVES = [ARCHIVE_REL, GATES_ARCHIVE_REL]  # listed last, below a divider
FIXED_PAGES = set(TOP_ORDER) | set(ARCHIVES)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
FILL_MARKER = re.compile(r"<!--\s*pmdocs:fill")  # the template comment, not prose that mentions it


@dataclass
class Finding:
    level: str  # ERROR | WARN | FIXED | INFO
    where: str
    msg: str

    def __str__(self) -> str:
        return f"{self.level} {self.where}: {self.msg}"


@dataclass
class Page:
    rel: str
    text: str
    meta: dict | None
    body: str
    fm_error: str | None


@dataclass
class Model:
    cfg: Config
    pages: dict
    specs: dict
    plans: dict
    backlog: list
    archive: list
    decisions: list
    inbox: int
    gates: list          # open gates (docs/gates.md)
    gates_archive: list  # answered / dropped gates

    def item(self, key: str):
        k = id_key(str(key))
        for it in self.backlog + self.archive:
            if it.key == k:
                return it
        return None

    def gate(self, key: str):
        k = id_key(str(key))
        return next((g for g in self.gates + self.gates_archive if g.key == k), None)

    def verdicts(self, gate) -> list:
        """The dated verdict lines (`- YYYY-MM-DD …`) inside a gate's block."""
        lines = self.pages[gate.file].text.split("\n")[gate.start:gate.end]
        return VERDICT_LINE.findall("\n".join(lines))


def doc_files(cfg: Config) -> list:
    """Every docs/**/*.md except the generated site and excluded globs, in stable order."""
    docs = cfg.root / "docs"
    out = []
    for p in sorted(docs.rglob("*.md"), key=lambda p: p.as_posix()):
        rel = p.relative_to(cfg.root).as_posix()
        if rel.startswith("docs/site/") or any_match(rel, cfg.exclude) or not in_territory(rel, cfg.nested):
            continue  # a doc root nested under docs/ owns its own pages
        out.append(rel)
    return out


def _glob_base(pattern: str) -> str:
    """The directory part of a glob before its first wildcard: where to start walking."""
    head = re.split(r"[*?]", pattern, maxsplit=1)[0]
    return head.rsplit("/", 1)[0] if "/" in head else ""


def extra_patterns(cfg: Config) -> list:
    return [p for g in cfg.extra for p in g.paths]


def extra_group(cfg: Config, rel: str):
    """The first ExtraGroup whose globs match rel, or None."""
    return next((g for g in cfg.extra if any_match(rel, g.paths)), None)


def extra_files(cfg: Config) -> list:
    """Markdown outside docs/ that [site] extra asks to render, in stable order."""
    found = set()
    for pattern in extra_patterns(cfg):
        base = cfg.root / _glob_base(pattern)
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            rel = p.relative_to(cfg.root).as_posix()
            if glob_match(rel, pattern) and not rel.startswith("docs/") and in_territory(rel, cfg.nested):
                found.add(rel)
    return sorted(found)


def is_extra(rel: str) -> bool:
    return not rel.startswith("docs/")


def make_page(rel: str, text: str) -> Page:
    meta, body, err = split_frontmatter(text)
    return Page(rel, text, meta, body, err)


def inbox_count(root: Path) -> int:
    """Items in the root TODO.md inbox (0 if there is none). Cheap: the Stop hook calls it."""
    path = Path(root) / INBOX_REL
    return count_inbox(read_text(path)) if path.is_file() else 0


def load_model(cfg: Config) -> Model:
    pages = {rel: make_page(rel, read_text(cfg.root / rel)) for rel in doc_files(cfg) + extra_files(cfg)}
    specs = {r: p for r, p in pages.items() if r.startswith(cfg.specs + "/")}
    plans = {r: p for r, p in pages.items() if r.startswith(cfg.plans + "/")}

    def items(rel, head=ITEM_HEAD):
        return parse_items(pages[rel].text, rel, head) if rel in pages else []

    inbox = inbox_count(cfg.root)
    return Model(cfg, pages, specs, plans, items(BACKLOG_REL), items(ARCHIVE_REL),
                 items(DECISIONS_REL, DECISION_HEAD), inbox,
                 items(GATES_REL, GATE_HEAD), items(GATES_ARCHIVE_REL, GATE_HEAD))


def docs_ref(ref: str) -> str:
    """Refs in frontmatter and backlog lines are relative to docs/."""
    ref = norm(str(ref)).split("#", 1)[0]
    return ref if ref.startswith("docs/") else "docs/" + ref


def as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def validate(model: Model) -> list:
    out, cfg = [], model.cfg

    def err(where, msg):
        out.append(Finding("ERROR", where, msg))

    def warn(where, msg):
        out.append(Finding("WARN", where, msg))

    for rel, page in model.pages.items():
        if rel in GENERATED or is_extra(rel):
            continue  # extra files are rendered, not held to the docs convention
        if page.fm_error:
            err(rel, page.fm_error)
        elif page.meta is None:
            fixable = rel in model.specs or rel in model.plans
            err(rel, "missing frontmatter" + (" (check --fix adds it)" if fixable else ""))
        elif not page.meta.get("title"):
            err(rel, "frontmatter has no title")
        if has_fill_marker(page.body):
            warn(rel, "still has pmdocs:fill template markers")

    for rel, page in model.specs.items():
        if page.meta is None:
            continue
        status = page.meta.get("status")
        if status not in SPEC_STATUSES:
            err(rel, f"status {status!r} is not one of {', '.join(SPEC_STATUSES)}")
        for ref in as_list(page.meta.get("backlog")):
            if model.item(str(ref)) is None:
                err(rel, f"backlog item {ref} does not exist")
        for ref in as_list(page.meta.get("gates")):
            if model.gate(str(ref)) is None:
                err(rel, f"gate {ref} does not exist")
        sup = page.meta.get("superseded_by")
        if sup and docs_ref(sup) not in model.pages:
            err(rel, f"superseded_by {sup} does not exist")

    for rel, page in model.plans.items():
        if page.meta is None:
            continue
        status = page.meta.get("status")
        if status not in PLAN_STATUSES:
            err(rel, f"status {status!r} is not one of {', '.join(PLAN_STATUSES)}")
        spec = page.meta.get("spec")
        if spec and docs_ref(spec) not in model.specs:
            err(rel, f"spec {spec} does not exist")

    seen = {}
    for it in model.backlog + model.archive:
        where = f"{it.file}:{it.start + 1}"
        if it.key in seen:
            err(where, f"{it.id} duplicates {seen[it.key]}")
        else:
            seen[it.key] = where
        if it.status not in BACKLOG_STATUSES:
            err(where, f"{it.id} status {it.fields.get('Status')!r} is not one of {', '.join(BACKLOG_STATUSES)}")
        if not ISO_DATE.match(it.fields.get("Added", "")):
            err(where, f"{it.id} needs 'Added: YYYY-MM-DD'")
        if it.fields.get("Spec") and docs_ref(it.fields["Spec"]) not in model.pages:
            err(where, f"{it.id} spec {it.fields['Spec']} does not exist")
    for it in model.backlog:
        if it.status in CLOSED_STATUSES:
            warn(f"{it.file}:{it.start + 1}", f"{it.id} is {it.status}; check --fix moves it to {ARCHIVE_REL}")
    for it in model.archive:
        if it.status in ("open", "in-progress", "blocked"):
            err(f"{it.file}:{it.start + 1}", f"{it.id} is {it.status} but archived; move it back to {BACKLOG_REL}")
    for it in model.backlog + model.archive:
        if it.fields.get("Gate") and model.gate(it.fields["Gate"]) is None:
            err(f"{it.file}:{it.start + 1}", f"{it.id} gate {it.fields['Gate']} does not exist")

    gseen = {}
    for g in model.gates + model.gates_archive:
        where = f"{g.file}:{g.start + 1}"
        if g.key in gseen:
            err(where, f"{g.id} duplicates {gseen[g.key]}")
        else:
            gseen[g.key] = where
        if g.status not in GATE_STATUSES:
            err(where, f"{g.id} status {g.fields.get('Status')!r} is not one of {', '.join(GATE_STATUSES)}")
        if not ISO_DATE.match(g.fields.get("Asked", "")):
            err(where, f"{g.id} needs 'Asked: YYYY-MM-DD'")
        for ref in re.findall(r"[BG]\d+", g.fields.get("For", "")):
            if (model.item(ref) if ref.startswith("B") else model.gate(ref)) is None:
                err(where, f"{g.id} is for {ref}, which does not exist")
        if g.status == "answered" and not model.verdicts(g):
            warn(where, f"{g.id} is answered but has no dated verdict (`- YYYY-MM-DD — \"…\"`)")
    for g in model.gates:
        if g.status in ("answered", "dropped"):
            warn(f"{g.file}:{g.start + 1}", f"{g.id} is {g.status}; check --fix moves it to {GATES_ARCHIVE_REL}")
    for g in model.gates_archive:
        if g.status == "waiting":
            err(f"{g.file}:{g.start + 1}", f"{g.id} is waiting but archived; move it back to {GATES_REL}")

    dseen, dkeys = {}, {d.key for d in model.decisions}
    for d in model.decisions:
        where = f"{d.file}:{d.start + 1}"
        if d.key in dseen:
            err(where, f"{d.id} duplicates {dseen[d.key]}")
        else:
            dseen[d.key] = where
        m = re.search(r"superseded by (D\d+)", d.fields.get("Status", ""), re.I)
        if m and id_key(m.group(1)) not in dkeys:
            err(where, f"{d.id} is superseded by {m.group(1)}, which does not exist")

    # Every configured path stays inside the doc root: shared code is documented by the
    # doc root that contains it (B09).
    for entry in cfg.maps:
        for p in entry.paths:
            if leaves_root(p):
                err(CONFIG_REL, f"[[map]] path {p} leaves the doc root")
    for p in cfg.coverage_include + cfg.coverage_exclude:
        if leaves_root(p):
            err(CONFIG_REL, f"[coverage] path {p} leaves the doc root")
    for g in cfg.extra:
        for p in g.paths:
            if leaves_root(p):
                err(CONFIG_REL, f"[[site.extra]] path {p} leaves the doc root")
    for entry in cfg.maps:
        for pg in entry.pages:
            if leaves_root(pg):
                err(CONFIG_REL, f"[[map]] page {pg} leaves the doc root")
                continue
            # validate() also runs against the hook's export of docs/ only, so a page
            # outside docs/ (a LICENSE, a provenance table) is found via outside_root.
            if not ((cfg.root / pg).is_file() or (cfg.outside_root / pg).is_file()):
                err(CONFIG_REL, f"[[map]] page {pg} does not exist (paths are relative to the doc root)")

    if cfg.nav:
        err(CONFIG_REL, "[site] nav was removed in pmdocs 0.2.0: the sidebar order is fixed. Attach "
                        f"a page with `parent:` frontmatter ({', '.join(PARENTS)}) and delete `nav`.")

    for rel, page in model.pages.items():
        if (page.meta is None or is_extra(rel) or rel in FIXED_PAGES or rel in GENERATED
                or rel in model.specs or rel in model.plans):
            continue
        parent = page.meta.get("parent")
        if parent is None:
            warn(rel, f"no parent: set `parent:` to one of {', '.join(PARENTS)} "
                      "(until then it is listed under Other)")
        elif parent not in PARENTS:
            err(rel, f"parent {parent!r} is not one of {', '.join(PARENTS)}")
        elif CATEGORY_PAGES[parent] not in model.pages:
            warn(rel, f"parent {parent!r}, but {CATEGORY_PAGES[parent]} does not exist "
                      "(listed under Other)")
    return out


_MD = None


def markdown() -> MarkdownIt:
    global _MD
    if _MD is None:
        _MD = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    return _MD


def has_fill_marker(body: str) -> bool:
    """A real template marker is raw HTML in the page; quoted in code, it is just an example."""
    for t in markdown().parse(body):
        if t.type == "html_block" and FILL_MARKER.search(t.content):
            return True
        if any(c.type == "html_inline" and FILL_MARKER.search(c.content) for c in t.children or []):
            return True
    return False


def slugify(text: str) -> str:
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def headings(tokens) -> list:
    """[(level, raw text, slug)], de-duplicated GitHub-style (-1, -2, ...)."""
    out, seen = [], {}
    for i, t in enumerate(tokens):
        if t.type == "heading_open":
            text = tokens[i + 1].content
            base = slugify(text)
            n = seen.get(base, 0)
            seen[base] = n + 1
            out.append((int(t.tag[1]), text, base if n == 0 else f"{base}-{n}"))
    return out


def iter_links(tokens):
    for t in tokens:
        for child in t.children or []:
            if child.type == "link_open":
                yield child.attrGet("href"), child
            elif child.type == "image":
                yield child.attrGet("src"), child


LINK_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)


def resolve_href(src_rel: str, href: str):
    """(repo-relative target, anchor) for a relative href in page src_rel."""
    path, _, anchor = href.partition("#")
    if not path:
        return src_rel, anchor
    return posixpath.normpath(posixpath.join(posixpath.dirname(src_rel), unquote(path))), anchor


def check_links(model: Model) -> list:
    out, slug_cache = [], {}

    def slugs(rel):
        if rel not in slug_cache:
            slug_cache[rel] = {s for _, _, s in headings(markdown().parse(model.pages[rel].body))}
        return slug_cache[rel]

    for rel, page in sorted(model.pages.items()):
        if rel in GENERATED:
            continue
        for href, _ in iter_links(markdown().parse(page.body)):
            if not href or LINK_SCHEME.match(href) or href.startswith("//"):
                continue
            target, anchor = resolve_href(rel, href)
            if target in GENERATED:
                continue
            if target in model.pages:
                if anchor and anchor not in slugs(target):
                    out.append(Finding("ERROR", rel, f"broken anchor {href}"))
            elif target == ".." or target.startswith("../"):
                continue  # outside the repository; not ours to check
            elif not ((model.cfg.root / target).exists() or (model.cfg.outside_root / target).exists()):
                out.append(Finding("ERROR", rel, f"broken link {href}"))
    return out

# === git, drift, staleness ===

def git(root: Path, *args, check: bool = True, input: str | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", input=input)
    if check and r.returncode != 0:
        raise PmdocsError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def zsplit(out: str) -> list:
    """NUL-separated git output (-z: no quoting of odd names) → normalized paths."""
    return [norm(f) for f in out.split("\0") if f]


def has_head(root: Path) -> bool:
    return git(root, "rev-parse", "--verify", "-q", "HEAD", check=False).strip() != ""


def in_work_tree(root: Path) -> bool:
    return git(root, "rev-parse", "--is-inside-work-tree", check=False).strip() == "true"


def changed_files(root: Path, staged: bool, nested=()) -> set:
    """Changed files in this doc root's territory, as doc-root-relative paths.

    staged: index vs HEAD. Otherwise: working tree vs HEAD plus untracked files.
    `diff --relative` makes paths doc-root-relative and drops changes outside the doc root
    (plain `diff` reports repo-top paths, which never match a subfolder's doc-map);
    `ls-files` is cwd-relative already. Files in nested doc roots are dropped too."""
    if staged:
        files = set(zsplit(git(root, "diff", "--cached", "--name-only", "-z", "--no-renames", "--relative")))
    else:
        files = set(zsplit(git(root, "ls-files", "--others", "--exclude-standard", "-z")))
        if has_head(root):
            files |= set(zsplit(git(root, "diff", "HEAD", "--name-only", "-z", "--no-renames", "--relative")))
        else:
            files |= set(zsplit(git(root, "ls-files", "-z")))
    return {f for f in files if in_territory(f, nested)}


def pages_for(cfg: Config, path: str) -> list:
    pages = []
    for entry in cfg.maps:
        if any_match(path, entry.paths):
            pages += [p for p in entry.pages if p not in pages]
    return pages


# This tool's own vendored files. They change on every `update` and are documented by
# pm-framework, not by the project, so no doc-map or coverage rule applies to them.
VENDORED = ("scripts/pmdocs.py", "scripts/hooks/pre-commit")


def staleness(cfg: Config, changed: set) -> list:
    out = []
    for f in sorted(changed - set(VENDORED)):
        for entry in cfg.maps:
            if any_match(f, entry.paths) and not any(p in changed for p in entry.pages):
                out.append(Finding("WARN", f, f"changed, but none of its docs did: {', '.join(entry.pages)}"))
    return out


def coverage(cfg: Config) -> list:
    if not cfg.coverage_include:
        return []
    out = []
    for f in sorted(zsplit(git(cfg.root, "ls-files", "-z"))):
        if f in VENDORED or not in_territory(f, cfg.nested):
            continue
        if (any_match(f, cfg.coverage_include) and not any_match(f, cfg.coverage_exclude)
                and not any(any_match(f, e.paths) for e in cfg.maps)):
            out.append(Finding("WARN", f, f"not covered by any [[map]] in {CONFIG_REL}"))
    return out


def drift_static(model: Model) -> list:
    """Status disagreements visible from the files alone (deterministic; used by the roadmap)."""
    out = []
    for rel, plan in sorted(model.plans.items()):
        meta = plan.meta or {}
        spec_rel = docs_ref(meta["spec"]) if meta.get("spec") else None
        spec = model.specs.get(spec_rel) if spec_rel else None
        if spec is None or spec.meta is None:
            continue
        sstatus, pstatus = spec.meta.get("status"), meta.get("status")
        if pstatus not in (None, "draft") and sstatus == "draft":
            out.append(Finding("WARN", spec_rel, f"still draft, but plan {rel} is {pstatus}"))
        if pstatus == "shipped" and sstatus not in ("shipped", "superseded"):
            out.append(Finding("WARN", rel, f"shipped, but its spec {spec_rel} is {sstatus}"))
    for rel, spec in sorted(model.specs.items()):
        meta = spec.meta or {}
        if meta.get("status") != "shipped":
            continue
        for ref in as_list(meta.get("backlog")):
            it = model.item(str(ref))
            if it and it.status in ("open", "in-progress"):
                out.append(Finding("WARN", rel, f"shipped, but {it.id} is still {it.status}"))
        for ref in as_list(meta.get("gates")):
            g = model.gate(str(ref))
            if g and g.status == "waiting":
                out.append(Finding("WARN", rel, f"shipped, but gate {g.id} is still waiting on the user"))
    for it in model.backlog:
        g = model.gate(it.fields["Gate"]) if it.fields.get("Gate") else None
        if g and it.status == "blocked" and g.status in ("answered", "dropped"):
            out.append(Finding("WARN", f"{it.file}:{it.start + 1}",
                               f"{it.id} is blocked on {g.id}, which is {g.status}; unblock it"))
    return out


STALE_DAYS = 30


def _log_time(root: Path, paths: list):
    r = subprocess.run(["git", "log", "-1", "--format=%ct", "--", *paths], cwd=root,
                       capture_output=True, text=True)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def _blame_time(root: Path, file: str, start: int, end: int):
    r = subprocess.run(["git", "blame", "--porcelain", "-L", f"{start + 1},{end}", "--", file],
                       cwd=root, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return None
    times = [int(line.split()[1]) for line in r.stdout.splitlines() if line.startswith("committer-time ")]
    return max(times) if times else None


def drift_stale_progress(model: Model, now: float) -> list:
    """in-progress items with no commit touching their entry, spec or plans for STALE_DAYS."""
    root = model.cfg.root
    if not in_work_tree(root):
        return []
    out = []
    for it in model.backlog:
        if it.status != "in-progress":
            continue
        n_lines = len(model.pages[it.file].text.rstrip("\n").split("\n"))
        times = [_blame_time(root, it.file, it.start, min(it.end, n_lines))]
        if it.fields.get("Spec"):
            spec_rel = docs_ref(it.fields["Spec"])
            plans = [r for r, p in model.plans.items()
                     if p.meta and p.meta.get("spec") and docs_ref(p.meta["spec"]) == spec_rel]
            times.append(_log_time(root, [spec_rel, *plans]))
        latest = max((t for t in times if t), default=None)
        if latest and now - latest > STALE_DAYS * 86400:
            days = int((now - latest) // 86400)
            out.append(Finding("WARN", f"{it.file}:{it.start + 1}", f"{it.id} is in-progress but untouched for {days} days"))
    return out

# === fixes and check ===

ARCHIVE_TEMPLATE = ("---\ntitle: Backlog archive\nsummary: Closed backlog items, oldest first.\norder: 91\n---\n\n"
                    "# Backlog archive\n")
H1_LINE = re.compile(r"^# (.+?)\s*$", re.M)
SPEC_LINE = re.compile(r"^\*\*Spec:\*\*\s*`?([^`\s]+)`?", re.M)


GATES_ARCHIVE_TEMPLATE = ("---\ntitle: Gates archive\nsummary: Answered and dropped gates, with their "
                          "verdicts, oldest first.\n---\n\n# Gates archive\n")


def _archive_items(cfg: Config, model: Model, items: list, src_rel: str, dst_rel: str,
                   template: str, today: str | None) -> list:
    """Move closed items (blocks) from src to the end of dst; stamp `Closed:` if today is given."""
    if not items:
        return []
    lines = model.pages[src_rel].text.split("\n")
    blocks = []
    for it in items:
        block = lines[it.start:it.end]
        if today and it.meta_line is not None and "Closed" not in it.fields:
            block[it.meta_line - it.start] += f" · Closed: {today}"
        while block and not block[-1].strip():
            block.pop()
        blocks.append("\n".join(block))
    for it in sorted(items, key=lambda i: i.start, reverse=True):
        del lines[it.start:it.end]
    write_text(cfg.root / src_rel, "\n".join(lines).rstrip("\n") + "\n")
    archive = model.pages[dst_rel].text if dst_rel in model.pages else template
    write_text(cfg.root / dst_rel, archive.rstrip("\n") + "\n\n" + "\n\n".join(blocks) + "\n")
    return [Finding("FIXED", src_rel, f"moved {', '.join(i.id for i in items)} to {dst_rel}")]


def fix_closed_items(cfg: Config, model: Model, today: str) -> list:
    """Move done/dropped items from the backlog to the end of the archive."""
    closed = [it for it in model.backlog if it.status in CLOSED_STATUSES]
    return _archive_items(cfg, model, closed, BACKLOG_REL, ARCHIVE_REL, ARCHIVE_TEMPLATE, today)


def fix_closed_gates(cfg: Config, model: Model) -> list:
    """Move answered/dropped gates to the gates archive (their verdicts are already dated)."""
    closed = [g for g in model.gates if g.status in ("answered", "dropped")]
    return _archive_items(cfg, model, closed, GATES_REL, GATES_ARCHIVE_REL, GATES_ARCHIVE_TEMPLATE, None)


def fix_missing_frontmatter(cfg: Config, model: Model, blocked: frozenset) -> list:
    """Specs and plans written without frontmatter (e.g. by other skills) get a draft header."""
    out = []
    for rel in sorted({**model.specs, **model.plans}):
        page = model.pages[rel]
        if page.meta is not None or page.fm_error or rel in blocked:
            continue
        m = H1_LINE.search(page.text)
        meta = {"title": m.group(1) if m else posixpath.basename(rel)[:-3], "status": "draft"}
        if rel in model.plans:
            s = SPEC_LINE.search(page.text)
            if s:
                ref = norm(s.group(1))
                ref = ref[len("docs/"):] if ref.startswith("docs/") else ref
                if docs_ref(ref) in model.specs:
                    meta["spec"] = ref
        header = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
        write_text(cfg.root / rel, f"---\n{header}---\n\n{page.text}")
        out.append(Finding("FIXED", rel, "added frontmatter (status: draft); correct it if needed"))
    return out


def apply_fixes(cfg: Config, model: Model, today: str, blocked: frozenset = frozenset()):
    """Apply every mechanical fix whose files aren't blocked. Returns (findings, touched files)."""
    findings, touched = [], []
    if not ({BACKLOG_REL, ARCHIVE_REL} & blocked):
        moved = fix_closed_items(cfg, model, today)
        if moved:
            findings += moved
            touched += [BACKLOG_REL, ARCHIVE_REL]
    if not ({GATES_REL, GATES_ARCHIVE_REL} & blocked):
        moved = fix_closed_gates(cfg, model)
        if moved:
            findings += moved
            touched += [GATES_REL, GATES_ARCHIVE_REL]
    for f in fix_missing_frontmatter(cfg, model, blocked):
        findings.append(f)
        touched.append(f.where)
    return findings, touched


def doc_findings(model: Model) -> list:
    return validate(model) + check_links(model) + drift_static(model)


def repo_findings(cfg: Config, model: Model, staged: bool, now: float) -> list:
    if not in_work_tree(cfg.root):
        return [Finding("INFO", ".", "not a git work tree; staleness and coverage skipped")]
    changed = changed_files(cfg.root, staged, cfg.nested)
    return staleness(cfg, changed) + coverage(cfg) + drift_stale_progress(model, now)


def inbox_findings(model: Model) -> list:
    if not model.inbox:
        return []
    return [Finding("INFO", INBOX_REL, f"{model.inbox} inbox item(s) awaiting triage")]


_LEVEL_ORDER = {"ERROR": 0, "WARN": 1, "FIXED": 2, "INFO": 3}


def report(findings, stream=None) -> None:
    stream = stream or sys.stdout
    for f in sorted(findings, key=lambda f: _LEVEL_ORDER[f.level]):
        print(f, file=stream)


def cmd_check(args) -> int:
    cfg = load_config(default_root())
    findings = []
    model = load_model(cfg)
    if args.fix:
        fixed, _ = apply_fixes(cfg, model, date.today().isoformat())
        findings += fixed
        model = load_model(cfg)
    findings += doc_findings(model) + repo_findings(cfg, model, args.staged, time.time()) + inbox_findings(model)
    report(findings)
    if not any(f.level in ("ERROR", "WARN") for f in findings):
        print("pmdocs: no errors or warnings")
    return 1 if any(f.level == "ERROR" for f in findings) else 0

# === roadmap ===

GENERATED_BANNER = "<!-- GENERATED by scripts/pmdocs.py — do not edit by hand -->"


def _md_text(s) -> str:
    """Safe inside a table cell and inside link text."""
    return re.sub(r"([|\[\]*_`])", r"\\\1", str(s)).replace("\n", " ")


def _link(to_rel: str, text, anchor: str = "") -> str:
    href = posixpath.relpath(to_rel, posixpath.dirname(ROADMAP_REL))
    return f"[{_md_text(text)}]({href}{'#' + anchor if anchor else ''})"


def render_roadmap(model: Model) -> str:
    out = ["---", "title: Roadmap", "summary: Generated from gates, specs, plans, the backlog and the inbox.",
           "order: 5", "---", "", GENERATED_BANNER, "", "# Roadmap", "", "## Waiting on you", ""]
    waiting = [g for g in model.gates if g.status == "waiting"]
    for g in waiting:
        details = [f"{k.lower()}: {g.fields[k]}" for k in ("Needs", "For") if g.fields.get(k)]
        details.append(f"asked {g.fields.get('Asked', '?')}")
        out.append(f"- **{g.id}** {_link(GATES_REL, g.title, slugify(f'{g.id}. {g.title}'))} — "
                   + " · ".join(details))
    out += ([""] if waiting else ["Nothing is waiting on you.", ""]) + ["## Initiatives", ""]
    plans_by_spec = {}
    for rel, p in sorted(model.plans.items()):
        if p.meta and p.meta.get("spec"):
            plans_by_spec.setdefault(docs_ref(p.meta["spec"]), []).append((rel, p))
    if model.specs:
        out += ["| Spec | Status | Plans | Backlog |", "|---|---|---|---|"]
        for rel, s in sorted(model.specs.items(), reverse=True):
            meta = s.meta or {}
            plans = ", ".join(f"{_link(r, (p.meta or {}).get('title', r))} ({(p.meta or {}).get('status', '?')})"
                              for r, p in plans_by_spec.get(rel, [])) or "—"
            backlog = ", ".join(str(b) for b in as_list(meta.get("backlog"))) or "—"
            out.append(f"| {_link(rel, meta.get('title', rel))} | {meta.get('status', '?')} | {plans} | {backlog} |")
    else:
        out.append("No specs yet.")
    out += ["", "## Backlog", ""]
    any_open = False
    for heading, status in (("In progress", "in-progress"), ("Blocked", "blocked"), ("Open", "open")):
        items = [it for it in model.backlog if it.status == status]
        if not items:
            continue
        any_open = True
        out += [f"### {heading}", ""]
        for it in items:
            spec = f" — {_link(docs_ref(it.fields['Spec']), 'spec')}" if it.fields.get("Spec") else ""
            out.append(f"- **{it.id}** {_link(BACKLOG_REL, it.title, slugify(f'{it.id}. {it.title}'))}{spec}")
        out.append("")
    if not any_open:
        out += ["Nothing open.", ""]
    if model.archive:
        out += [f"Closed items: {len(model.archive)} in {_link(ARCHIVE_REL, 'the archive')}.", ""]
    else:
        out += ["Closed items: none yet.", ""]
    out += ["## Inbox", "",
            f"{model.inbox} item(s) in `TODO.md` awaiting triage." if model.inbox else "Empty.", ""]
    out += ["## Drift", ""]
    out += [f"- `{f.where}`: {f.msg}" for f in drift_static(model)] or ["No drift detected."]
    out += ["", "## What this cannot tell you", "",
            "- Whether a `shipped` spec delivered everything it claims.",
            "- Work that was never written down in a spec, the backlog or `TODO.md`.",
            "- Whether a page is accurate — only whether it changed alongside the code it covers.", ""]
    return "\n".join(out)

# === site ===

SITE_DIR = "docs/site"
ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf"}

CSS = """
:root{--bg:#fbfbf9;--fg:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--accent:#2f5d8a;--code:#f1f0ec;--side:#f4f3ef}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#e8e6e1;--muted:#9a978f;--line:#2e2d2a;--accent:#8ab4e0;--code:#22211f;--side:#1c1b1a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}
.layout{display:grid;grid-template-columns:16rem minmax(0,1fr);min-height:100vh}
nav.side{background:var(--side);border-right:1px solid var(--line);padding:1.25rem 1rem;font-size:.9rem;position:sticky;top:0;height:100vh;overflow:auto}
nav.side .site{display:block;font-weight:700;color:var(--fg);text-decoration:none;margin-bottom:1rem}
nav.side h2{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:1.25rem 0 .35rem;border:0;padding:0}
nav.side ul{list-style:none;margin:0;padding:0}
nav.side ul.continued{border-top:1px solid var(--line);margin-top:.75rem;padding-top:.5rem}
nav.side ul.children{margin:.1rem 0 .3rem .75rem;padding-left:.5rem;border-left:1px solid var(--line);font-size:.85rem}
nav.side li a{display:block;padding:.15rem .4rem;border-radius:4px;color:var(--fg);text-decoration:none}
nav.side li a[aria-current]{background:var(--line);font-weight:600}
main{max-width:52rem;padding:2rem 2.5rem 4rem}
h1{margin-top:0;line-height:1.2}
h2{margin-top:2.2rem;padding-bottom:.25rem;border-bottom:1px solid var(--line)}
.summary{color:var(--muted);font-size:1.05rem;margin-top:-.5rem}
.meta{font-size:.85rem;color:var(--muted)}
.about{font-size:.9rem;border-left:3px solid var(--accent);padding:.1rem .75rem;margin:.5rem 0}
.badge{display:inline-block;padding:0 .5rem;border-radius:999px;border:1px solid var(--line);font-weight:600}
.s-shipped,.s-done{background:#d9f0dc;color:#1d4d24}
.s-in-progress,.s-approved{background:#dbe8f7;color:#1d3a5c}
.s-draft,.s-open,.s-blocked{background:#f3ecd6;color:#5a4712}
.s-superseded,.s-abandoned,.s-dropped{background:#eeeeec;color:#555;text-decoration:line-through}
details.toc{font-size:.85rem;border-left:2px solid var(--line);padding-left:.75rem;margin:.5rem 0 1.5rem}
details.toc summary{cursor:pointer;color:var(--muted)}
details.toc ul{list-style:none;margin:.25rem 0 0;padding:0}
details.toc .l3{padding-left:1rem}
code,pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.9em;background:var(--code);border-radius:4px}
code{padding:.1em .3em}
pre{padding:.8rem 1rem;overflow:auto}
pre code{padding:0;background:none}
table{border-collapse:collapse;display:block;overflow:auto;margin:1rem 0}
th,td{border:1px solid var(--line);padding:.35rem .6rem;text-align:left;vertical-align:top}
blockquote{margin:1rem 0;padding:.1rem 1rem;border-left:3px solid var(--line);color:var(--muted)}
img,svg{max-width:100%}
@media (max-width:48rem){.layout{grid-template-columns:1fr}nav.side{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}main{padding:1.25rem 1rem 3rem}}
""".strip()

PAGE = Template("""<!doctype html>
$banner
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title — $site</title>
<style>$css</style>
</head>
<body>
<div class="layout">
<nav class="side"><a class="site" href="$home">$site</a>
$nav
</nav>
<main>
<h1>$title</h1>
$summary$meta$toc
$content
</main>
</div>
</body>
</html>
""")


def is_generated_file(name: str) -> bool:
    """What build writes into docs/site/: pages and copied assets. Anything else is left alone."""
    suffix = posixpath.splitext(name)[1].lower()
    return suffix == ".html" or suffix in ASSET_EXT


def site_path(rel: str) -> str:
    """docs/a/b.md -> docs/site/a/b.html; an extra file x/y.md -> docs/site/extra/x/y.html"""
    if is_extra(rel):
        return f"{SITE_DIR}/extra/{rel[:-len('.md')]}.html"
    return f"{SITE_DIR}/{rel[len('docs/'):-len('.md')]}.html"


def _title(page: Page) -> str:
    """frontmatter title, then name (skills), then the first H1, then the file name."""
    meta = page.meta or {}
    if meta.get("title") or meta.get("name"):
        return str(meta.get("title") or meta.get("name"))
    m = H1_LINE.search(page.body)
    return m.group(1) if m else posixpath.basename(page.rel)[:-3]


def _page_key(item):
    rel, p = item
    order = (p.meta or {}).get("order", 50)
    return (order if isinstance(order, (int, float)) else 50, _title(p).lower(), rel)


def _extra_key(cfg: Config, rel: str):
    """Extra pages keep the order their globs are listed in (then by path)."""
    patterns = extra_patterns(cfg)
    return (next((i for i, p in enumerate(patterns) if glob_match(rel, p)), len(patterns)), rel)


def placed_parent(model: Model, rel: str):
    """The category a project page hangs under, or None if it goes under "Other"."""
    parent = ((model.pages[rel].meta or {}).get("parent"))
    return parent if parent in PARENTS and CATEGORY_PAGES[parent] in model.pages else None


def nav_groups(model: Model) -> list:
    """The fixed sidebar, as [(heading, [(rel, page, [(rel, page)] children)], kind)].

    Overview, Roadmap, Backlog, Product, Architecture, Decisions (a project's own pages
    nested under the category their `parent:` names); then Specs, Plans, the extra groups,
    "Other" (pages without a usable parent) and, last, the backlog archive. Projects can't
    reorder it — the work status is always in the same, prominent place (D09)."""
    pages, cfg = model.pages, model.cfg
    children = {c: [] for c in PARENTS}
    for rel in pages:
        if is_extra(rel) or rel in FIXED_PAGES or rel in model.specs or rel in model.plans:
            continue
        parent = placed_parent(model, rel)
        if parent:
            children[parent].append((rel, pages[rel]))
    by_page = {page: cat for cat, page in CATEGORY_PAGES.items()}
    tree = [(rel, pages[rel], sorted(children.get(by_page.get(rel), []), key=_page_key))
            for rel in TOP_ORDER if rel in pages]
    sections = [("", tree, "tree")] if tree else []

    for heading, group in (("Specs", model.specs), ("Plans", model.plans)):
        if group:
            sections.append((heading, [(r, p, []) for r, p in sorted(group.items(), reverse=True)], "group"))

    extra_sections = {}
    for rel, p in pages.items():
        if is_extra(rel):
            g = extra_group(cfg, rel)
            extra_sections.setdefault(g.group if g else "Reference", []).append((rel, p))
    for name in dict.fromkeys(g.group for g in cfg.extra):
        if name in extra_sections:
            items = sorted(extra_sections[name], key=lambda x: _extra_key(cfg, x[0]))
            sections.append((name, [(r, p, []) for r, p in items], "group"))

    other = [(rel, p) for rel, p in pages.items()
             if not (is_extra(rel) or rel in FIXED_PAGES or rel in model.specs or rel in model.plans)
             and not placed_parent(model, rel)]
    if other:
        sections.append(("Other", [(r, p, []) for r, p in sorted(other, key=_page_key)], "group"))
    archives = [(rel, pages[rel], []) for rel in ARCHIVES if rel in pages]
    if archives:
        sections.append(("", archives, "continued"))
    return sections


def rewrite_href(href: str, src_rel: str, model: Model) -> str:
    """Point a Markdown link at the right file from the page's place in docs/site/."""
    if not href or LINK_SCHEME.match(href) or href.startswith(("#", "//")):
        return href
    target, anchor = resolve_href(src_rel, href)
    if target in model.pages or target in GENERATED:
        dest = site_path(target)
    elif (target.startswith("docs/") and not target.startswith(SITE_DIR + "/")
          and posixpath.splitext(target)[1].lower() in ASSET_EXT):
        dest = SITE_DIR + target[len("docs"):]
    else:
        dest = target  # a repository file outside the rendered site
    rel = posixpath.relpath(dest, posixpath.dirname(site_path(src_rel)))
    return quote(rel, safe="/") + (f"#{anchor}" if anchor else "")


def render_body(page: Page, model: Model):
    md = markdown()
    tokens = md.parse(page.body)
    heads = headings(tokens)
    ids = iter(heads)
    for t in tokens:
        if t.type == "heading_open":
            t.attrSet("id", next(ids)[2])
        for child in t.children or []:
            if child.type == "link_open":
                child.attrSet("href", rewrite_href(child.attrGet("href"), page.rel, model))
            elif child.type == "image":
                child.attrSet("src", rewrite_href(child.attrGet("src"), page.rel, model))
    if len(tokens) >= 3 and tokens[0].type == "heading_open" and tokens[0].tag == "h1":
        tokens = tokens[3:]  # the template renders the title as the page's only H1
    return md.renderer.render(tokens, md.options, {}), [h for h in heads if h[0] in (2, 3)]


def render_meta(page: Page, model: Model) -> str:
    meta = page.meta or {}
    bits = []
    if meta.get("status"):
        s = str(meta["status"])
        known = set(SPEC_STATUSES) | set(PLAN_STATUSES) | set(BACKLOG_STATUSES)
        bits.append(f'<span class="badge s-{s if s in known else "other"}">{html.escape(s)}</span>')
    if meta.get("created"):
        bits.append(f"created {html.escape(str(meta['created']))}")
    if meta.get("spec"):
        target = docs_ref(meta["spec"])
        href = posixpath.relpath(site_path(target), posixpath.dirname(site_path(page.rel)))
        label = _title(model.pages[target]) if target in model.pages else str(meta["spec"])
        bits.append(f'spec: <a href="{html.escape(quote(href, safe="/"))}">{html.escape(label)}</a>')
    if meta.get("backlog"):
        bits.append("backlog: " + html.escape(", ".join(str(b) for b in as_list(meta["backlog"]))))
    return " · ".join(bits)


def render_page(page: Page, model: Model, nav) -> str:
    body, toc_heads = render_body(page, model)
    here = posixpath.dirname(site_path(page.rel))
    nav_html = []
    def link(rel, p):
        href = quote(posixpath.relpath(site_path(rel), here), safe="/")
        current = ' aria-current="page"' if rel == page.rel else ""
        return f'<a href="{html.escape(href)}"{current}>{html.escape(_title(p))}</a>'

    for heading, items, kind in nav:
        if kind == "continued":
            nav_html.append('<ul class="continued">')  # a divider: not part of the group above
        else:
            nav_html.append((f"<h2>{html.escape(heading)}</h2>" if heading else "") + "<ul>")
        for rel, p, kids in items:
            sub = "".join(f"<li>{link(r, q)}</li>" for r, q in kids)
            nav_html.append(f"<li>{link(rel, p)}" + (f'<ul class="children">{sub}</ul>' if sub else "") + "</li>")
        nav_html.append("</ul>")
    toc = ""
    if len(toc_heads) >= 2:
        entries = "".join(f'<li class="l{lvl}"><a href="#{slug}">{html.escape(re.sub(r"[*_`]", "", text))}</a></li>'
                          for lvl, text, slug in toc_heads)
        # <details> collapses with no script; closed by default so it costs one line.
        toc = f'<details class="toc"><summary>On this page</summary><ul>{entries}</ul></details>\n'
    meta = render_meta(page, model)
    summary = (page.meta or {}).get("summary") or (page.meta or {}).get("description")
    provenance = ""
    if is_extra(page.rel):
        # Say where an extra page lives and why it is here, so it isn't mistaken for docs.
        group = extra_group(model.cfg, page.rel)
        href = quote(posixpath.relpath(page.rel, here), safe="/")
        if group and group.about:
            provenance += f'<p class="about">{html.escape(group.about)}</p>\n'
        provenance += (f'<p class="meta source">Source: <a href="{html.escape(href)}">'
                       f"<code>{html.escape(page.rel)}</code></a> — outside <code>docs/</code>, "
                       "rendered here for reading.</p>\n")
    return PAGE.substitute(
        banner=f"<!-- GENERATED by scripts/pmdocs.py from {page.rel} — do not edit by hand -->",
        title=html.escape(_title(page)),
        site=html.escape(model.cfg.title),
        css=CSS,
        home=html.escape(posixpath.relpath(f"{SITE_DIR}/index.html", here)),
        nav="\n".join(nav_html),
        summary=(f'<p class="summary">{html.escape(str(summary))}</p>\n' if summary else "") + provenance,
        meta=f'<p class="meta">{meta}</p>\n' if meta else "",
        toc=toc,
        content=body,
    )


def site_outputs(model: Model) -> dict:
    """{repo-relative path: str | bytes} — everything that belongs under docs/site/."""
    nav = nav_groups(model)
    out = {site_path(rel): render_page(p, model, nav) for rel, p in model.pages.items()}
    docs = model.cfg.root / "docs"
    for p in sorted(docs.rglob("*"), key=lambda p: p.as_posix()):
        rel = p.relative_to(model.cfg.root).as_posix()
        if (p.is_file() and p.suffix.lower() in ASSET_EXT and not rel.startswith(SITE_DIR + "/")
                and not any_match(rel, model.cfg.exclude) and in_territory(rel, model.cfg.nested)):
            out[SITE_DIR + rel[len("docs"):]] = p.read_bytes()
    return out


def build(cfg: Config, check: bool = False) -> list:
    """Regenerate docs/roadmap.md and docs/site/. Returns the paths that changed (or would)."""
    model = load_model(cfg)
    changed = []
    roadmap = render_roadmap(model)
    rp = cfg.root / ROADMAP_REL
    if not rp.is_file() or read_text(rp) != roadmap:
        changed.append(ROADMAP_REL)
        if not check:
            write_text(rp, roadmap)
    model.pages[ROADMAP_REL] = make_page(ROADMAP_REL, roadmap)
    outputs = site_outputs(model)
    site = cfg.root / SITE_DIR
    existing = ({p.relative_to(cfg.root).as_posix() for p in site.rglob("*") if p.is_file() and is_generated_file(p.name)}
                if site.is_dir() else set())
    for rel, content in sorted(outputs.items()):
        path = cfg.root / rel
        data = content.encode("utf-8") if isinstance(content, str) else content
        current = path.read_bytes() if path.is_file() else None
        if current is not None and isinstance(content, str):
            current = current.replace(b"\r\n", b"\n")  # a CRLF checkout is not a stale page
        if current != data:
            changed.append(rel)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
    for rel in sorted(existing - set(outputs)):
        changed.append(rel)
        if not check:
            (cfg.root / rel).unlink()
    if not check and site.is_dir():
        for d in sorted((p for p in site.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
    return changed


def cmd_build(args) -> int:
    cfg = load_config(default_root())
    changed = build(cfg, check=args.check)
    if args.check:
        for rel in changed:
            print(f"stale: {rel}")
        return 1 if changed else 0
    print(f"pmdocs: {len(changed)} file(s) updated" if changed else "pmdocs: site up to date")
    return 0

# === hooks ===

BLOCK_EXIT = 10  # the git hook blocks only on this; 1 and 2 belong to uv/Python failures


def _git_dir(root: Path) -> Path:
    d = Path(git(root, "rev-parse", "--git-dir").strip())
    return d if d.is_absolute() else root / d


def _operation_in_progress(root: Path) -> bool:
    gd = _git_dir(root)
    return any((gd / m).exists() for m in
               ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"))


def repo_prefix(root: Path) -> str:
    """The doc root's path from the repository top, with a trailing slash ('' at the top)."""
    return git(root, "rev-parse", "--show-prefix").strip()


def export_index(root: Path, dest: Path, extra: list = (), nested=()) -> Path:
    """Write what the build reads — staged docs/ (minus the site), TODO.md and any
    [site] extra files, within this doc root's territory — exactly as they will be
    committed. Returns where the doc root landed: `checkout-index` writes every file at
    its repo-top path, so a doc root at apps/foo/ is exported to dest/apps/foo/."""
    files = [f for f in zsplit(git(root, "ls-files", "-z", "--", "docs", INBOX_REL))
             if not f.startswith(SITE_DIR + "/")]
    if extra:
        files += [f for f in zsplit(git(root, "ls-files", "-z"))
                  if not f.startswith("docs/") and any_match(f, extra)]
    files = [f for f in files if in_territory(f, nested)]
    if files:
        git(root, "checkout-index", f"--prefix={dest.as_posix()}/", "-z", "--stdin", input="\0".join(files))
    return dest / repo_prefix(root)


def _mirror(src: Path, dest: Path) -> list:
    """Make dest's generated files match src, leaving any other file alone.
    Returns the paths (relative to dest) that were written or deleted."""
    produced = {p.relative_to(src).as_posix(): p for p in src.rglob("*") if p.is_file()} if src.is_dir() else {}
    touched = []
    if dest.is_dir():
        for p in dest.rglob("*"):
            rel = p.relative_to(dest).as_posix()
            if p.is_file() and is_generated_file(p.name) and rel not in produced:
                p.unlink()
                touched.append(rel)
    for rel, p in sorted(produced.items()):
        target = dest / rel
        if not target.is_file() or target.read_bytes() != p.read_bytes():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
        touched.append(rel)
    return touched


def hook_pre_commit(root: Path, today: str | None = None) -> int:
    root = Path(root)
    if os.environ.get("PMDOCS_SKIP") == "1" or _operation_in_progress(root):
        return 0
    cfg = load_config(root)
    # Never stage a file the user hasn't fully staged: skip fixes on dirty or untracked files.
    blocked = frozenset(zsplit(git(root, "diff", "--name-only", "-z", "--relative"))) | frozenset(
        zsplit(git(root, "ls-files", "--others", "--exclude-standard", "-z")))
    findings, touched = apply_fixes(cfg, load_model(cfg), today or date.today().isoformat(), blocked)
    if touched:
        git(root, "add", "--", *sorted(set(touched)))
    with tempfile.TemporaryDirectory(prefix="pmdocs-") as tmpdir:
        tmp = export_index(root, Path(tmpdir), extra_patterns(cfg), cfg.nested)
        if not (tmp / CONFIG_REL).is_file():
            print(f"pmdocs: {CONFIG_REL} is not in the index yet; skipping", file=sys.stderr)
            return 0
        icfg = load_config(tmp, outside_root=root)
        icfg.nested = cfg.nested
        model = load_model(icfg)
        findings += (doc_findings(model) + staleness(cfg, changed_files(root, True, cfg.nested))
                     + coverage(cfg) + inbox_findings(model))
        report(findings, sys.stderr)
        if any(f.level == "ERROR" for f in findings):
            print("pmdocs: commit blocked. Fix the errors above, or bypass once with "
                  "PMDOCS_SKIP=1 (or git commit --no-verify).", file=sys.stderr)
            return BLOCK_EXIT
        build(icfg)
        site_paths = [f"{SITE_DIR}/{rel}" for rel in _mirror(tmp / SITE_DIR, root / SITE_DIR)]
        shutil.copyfile(tmp / ROADMAP_REL, root / ROADMAP_REL)
    # Stage exactly what the build produced or removed; pathspecs go through stdin so a
    # large site cannot overflow the Windows command line.
    git(root, "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul",
        input="\0".join([ROADMAP_REL, *site_paths]))
    return 0


def cmd_hook(args) -> int:
    if args.event == "pre-commit":
        try:
            return hook_pre_commit(default_root())
        except Exception:
            traceback.print_exc()
            print("pmdocs: hook failed; commit allowed", file=sys.stderr)
            return 2
    handler = globals().get("hook_" + args.event.replace("-", "_"))
    out = handler(sys.stdin.read(), Path.cwd()) if handler else ""
    if out:
        print(out)
    return 0

def hook_post_edit(stdin_text: str, cwd: Path) -> str:
    """Claude Code PostToolUse: tell the agent which pages cover the file it just edited."""
    try:
        data = json.loads(stdin_text)
        file_path = (data.get("tool_input") or {}).get("file_path")
        if not file_path:
            return ""
        base = Path(data.get("cwd") or cwd)
        root = own_root() or find_root(base)
        p = Path(file_path)
        p = p if p.is_absolute() else base / p
        rel = norm(os.path.relpath(p.resolve(), root.resolve()))
        cfg = load_config(root)
        if rel.startswith("../") or not in_territory(rel, cfg.nested):
            return ""  # another doc root's file: its own hook entry speaks for it
        pages = pages_for(cfg, rel)
        if not pages:
            return ""
        msg = (f"{rel} is documented in {', '.join(pages)}. "
               "If this edit changes behavior, update those pages in the same change.")
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}})
    except Exception:
        return ""


def hook_stop(stdin_text: str, cwd: Path) -> str:
    """Claude Code Stop: list stale pages and untriaged inbox items. Never blocks."""
    try:
        data = json.loads(stdin_text) if stdin_text.strip() else {}
        root = own_root() or find_root(Path(data.get("cwd") or cwd))
        cfg = load_config(root)
        label = _project_label(root, cfg)
        stale = [f"{f.where} -> {', '.join(pages_for(cfg, f.where))}"
                 for f in staleness(cfg, changed_files(root, False, cfg.nested))]
        stale_text = "docs may be stale: " + "; ".join(dict.fromkeys(stale)) if stale else ""
        n = inbox_count(root)
        waiting = len(waiting_gates(root))
        parts = [p for p in (stale_text,
                             f"{waiting} gate(s) waiting on you (docs/gates.md)" if waiting else "",
                             f"{n} inbox item(s) in TODO.md awaiting triage" if n else "") if p]
        if not parts:
            return ""
        # systemMessage is shown to the user. additionalContext re-invokes the agent, so it
        # carries only what the agent should act on (stale pages), and never on a turn that a
        # Stop hook already caused (stop_hook_active) — otherwise a persisting condition loops.
        out = {"systemMessage": f"pmdocs{label}: " + " | ".join(parts)}
        if stale_text and not data.get("stop_hook_active"):
            out["hookSpecificOutput"] = {"hookEventName": "Stop", "additionalContext": f"pmdocs{label}: " + stale_text}
        return json.dumps(out)
    except Exception:
        return ""


def _project_label(root: Path, cfg: Config) -> str:
    """' [title]' when the repository has several doc roots, so their notes can be told apart."""
    try:
        return f" [{cfg.title}]" if len(repo_doc_roots(root)) > 1 else ""
    except PmdocsError:
        return ""


def _items_in(root: Path, rel: str, head: re.Pattern) -> list:
    path = Path(root) / rel
    return parse_items(read_text(path), rel, head) if path.is_file() else []


def waiting_gates(root: Path) -> list:
    """Open gates still waiting on the user. Cheap (reads one file): hooks call it every turn."""
    return [g for g in _items_in(root, GATES_REL, GATE_HEAD) if g.status == "waiting"]


def hook_session_start(stdin_text: str, cwd: Path) -> str:
    """Claude Code SessionStart: tell the agent what is in flight — gates waiting on the user,
    backlog items in progress or blocked — so a new session starts current (D10)."""
    try:
        data = json.loads(stdin_text) if stdin_text.strip() else {}
        root = own_root() or find_root(Path(data.get("cwd") or cwd))
        lines = []
        gates = waiting_gates(root)
        if gates:
            lines.append("Waiting on the user (docs/gates.md):")
            for g in gates:
                needs = f"needs: {g.fields['Needs']}; " if g.fields.get("Needs") else ""
                lines.append(f"- {g.id} {g.title} ({needs}asked {g.fields.get('Asked', '?')})")
        active = [it for it in _items_in(root, BACKLOG_REL, ITEM_HEAD) if it.status in ("in-progress", "blocked")]
        if active:
            lines.append("In flight (docs/backlog.md):")
            for it in active:
                state = f"blocked on {it.fields['Gate']}" if it.status == "blocked" and it.fields.get("Gate") else it.status
                lines.append(f"- {it.id} {it.title} ({state})")
        n = inbox_count(root)
        if n:
            lines.append(f"{n} inbox item(s) in TODO.md awaiting triage.")
        if not lines:
            return ""
        if gates:
            lines.append("When the user gives a verdict on a gate, record their words in that gate at "
                         "once (a dated `- YYYY-MM-DD — \"…\"` line) and reference the gate by ID elsewhere.")
        label = _project_label(root, load_config(root))
        msg = f"pmdocs{label} — project status at session start:\n" + "\n".join(lines)
        return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}})
    except Exception:
        return ""


# === install-hooks ===

HOOKS_PATH = "scripts/hooks"
SETTINGS_REL = ".claude/settings.json"   # always the repository top's
# Claude Code event -> (matcher, `pmdocs hook` subcommand)
CLAUDE_HOOKS = {
    "PostToolUse": ("Edit|Write|MultiEdit", "post-edit"),
    "Stop": (None, "stop"),
    "SessionStart": (None, "session-start"),
}
OLD_TOOL_REF = '"$CLAUDE_PROJECT_DIR/scripts/pmdocs.py"'  # the command form before 0.4.0
DISPATCHER_MARKER = "this hook serves every doc root"     # text in the vendored pre-commit


def tool_ref(prefix: str) -> str:
    """How a Claude Code hook finds a doc root's tool: through git, so it works wherever
    Claude was launched in the repository (B09)."""
    return f'"$(git rev-parse --show-toplevel)/{prefix}scripts/pmdocs.py"'


def claude_command(prefix: str, sub: str) -> str:
    return f"uv run --quiet {tool_ref(prefix)} hook {sub}"


def _is_ours(command: str, prefix=None) -> bool:
    """A pmdocs hook entry — for this doc root's prefix if given, for any doc root if not."""
    if " hook " not in command:
        return False
    if prefix is None:
        return "scripts/pmdocs.py" in command
    return tool_ref(prefix) in command or (prefix == "" and OLD_TOOL_REF in command)


def repo_top(root: Path) -> Path:
    return Path(git(root, "rev-parse", "--show-toplevel").strip())


def repo_doc_roots(path: Path) -> list:
    """Every doc root in the repository, as repo-top-relative directories ('.' for the top)."""
    top = repo_top(path)
    files = zsplit(git(top, "ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    roots = {"." if f == CONFIG_REL else f[:-len("/" + CONFIG_REL)]
             for f in files if f == CONFIG_REL or f.endswith("/" + CONFIG_REL)}
    return sorted(roots)


def _load_settings(root: Path) -> dict:
    path = root / SETTINGS_REL
    if not path.is_file():
        return {}
    text = read_text(path).strip()
    if not text:
        return {}  # an empty file (touch, a truncating editor) holds nothing to protect
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # malformed JSON is a real settings file we must not overwrite
        raise PmdocsError(f"{SETTINGS_REL} is not valid JSON: {e}") from e


IGNORED_SETTINGS_WARNING = (
    f"WARNING: {SETTINGS_REL} is gitignored, so the Claude Code hooks are not shared with "
    f"other clones. To share it, ignore `.claude/*` (not `.claude/`) and add "
    f"`!{SETTINGS_REL}`: git cannot re-include a file whose parent directory is excluded.")


def settings_ignored(root: Path) -> bool:
    # Trust only the exit status of `check-ignore -q`. The -v output also prints a matching
    # *negation* pattern, so a re-included (tracked) path would look ignored.
    r = subprocess.run(["git", "check-ignore", "-q", "--", SETTINGS_REL], cwd=root,
                       capture_output=True, text=True)
    return r.returncode == 0


def _drop(hooks: dict, keep) -> bool:
    """Remove hook entries for which keep(command) is false; drop emptied groups/events."""
    changed = False
    for event in list(hooks):
        kept_groups = []
        for g in hooks[event]:
            kept = [h for h in g.get("hooks", []) if keep(h.get("command", ""))]
            changed |= len(kept) != len(g.get("hooks", []))
            if kept:
                kept_groups.append({**g, "hooks": kept})
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    return changed


def merge_claude_settings(root: Path) -> bool:
    """Register this doc root's Claude Code hooks in the repository top's settings,
    replacing any older form of them (each doc root has its own set)."""
    top, prefix = repo_top(root), repo_prefix(root)
    data = _load_settings(top)
    hooks = data.setdefault("hooks", {})
    wanted = {claude_command(prefix, sub) for _, sub in CLAUDE_HOOKS.values()}
    changed = _drop(hooks, lambda c: not _is_ours(c, prefix) or c in wanted)
    for event, (matcher, sub) in CLAUDE_HOOKS.items():
        command = claude_command(prefix, sub)
        groups = hooks.setdefault(event, [])
        if any(h.get("command") == command for g in groups for h in g.get("hooks", [])):
            continue
        group = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            group = {"matcher": matcher, **group}
        groups.append(group)
        changed = True
    if changed:
        write_text(top / SETTINGS_REL, json.dumps(data, indent=2) + "\n")
    return changed


def remove_claude_settings(root: Path) -> bool:
    top, prefix = repo_top(root), repo_prefix(root)
    data = _load_settings(top)
    hooks = data.get("hooks", {})
    changed = _drop(hooks, lambda c: not _is_ours(c, prefix))
    if "hooks" in data and not hooks:
        del data["hooks"]
    if changed:
        write_text(top / SETTINGS_REL, json.dumps(data, indent=2) + "\n")
    return changed


def _is_dispatcher(path: Path) -> bool:
    try:
        return DISPATCHER_MARKER in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _is_old_pmdocs_hook(path: Path) -> bool:
    """A vendored pmdocs hook from before the 0.4 dispatcher."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "vendored from pm-framework" in text and DISPATCHER_MARKER not in text


def install_hooks(root: Path) -> list:
    msgs = []
    hook = root / HOOKS_PATH / "pre-commit"
    if not hook.is_file():
        raise PmdocsError(f"{HOOKS_PATH}/pre-commit is missing; vendor it from the project-docs skill first")
    top = repo_top(root)
    # git resolves a relative core.hooksPath from the repository top, so point at this
    # doc root's hooks by their repo-top path (B09).
    target = repo_prefix(root) + HOOKS_PATH
    current = norm(git(root, "config", "--get", "core.hooksPath", check=False).strip()).rstrip("/")
    if not _is_dispatcher(hook):
        msgs.append(f"WARNING: {HOOKS_PATH}/pre-commit predates the pmdocs 0.4 dispatcher; re-vendor it "
                    "from the project-docs skill (the update workflow)")
    if current and current != target:
        current_hook = top / current / "pre-commit"
        if _is_dispatcher(current_hook):
            msgs.append(f"core.hooksPath stays {current}: that pmdocs hook dispatches to every doc root, "
                        "including this one")
        elif _is_old_pmdocs_hook(current_hook):
            owner = current[:-len(HOOKS_PATH)].rstrip("/") or "."
            raise PmdocsError(
                f"core.hooksPath points at {current}, a pmdocs hook from before 0.4 that checks only its "
                f"own doc root. Update the doc root at {owner} to pmdocs 0.4 or later first (the skill's "
                "update workflow), then re-run install-hooks here.")
        else:
            raise PmdocsError(
                f"core.hooksPath is already {current!r}. Either call this doc root's "
                f"`uv run {target[:-len(HOOKS_PATH)]}scripts/pmdocs.py hook pre-commit` from that pre-commit hook "
                f"(exit 10 means block the commit), or move those hooks into {target}/, unset "
                "core.hooksPath and re-run.")
    if not current:
        hooks_dir = Path(git(root, "rev-parse", "--git-path", "hooks").strip())
        hooks_dir = hooks_dir if hooks_dir.is_absolute() else root / hooks_dir
        active = sorted(p.name for p in hooks_dir.glob("*")
                        if p.is_file() and not p.name.endswith(".sample")) if hooks_dir.is_dir() else []
        if active:
            raise PmdocsError(
                f"{hooks_dir} has active hooks ({', '.join(active)}) that core.hooksPath would disable. "
                f"Move them into {target}/ (chaining pmdocs from pre-commit), then re-run.")
        git(root, "config", "core.hooksPath", target)
        msgs.append(f"core.hooksPath -> {target}")
    if os.name != "nt":
        hook.chmod(hook.stat().st_mode | 0o111)
    git(root, "add", "--", f"{HOOKS_PATH}/pre-commit")
    git(root, "update-index", "--chmod=+x", "--", f"{HOOKS_PATH}/pre-commit")
    msgs.append(f"{HOOKS_PATH}/pre-commit staged as executable")
    if merge_claude_settings(root):
        msgs.append(f"Claude Code hooks added to {SETTINGS_REL} (repository top)")
    if settings_ignored(top):
        msgs.append(IGNORED_SETTINGS_WARNING)
    return msgs


def hooks_status(root: Path) -> list:
    top, prefix = repo_top(root), repo_prefix(root)
    current = norm(git(root, "config", "--get", "core.hooksPath", check=False).strip()).rstrip("/")
    staged = git(root, "ls-files", "-s", "--", f"{HOOKS_PATH}/pre-commit").split(" ")[0]
    hook_state = {"100755": "executable in git", "100644": "NOT executable in git", "": "not in git"}.get(staged, staged)
    ours = any(_is_ours(h.get("command", ""), prefix)
               for groups in _load_settings(top).get("hooks", {}).values()
               for g in groups for h in g.get("hooks", []))
    lines = [f"core.hooksPath: {current or '(unset)'}",
             f"{HOOKS_PATH}/pre-commit: {hook_state}",
             f"Claude Code hooks: {'installed' if ours else 'missing'}",
             "pre-commit covers doc roots: " + ", ".join(repo_doc_roots(root))]
    if current and not (top / current / "pre-commit").is_file():
        lines.append(f"WARNING: core.hooksPath {current} has no pre-commit hook, so no doc root is checked")
    if settings_ignored(top):
        lines.append(IGNORED_SETTINGS_WARNING)
    return lines


def uninstall_hooks(root: Path) -> list:
    msgs = []
    current = norm(git(root, "config", "--get", "core.hooksPath", check=False).strip()).rstrip("/")
    if current == repo_prefix(root) + HOOKS_PATH:
        if len(repo_doc_roots(root)) > 1:
            msgs.append(f"core.hooksPath left at {current}: other doc roots in this repository use it")
        else:
            git(root, "config", "--unset", "core.hooksPath")
            msgs.append("core.hooksPath unset")
    if remove_claude_settings(root):
        msgs.append(f"Claude Code hooks removed from {SETTINGS_REL}")
    return msgs


def cmd_install_hooks(args) -> int:
    root = default_root()
    if args.status:
        lines = hooks_status(root)
    elif args.uninstall:
        lines = uninstall_hooks(root) or ["nothing to uninstall"]
    else:
        lines = install_hooks(root)
    for line in lines:
        print(line)
    return 0

# === cli ===

def cmd_version(args) -> int:
    print(f"pmdocs {VERSION}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pmdocs", description="Docs and work-status tooling (pm-framework).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version", help="print the vendored version")
    b = sub.add_parser("build", help="render docs/site/ and docs/roadmap.md")
    b.add_argument("--check", action="store_true", help="write nothing; exit 1 if anything is stale")
    c = sub.add_parser("check", help="validate docs, drift and staleness")
    c.add_argument("--staged", action="store_true", help="staleness against the index instead of the working tree")
    c.add_argument("--fix", action="store_true", help="apply mechanical fixes")
    h = sub.add_parser("hook", help="entry points for the git and Claude Code hooks")
    h.add_argument("event", choices=["pre-commit", "post-edit", "stop", "session-start"])
    i = sub.add_parser("install-hooks", help="point git at scripts/hooks and register Claude Code hooks")
    g = i.add_mutually_exclusive_group()
    g.add_argument("--status", action="store_true")
    g.add_argument("--uninstall", action="store_true")
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
        except Exception:
            pass  # not a reconfigurable stream (e.g. under pytest capture)
    args = build_parser().parse_args(argv)
    handler = globals().get("cmd_" + args.cmd.replace("-", "_"))
    if handler is None:
        print(f"pmdocs: '{args.cmd}' is not implemented", file=sys.stderr)
        return 2
    try:
        return handler(args)
    except PmdocsError as e:
        print(f"pmdocs: {e}", file=sys.stderr)
        return 2
    except Exception:
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
