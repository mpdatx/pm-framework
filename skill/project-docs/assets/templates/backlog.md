---
title: Backlog
summary: Open work. Closed items move to the archive.
order: 90
---

# Backlog

Each item is `## Bnn. Title` followed by one line, then free prose:

    Status: open · Added: YYYY-MM-DD · Spec: superpowers/specs/… · Source: TODO.md

`Status` and `Added` are required. Statuses: open, in-progress, blocked, done, dropped.
Done and dropped items are moved to the [archive](backlog-archive.md) by the pre-commit
hook. IDs are never reused.
