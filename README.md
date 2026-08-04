# Copyist

**Turns what you played in a DAW into a score somebody actually wants to read.**

You compose in a DAW. You play the parts in by hand, because that is how the
music happens. Then you export MIDI, import it into MuseScore, and the page is
unreadable — 64th rests everywhere, absurd tied rhythms, accidentals fighting
the key, both hands crammed onto one staff and the clef flipping mid-bar to
cope.

Copyist sits between those two steps.

It is built accessibility-first, by and for a blind composer, on a premise that
turns out to make the tool better for everyone: **you cannot proofread a page
you cannot see.** So Copyist tells you in text what is wrong with the score,
lets you check it by ear, and verifies its own output rather than asking you to
look.

> **Status: early prototype.** The engine converts real MIDI to real MusicXML
> and verifies itself, but large parts of [DESIGN.md](DESIGN.md) are not built
> yet. Not ready for daily use.

## What makes it different

**It emits MusicXML, not MIDI.** MIDI cannot express voices, spelling, staff
assignment, dynamics, articulation or pedal — so a MIDI-based workflow asks the
notation program to invent all of it, and it invents badly. That single change
fixes most of the problem before any clever algorithm runs.

**Gate time means articulation, never rests.** Releasing a key 70 ms early is
not a 64th rest. It is a staccato dot. This one rule removes most of the visual
noise from a hand-played part.

**Hands are separated by physics, not by a pitch split point.** Hand span,
movement cost and continuity — so crossings come out right, because crossing is
physically cheap when the hands are already close. A fixed split at middle C
gets that wrong every time.

**The output is a chart, not a transcription.** Every other tool in this space
maximizes fidelity. That is the wrong goal when the reader is a collaborator who
will interpret the part. Copyist can deliberately discard detail — slashes,
chord symbols, "groove as demo" — because for that reader, less is often better.

**It reports what it did, and what it is unsure about.** Severity-first, each
finding carrying the settings change that would fix it, each suppressible so the
second run is quieter than the first.

**It verifies itself.** Output is rendered back to MIDI and diffed against the
original performance. During development this caught a bug that lost 33 notes
while the rendered page still looked perfect.

## Try the prototype

No dependencies — the MIDI parser is self-contained, so stock Python 3 is enough.

```bash
python3 prototype/analyze.py yourfile.mid
```

```bash
python3 prototype/convert.py yourfile.mid -o out.musicxml --key "C# minor"
```

`analyze` reports what it found: the timing grid, whether the file was played
live or quantized-then-humanized, key estimate with confidence, texture, hand
span evidence, markers, pedal. `convert` writes MusicXML and prints its
findings.

## Verified results

On the included fixture — ten bars of two-hand piano, 110 notes:

| | Result |
|---|---|
| Round-trip note accuracy | **100%** onset and pitch |
| Phantom rests removed | 42 |
| Clef changes | **0** (a plain MIDI import of comparable material produces six or more, mid-bar) |
| Humanized input vs click-locked input | **byte-identical output**, though humanize shatters every chord into separate events |

The fixture is synthetic so that the corpus carries no private material, but it
was built to reproduce pathologies measured on real DAW exports — including the
finding that REAPER's humanize moves notes independently and therefore breaks
chords apart, which is reversible once you know to look for it (DESIGN.md §7.5.1).

## Documentation

- **[DESIGN.md](DESIGN.md)** — the full design. Twenty-one sections, twenty
  locked decisions, ten open questions. Read this before proposing anything.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — the rules, accessibility first.
- **[corpus/](corpus/)** — test fixtures. Every bug becomes one of these.

## License

MIT for the engine. Instrument data derived from MuseScore is GPL-3 and will
live in a separate optional package, so the core stays reusable by anyone —
including commercial notation tools. See DESIGN.md §17.
