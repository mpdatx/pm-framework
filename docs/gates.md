---
title: Waiting on you
summary: Questions only the user can answer — a look, a listen, an approval, a decision — and their verdicts.
---

# Waiting on you

A gate is a question the work can't settle by itself: an in-person check, a listening
pass, an A/B choice, an approval, a decision. Each is one record; everything else refers
to it by ID rather than restating it. Answered and dropped gates move to the
[archive](gates-archive.md), verdicts and all.

    ## G04. The question, as the user will read it
    Status: waiting · Asked: YYYY-MM-DD · For: B03 · Needs: what must be true to answer it

    Setup: exactly what to look at or run, and how.
    Passes if: what a "yes" looks like.
    Evidence: paths to the build, render, demo or log.

    ### Verdicts

    - YYYY-MM-DD — "the user's words, verbatim" — pass / fail / unclear. Checked: preconditions.

`Status` (waiting, answered, dropped) and `Asked` are required. To retract a verdict, add
a new dated line saying what is withdrawn and set the gate back to `waiting`; never edit
an old verdict.
