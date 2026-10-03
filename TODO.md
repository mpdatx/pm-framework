# TODO

<!-- Inbox: jot anything here, any format, any time. The project-docs triage workflow
     turns items into backlog entries (docs/backlog.md) with you, then removes them. -->

- noted during the 0.4.0 review: a nested doc root whose docs/pmdocs.toml isn't committed yet is excluded from the outer root's territory but not run by the dispatcher (which lists only tracked roots), so its files commit unchecked until the toml is staged; `install-hooks --status` should mark such roots "not yet committed"
- noted during the 0.4.0 review: the dispatcher runs an umbrella (top) doc root on every commit, even one touching only a nested package — harmless but slower; could exclude nested roots from its `git diff --cached --quiet` pathspec
- noted during the 0.4.0 review: every PostToolUse/Stop/SessionStart scans the whole repo for untracked files (nested-root discovery, project label) — consider caching or tracked-only discovery for large monorepos
- noted during the 0.4.0 review: `leaves_root` misses an interior `..` (e.g. `docs/../../x`); normalise with posixpath.normpath before checking
