import pmdocs

BACKLOG = """---
title: Backlog
---

# Backlog

## B01. First thing
Status: open · Added: 2026-09-01

Why it matters.

## B7. Second thing
Status: in-progress | Spec: superpowers/specs/2026-09-02-x-design.md | Added: 2026-09-02

## Notes
Not an item.
"""


def test_parse_items():
    items = pmdocs.parse_items(BACKLOG, "docs/backlog.md")
    assert [i.id for i in items] == ["B01", "B7"]
    assert [i.key for i in items] == ["B1", "B7"]
    first, second = items
    assert first.title == "First thing"
    assert first.fields == {"Status": "open", "Added": "2026-09-01"}
    assert second.status == "in-progress"
    assert second.fields["Spec"] == "superpowers/specs/2026-09-02-x-design.md"
    lines = BACKLOG.split("\n")
    assert lines[first.start] == "## B01. First thing"
    assert lines[first.meta_line] == "Status: open · Added: 2026-09-01"
    assert lines[first.end] == "## B7. Second thing"
    assert lines[second.end] == "## Notes"


def test_item_without_meta_line():
    [it] = pmdocs.parse_items("## B03. Bare\n\nJust prose.\n", "docs/backlog.md")
    assert it.meta_line is None and it.fields == {} and it.status is None


def test_status_is_lowercased():
    [it] = pmdocs.parse_items("## B01. X\nStatus: Done · Added: 2026-09-01\n", "f")
    assert it.status == "done"


def test_decisions_parse():
    [d] = pmdocs.parse_items("## D12. Use uv\nStatus: superseded by D14\n\nContext.\n",
                             "docs/decisions.md", pmdocs.DECISION_HEAD)
    assert d.key == "D12" and d.fields["Status"] == "superseded by D14"


def test_id_key():
    assert pmdocs.id_key("B007") == "B7"
    assert pmdocs.id_key(" D3 ") == "D3"
    assert pmdocs.id_key("weird") == "weird"


def test_next_id():
    items = pmdocs.parse_items(BACKLOG, "docs/backlog.md")
    assert pmdocs.next_id(items) == "B08"
    assert pmdocs.next_id([]) == "B01"


def test_inbox_counts_top_level_list_items():
    text = "# TODO\n\n- one\n  - nested detail\n- [ ] two\n* three\n1. four\n"
    assert pmdocs.count_inbox(text) == 4


def test_inbox_counts_paragraphs_when_no_list_and_no_headings():
    assert pmdocs.count_inbox("fix the thing\nsoon\n\nanother idea\n") == 2


def test_inbox_paragraphs_under_the_title_alone_are_intro():
    # 0.3.1 still counted a description sentence directly under `# TODO`
    assert pmdocs.count_inbox("# TODO\n\nA scratch inbox; jot anything here.\n") == 0
    assert pmdocs.count_inbox("# TODO\n\nfix the thing\n\nanother idea\n") == 0


def test_inbox_counts_paragraphs_after_the_first_section_heading():
    text = "# TODO\n\nA description of this file.\n\n## Soon\n\nfix the thing\n\nanother idea\n"
    assert pmdocs.count_inbox(text) == 2


def test_inbox_without_a_title_its_first_heading_is_a_section():
    assert pmdocs.count_inbox("## Soon\n\nfix the thing\n") == 1


def test_inbox_template_is_empty():
    text = ("# TODO\n\n<!-- Inbox: jot anything here, any format.\n"
            "     - not an item -->\n")
    assert pmdocs.count_inbox(text) == 0


def test_inbox_of_only_headings_intro_and_rules_is_empty():
    # the reported phantom: no list items, so paragraphs were counted — including the
    # intro above the first heading and the --- rules
    text = ("This file is my scratch inbox. Jot anything here.\n\n---\n\n"
            "# TODO\n\n***\n\n## Soon\n\n___\n\n## Later\n")
    assert pmdocs.count_inbox(text) == 0


def test_inbox_counts_paragraphs_only_after_the_first_section():
    text = ("Intro paragraph, not an item.\n\n# TODO\n\nDescription, not an item.\n\n"
            "## Ideas\n\nfix the thing\n\n---\n\nanother idea\n")
    assert pmdocs.count_inbox(text) == 2


def test_inbox_ignores_bullets_inside_code_blocks():
    text = "# TODO\n\n```\n- not an item\n- nor this\n```\n\n- a real item\n"
    assert pmdocs.count_inbox(text) == 1


def test_inbox_setext_heading_is_a_heading_not_an_item():
    assert pmdocs.count_inbox("TODO\n----\n\n") == 0


def test_inbox_crlf():
    assert pmdocs.count_inbox("- a\r\n- b\r\n") == 2
