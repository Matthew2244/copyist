# Contributing to Copyist

## Three rules, in order

**1. Nothing may require sight.**

Every feature must be fully usable by someone who cannot see the screen. If a
capability exists only as something to look at, it is not finished. In practice:
findings are text, verification is by ear or by diff, and any claim the tool
makes about a score must be readable rather than rendered.

This is not a nice-to-have bolted on afterwards. It is why the project exists,
and it is the reason the tool is better for sighted users too — a program that
can explain its own output is more useful than one that just produces it.

**2. Never guess silently.**

Below a confidence threshold, ask, or record a finding, or mark it in the score.
Silently guessing wrong is the failure mode of every existing tool in this
space, and it is worse than admitting uncertainty because the user has no way to
know it happened.

**3. Calibrate thresholds, don't pick them.**

Any statistic that gates a decision must be tested against its null hypothesis
by simulation, at analysis time, on the actual data. A threshold chosen by
intuition is how a tool ends up confidently wrong — this already happened once
here, and the write-up is in DESIGN.md §7.5.2. Report percentiles, not
constants.

## Before you write code

Read [DESIGN.md](DESIGN.md). Decisions D1–D20 are settled; open questions are
O1–O10. If you want to change a settled decision, open an issue arguing the case
rather than a PR implementing it.

## Every bug becomes a fixture

`corpus/` holds paired inputs and expected outputs. When you fix a bug, add the
MIDI that triggered it. CI runs the whole corpus on every PR, so a fix that
isn't in the corpus isn't protected.

```bash
python3 prototype/test_corpus.py
```

Fixture MIDI must be material you have the right to publish. Short excerpts are
better than whole pieces — the goal is to reproduce a pathology, not to archive
music.

## Verification is not optional

If you change the conversion path, round-trip it. Render the output back to MIDI
and diff against the source performance. A change that looks right on the page
and loses notes is the exact failure this project is built to catch, and it has
already happened once.

## Style

Match the surrounding code. The prototype has no dependencies on purpose —
stock Python 3 runs it, including the MIDI parser. Keep it that way until the
Rust port, so anyone can run it without a build step.

Comments reference the design section they implement (`# 7.3 — gate time
becomes articulation`). That link is load-bearing; keep it accurate when you
move code.
