# Copyist — Design

**Status:** working prototype. Engine, both GUIs and the corpus are real; see
§22 for exactly what is built and what is not.
**Last updated:** 2026-08-04

---

## 1. What Copyist is

You compose in a DAW. You play parts in by hand, because that is how the music
actually happens. Then you export MIDI, import it into MuseScore, and the page
is unreadable — 64th rests everywhere, absurd tied rhythms, accidentals fighting
the key, both hands crammed onto one staff.

Copyist sits between those two steps. It reads what you played and writes a
score a musician would actually want to read.

It is built accessibility-first, by and for a blind composer, on the premise
that **you cannot proofread a page you cannot see** — so the tool has to tell
you what is wrong with it, in text, and let you verify by ear.

**And the output is a chart, not a transcription.** See §11 — this is the
single thing that most distinguishes Copyist from every other tool in this
space.

---

## 2. Why MIDI-to-notation looks terrible

MIDI stores four things: pitch number, note-on time, note-off time, velocity.
Everything a score needs, the importing program has to invent — and it invents
badly.

| What a score needs | What MIDI has | What goes wrong |
|---|---|---|
| Note values | Gate times | A quarter held 94% becomes a quarter tied to a 64th |
| On-grid onsets | Human timing | A note 9 ticks early becomes a rest, a tie, and a dotted mess |
| Pitch spelling | Note numbers | MIDI 61 is neither C♯ nor D♭; the importer guesses |
| Voices and staves | One flat stream | Fixed split point at C4; crossed hands land on the wrong staff |
| Dynamics, articulation | Velocity | Discarded entirely |
| Pedal marks | CC64 | Ignored, or turned into held notes |
| Written pitch | Concert pitch | Transposing instruments come out unplayable |
| Chord symbols, form | Nothing | Not representable at all |

None of this is fixable *inside* MIDI. Which leads to the first and largest
decision.

---

## 3. The core architectural decision

**Copyist emits MusicXML, not MIDI.**

MusicXML can express voices, spelling, staff assignment, clefs, beaming,
tuplets, grace notes, dynamics, articulations, pedal lines, chord symbols,
slash regions, rehearsal marks, cue-sized annotations — every single thing in
the table above. MuseScore's MusicXML importer is also dramatically better than
its MIDI importer.

That one change fixes most of the problem before a single clever algorithm
runs. Everything else in this document is refinement on top of it.

REAPER has no MusicXML export, native or otherwise. This fills a real hole.

---

## 4. Design principles

1. **The output is a chart, not a transcription.** The reader is a collaborator
   who will interpret it, not a machine reproducing it. Deliberately discarding
   detail is a feature, not a loss. See §11.
2. **Don't change how you compose.** The tool adapts to the performance, not
   the reverse. Anything that asks the composer to play differently has failed.
3. **Never silently guess.** Below a confidence threshold, either ask, or mark
   it in the findings *and* in the score. Silent wrong guesses are the existing
   tools' entire failure mode.
4. **Everything verifiable without sight.** Every claim the tool makes is
   readable as text or checkable by ear. No feature may require looking at a
   rendered page.
5. **Explain every decision.** Any bar, any note: why does it look like that,
   and what setting would change it.
6. **Non-destructive and reproducible.** Original in, new file out, always.
   Settings recorded alongside the output. Same input plus same profile equals
   byte-identical output.
7. **The engine is a library.** No UI assumptions anywhere in the core.

---

## 5. Architecture

```
core/       pure library — no UI, no I/O assumptions, no globals
cli/        thin wrapper over core
gui/
  macos/    SwiftUI
  windows/  WinUI
mcp/        later — same JSON-RPC surface as the GUI uses
profiles/   shipped presets
corpus/     test fixtures (see §16)
```

### 5.1 GUI: native per-platform

**Decided.** SwiftUI on macOS, WinUI on Windows. Real VoiceOver and real NVDA
behavior, not a webview's approximation.

The usual objection to native-per-platform is the cost of rebuilding a custom
canvas twice. Copyist has no canvas. The entire UI is:

- File picker
- Analysis read-back (table)
- Ambiguity questions (form)
- Detail-level settings, per instrument (form)
- A/B audition (transport: play, stop, prev section, next section)
- Findings list (list → detail)
- Settings and export (form + button)

Lists, tables, forms, a transport. Zero custom drawing. Both toolkits are
excellent at exactly this with first-class accessibility out of the box, so the
two codebases stay genuinely thin.

**Copyist does not render notation.** The score opens in MuseScore. Copyist's
job is everything before that.

### 5.2 Two thin UIs make the protocol load-bearing

Engine and UI talk over JSON-RPC. The protocol is not "process this file" — it
is a session model: analysis results, open questions, proposed settings,
findings, audition requests, locks. If the protocol is right, both UIs are thin
and the MCP server is nearly free.

### 5.3 Language: prototype in Python, ship in Rust

Native UIs on both platforms mean the engine must be callable from Swift and
C#. Bundling a Python runtime inside a signed, notarized `.app` *and* a Windows
installer is real ongoing pain. A Rust core with a C ABI is one ~5 MB library —
Swift calls it directly, C# via P/Invoke.

But the algorithms need fast iteration to get right, and Python has the
research ecosystem (`partitura`, `music21`, `mido`) plus reference
implementations to diff against.

**So: research bench in Python, shipped engine in Rust.** Get quantization,
spelling and stream separation correct in Python against the corpus. Port once
they stop changing. The corpus is what makes the port safe — identical output
on every fixture, or the port isn't done.

Note what `partitura` was actually saving: MusicXML *reading*, which is the
genuinely awful part and which Copyist barely needs. Copyist mostly writes.

---

## 6. Pipeline

1. Parse MIDI; read tempo map, meter, track names, program changes, markers
2. **Classify the timing** — humanized, click-locked, or free tempo (§7.5)
3. Establish the metric grid — downbeats, meter, swing ratio
4. **Quantize onsets** (§7)
5. **Stream separation** — hands, voices (§8)
6. **Staff assignment and engraving layer** (§8.5)
7. Quantize durations → articulation (§7.3)
8. **Pitch spelling** (§9)
9. Grace notes and ornaments
10. Velocity → dynamics; CC64 → pedal lines. **Normalize velocity to the
    piece's own distribution, never to absolute MIDI values** — a verified file
    here spans 14–84, which read absolutely would mark an entire expressive
    performance as *pp* to *mp*. Dynamics are relative to the music, not to the
    protocol.
11. Instrument resolution, transposition to written pitch, range check (§10)
12. **Harmony and annotations** — chord symbols, sections, fills (§12)
13. **Detail-level reduction**, per instrument (§11)
14. Emit MusicXML
15. Emit findings (§15)

Note that reduction (13) happens *late*, after everything is understood. You
cannot decide a bar should be four slashes until you know what is in it.

---

## 7. Quantization

### 7.1 What everyone else does, and why it fails

Snap each onset to the nearest grid line; snap each duration to the nearest
note value. Notes are treated independently and there is no model of what is
musically plausible. That is the whole reason the output is ugly.

### 7.2 Score whole beats, not individual notes

For each beat, enumerate candidate notations and choose the cheapest by three
costs:

**Fidelity** — how far notes moved from where they were actually played.

**Complexity** — an explicit notation-cost model:

| Notation | Cost |
|---|---|
| Quarter, eighth | cheap |
| Dotted eighth | cheapish |
| 32nd tied across a beat | expensive |
| 64th rest | very expensive |
| Tuplet | fixed setup cost + per-note cost |

The tuplet's fixed cost means it only wins when it genuinely explains the
passage, rather than appearing as noise.

**Consistency** — if the last seven bars were straight eighths, eighths get
cheaper and 32nds get more expensive. Established patterns are sticky.

Minimize total cost by shortest-path search over the beat. Small search space,
fast, and it produces notation *a human would have written* rather than a
mathematically-nearest transcription.

### 7.2.1 Choose the grid per beat, not per piece

This is why existing tools fail on mixed material: you must pick "16th" up
front and every triplet in the piece is mangled. Copyist hypothesizes per beat
and lets the consistency cost keep it stable.

### 7.3 Durations are a different problem — they mean articulation

Quantize onsets first. A note's **slot** then runs from its onset to the next
onset in the same stream. Gate time within that slot maps to articulation, not
to note value:

| Gate / slot | Result |
|---|---|
| > 90% | full value, slur or legato |
| 45–90% | full value, no marking — normal playing |
| 25–45% | full value + staccato |
| < 25% | full value + staccatissimo |

**Rule: never write a rest the player did not intend.** Orphan 32nd and 64th
rests are just a key released slightly early. They become a staccato dot.

This single rule kills the majority of the ugliness.

### 7.4 Three more rules

- **Anything quantizing to zero duration becomes a grace note, never a
  deletion.** Notes under roughly a third of the smallest grid unit sitting
  immediately before another onset are grace notes.
- **Detect swing before quantizing.** Measure where off-beat eighths land
  across the piece. Clustering around 62–70% of the beat means swing: notate
  straight eighths and add a "Swing" instruction. Quantizing swung eighths to a
  16th grid yields dotted-eighth-sixteenth on every beat — wrong *and*
  unreadable.
- **Free tempo is a separate, gated path.** See §7.5.

### 7.5 Timing classification — the humanize shortcut

Matthew's normal workflow is: record to a click, **quantize, then apply
REAPER's humanize**. This is enormously important, because those offsets are
not playing — they are synthetic noise on top of a grid that is *exactly*
known.

Three cases to distinguish, and they are statistically separable:

| Case | Signature | Consequence |
|---|---|---|
| **Quantized + humanized** | Residuals independent, zero-mean, **no autocorrelation**, and *identical at every metrical position* | Grid is exact. Snap to it. Quantization is free and 100% correct — skip §7.2 entirely |
| **Click-locked live playing** | Residuals structured: phrase-level drift, agogic weight on downbeats, systematic lateness on weak beats | Grid is known; run the §7.2 cost model |
| **Free tempo** | No stable grid at all | Requires beat tracking and meter inference (§7.6) |

The analyze pass reports which case it sees, with the measured parameters. It
never guesses silently.

### 7.5.1 Measured facts about REAPER's humanize

Verified by running the *same ten bars* twice, click-locked and humanized:

- **The offsets are gaussian, not uniform** — measured sd/peak ratio 0.64,
  where uniform would be 1.0. An earlier draft of this document said uniform;
  that was wrong.
- **It moves every note independently.** A three-note chord becomes three
  onsets up to 67 ms apart: the file went from **37 unique onsets to 121**.
  *This* is the real damage — a notation program sees three separate events
  where the player struck one chord.
- **It does not touch note lengths.** The gate-time distributions of the two
  files are identical (median 70.8 ms early, p95 132.1 ms). The sloppy
  releases are the playing, not the plugin. An earlier draft blamed humanize
  for the phantom rests; it does not cause them.

**So the fix is onset re-clustering, not offset subtraction.** Snap onsets to
the detected grid before grouping into chords. Verified end to end: Copyist's
output from the humanized file is **byte-identical** to its output from the
click-locked file, and round-trips to the clean original at 100% — even though
the two MIDI files agree on only 2.3% of onsets.

### 7.5.2 The discriminator must self-calibrate

The test that separates humanize from real playing is **whether deviation
depends on metrical position** — a human is systematically early on downbeats
and late on weak beats; a randomizer treats every slot in the bar identically.

But the raw statistic is **not comparable across files**. Its distribution
depends on note count and on how onsets happen to fall across slots. Measured
on this material, pure gaussian noise produced a median statistic of **3.31**,
not the 1.0 the formula's construction suggests, with a 95th percentile of
5.47. A fixed threshold picked by intuition would have misclassified every
file.

So the engine runs the null hypothesis **at analysis time**: take the file's
own grid positions, jitter them with the file's own measured sd, and see what
pure noise scores. The verdict is a percentile against that simulation, not a
magic constant. The humanized file lands at the 30th percentile of its own null
distribution — comfortably indistinguishable from noise, which is the correct
answer.

Any future statistic in Copyist gets the same treatment. Thresholds chosen by
eye are how a tool ends up confidently wrong.

### 7.6 Free tempo

Sometimes the vibe calls for no click. This is a real requirement, but a
**secondary, gated path**: beat tracking and meter inference are an open
research problem and must not block v1.

Design the seam now, build it after. Until it exists, the analyze pass detects
the case and says honestly that it cannot help yet, rather than producing
garbage.

---

## 8. Stream separation

Framed generally as **N-stream separation with instrument-specific
constraints**, not "piano hand splitting" — so "every instrument" stays true
instead of becoming piano plus a pile of special cases.

| Instrument | Streams | Constraint |
|---|---|---|
| Piano | 2 | hand span |
| Organ | 3 | two hands + feet; pedal notes are low, long, rarely fast — the easiest case |
| Harp | 2 | much wider span |
| Marimba, vibes | 2 | up to 4 mallets, span limited by mallet spread |
| Guitar | n/a | different problem: string and position assignment |

Same DP machinery, different constraint parameters, loaded from the instrument
profile.

### 8.1 Pitch ranges do not solve this

A fixed split point fails whenever hands cross. Overlapping per-hand ranges are
better, but they only *name* the ambiguous region — inside the overlap you
still need a tiebreak, and outside it you did not need the ranges.

So ranges are a **prior**, not a decision procedure: a cost nudge that strong
evidence can override. The composer's knowledge of the piece helps without ever
hard-blocking a legitimate crossing.

### 8.2 What actually separates hands is physics

- **Span.** Notes sounding together beyond the player's reach are two hands.
- **Continuity.** A hand cannot teleport. A twelfth in 80 ms is expensive; the
  same twelfth in 800 ms is free.
- **Persistence.** Hands stay put. Reassigning mid-phrase costs something.

Minimize total movement cost across the piece — a DP/HMM pass, structurally the
same as the quantizer's beat search. Crossings fall out *correctly*, because
when the hands are already close a crossing is physically cheap. A pitch split
gets that case wrong every time; a physics model gets it right for the same
reason the hands could do it.

Established work. Nakamura's merged-output HMM is the reference approach, with
reported error of **1.4% to 18.7% depending on the piece** — near-perfect on
straightforward textures, meaningfully wrong on dense ones with heavy crossing.
That spread is the argument for §8.4.

### 8.3 Hand span is a property of the player, not the song

Matthew reaches **C to F — an eleventh**, well past the octave a textbook model
assumes. A model tuned to an octave would read a wide chord he plays
comfortably with one hand as necessarily two hands, invent a crossing that
never happened, and do it most often on exactly the open-voiced writing he
reaches for *because* he can play it.

So span lives in the **user profile**, set once, applied to everything.

**Soft cost, not a hard cutoff.** Two values — *comfortable reach* and
*maximum reach* — with a rising cost curve between them and impossibility
beyond. That way a tenth in a fast passage reads as slightly suspicious while a
tenth in a held chord reads as normal, which is how a hand actually works. A
hard cutoff cannot express that difference.

Left and right are separate parameters. Matthew's are equal; many people's are
not.

**Calibrate by playing, not typing.** Onboarding is: *"Play the widest interval
you can reach comfortably with your right hand. Now the widest you can reach at
all."* Four notes, five seconds. Copyist can also infer it passively from a
folder of existing MIDI — the widest intervals recurring as simultaneous onsets
in unambiguously-one-hand contexts *are* the player's reach, measured from real
playing.

### 8.4 Three tiers, one mechanism

| Source | Confidence | Role |
|---|---|---|
| Two named tracks ("LH"/"RH") | 100% | Ground truth; inference skipped entirely |
| Per-song range hints | prior | Cost nudge, overridable by evidence |
| Span + movement model | per-note | The actual decision |

**Copyist supports separate hand tracks and never requires them.** Recording
hands separately would contort the creative process to serve the tool, which is
the thing this project exists to escape. But when the information is there for
free, take it.

Given 18.7% is a real possibility, the fourth tier matters most: **anywhere
confidence is low, it goes in the findings.** The composer listens, decides,
locks it, and the decision persists in the song sidecar across every future
re-run.

A wider reach means more configurations are physically possible for one hand,
so more notes are genuinely ambiguous, so low-confidence findings will be more
frequent for Matthew than for an average-handed player. Not a flaw — honest
uncertainty — but it means the listen-and-lock workflow carries real weight.

### 8.5 Hand ≠ staff

Two separate questions, and conflating them is a bug:

- **Who played it** — the physics model above.
- **Where it is printed** — a separate engraving layer: staff assignment,
  ledger lines vs. crossing the staff, when to use `8va`, when a cross-staff
  beam beats a pile of ledger lines.

A left-hand eleventh may well be notated with its top note in the treble staff.
That is correct engraving *and* correct hand assignment simultaneously — only
possible because the decisions are separate. Most tools conflate them, which is
another reason their output reads badly.

---

## 9. Pitch spelling

Implement **ps13** (Meredith). Two stages: assign pitch names by local key, then
correct names that produce poor voice-leading.

Reported 99.3% correct on a 1.73-million-note corpus, beating Temperley,
Cambouropoulos, Longuet-Higgins and Chew & Chen on both clean *and* noisy
input. Noisy is our case.

Key detection feeds it, and key is one of the few things worth *asking* about
when ambiguous (E♭ major vs. C minor is a coin-flip the composer can settle
instantly). A chord track (§12.1), when present, is a strong additional signal.

---

## 10. Instruments — every instrument

### 10.1 Fuse three open data sources

**MuseScore `instruments.xml`** — several hundred instruments with default
clef(s), staff count, amateur and professional ranges, `transposeDiatonic` /
`transposeChromatic`, and GM program. The most complete open instrument
database that exists. *GPL-3 — see §17.*

**MusicXML Standard Sounds (`sounds.xml`)** — the W3C's ~700 portable sound IDs
(`wind.reed.clarinet.bflat`). Emitted in `<instrument-sound>` so Dorico,
Sibelius and Finale recognize the instrument too, not just MuseScore. This is
the interoperability layer.

**GM / GM2 program map** — fallback when a track has no useful name.

### 10.2 Resolution chain

Track name → **plugin-name alias table** → fuzzy match against the database →
GM program as tiebreak → instrument record.

The alias table is not optional. Real exports name the track after the *plugin*,
not the instrument — a verified file here has its piano track named
`Pianoteq 9`, and there is no GM program event at all because the sound came
from a VST. Kontakt, Omnisphere, Serum, Addictive Drums and friends all produce
the same problem. Without aliasing, every VST-sourced track falls through to
"unknown instrument."

### 10.3 What the record drives

- **Written vs. sounding pitch.** MIDI is concert pitch. B♭ trumpet is written
  up a major second, alto sax up a major sixth. Get this wrong and the part is
  unplayable — and it is invisible to a blind composer unless the tool says so.
- **Clef, including the awkward cases.** Octave-down treble for tenor voice and
  guitar; bass↔tenor clef changes for cello, bassoon, trombone.
- **Range checking.** *"Bar 34, horn: written F6, above professional range."*
  Straight into the findings. Nobody else reports this.
- **Percussion routing.** GM drum map → percussion staff, correct noteheads,
  entirely separate code path.
- **Default detail level.** Rhythm section instruments default to slashes;
  melodic instruments default to full notation (§11).

### 10.4 User-definable

Instrument profile is a first-class, user-definable type — covering scordatura,
custom drum maps, and whatever obscure instrument someone shows up with.

---

## 11. Detail level — how much to tell them

**This is the section that most distinguishes Copyist.**

Every MIDI-to-notation tool ever built maximizes fidelity: reproduce the
performance as exactly as possible. That is the wrong goal here.

Matthew's own framing, to every collaborator who hears a demo:

> *"Do you. My demos are the foundation, but do your thing. I wanna hear your
> voice, your sound."*

The deliverable is a **chart a musician interprets**, not a transcription a
machine reproduces. A part that notates every 32nd of a placeholder groove is
*actively worse* for that purpose than one reading "Cm7, four bars, groove as
demo." It over-specifies, and over-specification reads as instruction.

So detail level is a first-class axis, set **per instrument**, and lower is
frequently the better answer:

| Level | Output |
|---|---|
| **Full** | Everything notated — pitches, rhythm, articulation, dynamics |
| **Simplified** | Rhythmic detail smoothed to the phrase level; ornament noise dropped |
| **Rhythmic slashes** | Chord symbols above, notated rhythm as slashes — the groove, not the voicing |
| **Slashes** | Chord symbols above, plain slashes — the harmony and the bars, nothing else |
| **Symbols only** | Chord symbols and bar count. *"×4, as demo"* |

Typical chart: melody **full**, keys and guitar on **rhythmic slashes**, bass
**simplified**, drums **symbols only** with "groove as demo, fills ad lib."

### 11.1 Consequences

- **Reduction runs late** in the pipeline (step 13), after everything is
  understood. You cannot decide a bar becomes four slashes until you know what
  is in it — and the chord symbols above those slashes come from that
  understanding.
- **Detail level suppresses findings.** "Bar 22 has messy 16th rests" is
  irrelevant when bar 22 is going to be four slashes. Findings are filtered by
  the detail level of the instrument they belong to, which makes the list
  dramatically shorter and more honest.
- **Detail level is per-song-per-instrument state**, stored in the sidecar
  (§14), with defaults from the instrument profile.
- **Fills and solos are regions**, not detail levels — see §12.3.

### 11.2 Evidence from a real chart

Measured on a real project from the author's catalogue, kept out of the public
corpus: a piano demo MIDI, and the finished 13-part arrangement a collaborator
built from it (trumpet, alto and tenor sax, trombone, two violins, viola,
cello, piano, electric guitar, bass, drum kit, percussion; 137 bars).

The demo's ending and the chart's ending are the **same music** — the MIDI's
last bars align pitch-for-pitch with the chart's closing bars. But:

| | Demo piano | Chart piano |
|---|---|---|
| Notes in the final ~10 bars | **129** | **14** |

The arranger stripped the piano to almost nothing and moved the material into
the horns and strings. The demo's high flourishes (up to G6) appear nowhere in
the piano part at all.

This is the §11 thesis confirmed from Matthew's own catalogue: **the demo is not
a draft of the part.** It is the source material a collaborator interprets, and
faithful transcription of it would have produced a piano part nobody wanted. A
tool that maximizes fidelity is solving the wrong problem.

It also means the finished arrangement is **not** a hand-corrected reference for
the corpus — it is the downstream product, not a cleaner notation of the same
notes. Corpus fixture one still needs its reference (see O8).

### 11.3 Target vocabulary

What that chart actually uses, and therefore what Copyist must be able to emit:

| Feature | Count in the reference | Copyist today |
|---|---|---|
| Transposing parts | 5 of 13 | §10.3, not yet implemented |
| Chord symbols | 86 | §12.1, not yet implemented |
| Ties | 1362 | done |
| `strong-accent` (marcato) | 120 | **missing** |
| `accent` | 68 | **missing** |
| `staccato` | 37 | done |
| `tenuto` | 32 | **missing** |
| `fp` | 52 | **missing** — Copyist has no sudden dynamics |
| Tuplets | 48 | §7.2, not yet implemented |
| `D.S. al Coda` / `To Coda` | present | §21, ranked too low — see O9 |
| Technique text (`Harmon mute`, `open`, `pizz.`, `arco`, `rit.`) | present | §12.4 covers as free text |
| Legitimate clef changes | 14 | not yet implemented |
| **Pedal marks** | **0** | Copyist wrote 31 — see below |

**The pedal finding is a real correction.** The human piano part in an ensemble
chart carries *no* pedal marks at all; the pianist pedals by ear. Copyist wrote
31 into a 10-bar fragment. Pedal marks belong to a solo piano score, not an
ensemble part — so pedal output must be governed by detail level and by whether
the part stands alone, not emitted because the CC data happened to exist.

The articulation vocabulary also has to widen. Gate time alone cannot produce
accent, marcato or tenuto — those come from **velocity relative to
neighbours**, which is a separate signal Copyist currently discards after
computing dynamics.

---

## 12. Lead sheets, chords and annotations

### 12.1 Chord symbols

**Primary source: a dedicated chord MIDI track.** Block chords played on their
own track are unambiguous. Pitch-class set → quality and inversion; bass note
from the lowest voice or from a separate bass track; key context (§9) resolves
spelling. Emitted as MusicXML `<harmony>`.

**Fallback: infer from the full arrangement.** Possible, meaningfully less
reliable, and always emitted with a confidence figure and a finding.

A chord track is also a strong signal *back into* key detection and pitch
spelling, so it improves the whole score, not just the symbols.

### 12.2 Slash notation

MusicXML `<measure-style><slash>` for slash regions; slash noteheads for
notated rhythm. MuseScore imports both. Driven directly by detail level (§11).

### 12.3 Annotations — one type, three sources

Section labels, rehearsal marks, fill and solo regions, and free text all share
one annotation type, fed from three sources at three confidence levels —
structurally identical to §8.4.

| Source | Confidence | Notes |
|---|---|---|
| **DAW project markers** | exact | Position and text both trustworthy |
| **Text sidecar** | exact | `20:1 Fill`, `36:1 Solo 8 bars` — DAW-independent fallback |
| **Whisper on a talkback track** | approximate | For instructions that only exist as speech; lands as *uncertain* findings to confirm |

**REAPER specifics, verified:** project MIDI export includes the tempo map and
**project markers**, but **not regions and not take markers**. So project
markers are the supported path today, with no new tooling — worth telling users
plainly. A future ReaScript (O2) would read regions and take markers too.

Ableton locator export behaviour is unverified — treat the text sidecar as the
guaranteed path there until tested.

**Whisper is deliberately second, not first.** Markers are exact and
structured; speech is approximate and positionally fuzzy. Whisper's real value
is instructions that exist *only* as speech — a talkback track, a voice memo of
production notes — and it belongs in the findings-review flow, never applied
silently.

### 12.4 What annotations become

- Section markers → rehearsal marks and section text
- "Fill" → a marked region, slashes plus the word
- "Solo — 8 bars" → slash region with bar count and chord symbols
- Anything unrecognized → text above the staff, verbatim

---

## 13. The analyze-first interview

Not a wizard that interrogates you up front. Copyist reads the file, states
what it found, and asks only where it is genuinely uncertain:

> Detected: 4/4 throughout. Tempo 92, steady. **Quantized then humanized —
> ±18 ms uniform, note lengths also randomized.** One track, two-hand piano
> texture. Straight eighths, no swing. Chord track found on track 3, 24 chords.
> Six project markers: Intro, Verse, Chorus, Verse, Chorus, Outro. Sustain
> pedal present, 34 depressions.
>
> One thing I'm unsure about: the key reads as E♭ major or C minor — 61% / 39%.
> Which is it?

Everything it is confident about, it states and moves on. One question instead
of twelve.

This is the accessible version *and* the better version — and it subsumes
questions a user should never have been asked, since the file already answers
them.

**The interview always ends by offering to save a profile.** Answer the
questions once for *ballads recorded to a click*, save `piano-ballad.toml`,
never answer them again.

---

## 14. Profiles and the sidecar

**Profile** — reusable settings, plain TOML, editable directly (more accessible
than any dialog, and diffable and shareable). Ships with presets; the interview
generates new ones.

**User profile** — properties of the player, not the music: hand spans, default
instrument, preferred notation app, default detail levels.

**Song sidecar** — per-piece state that must survive re-runs:
- locked stream/hand decisions
- locked key, meter, swing
- per-instrument detail levels
- confirmed annotations
- suppressed findings
- the exact settings that produced the last output

Reproducibility rule: the settings that produced an output are recorded *with*
the output, so months later "what made this?" is answerable and re-runnable
with one tweak.

---

## 15. Findings — the differentiator

A structured type, rendered three ways (GUI list, CLI text, MCP JSON) from one
source. Never a log.

```
Finding {
  id          F7
  severity    will-look-bad | uncertain | fixed-silently
  location    bar 22, beat 3, staff 1, voice 2
  what        "Three 16th rests from short releases"
  why         "Notes released at 31% of their slot"
  suggestion  "Raise staccato_threshold to 0.5"
  action      settings patch, applyable in one keystroke
}
```

Presented severity-first, so you can stop reading early:

- **N things that will look bad** — need your judgment
- **N things I wasn't sure about** — and what I guessed
- **N things I fixed silently** — collapsed, expandable

Four properties that make it usable:

1. **Every finding carries a fix**, not just a complaint — and the fix is a
   settings patch applyable from the list.
2. **Every finding is suppressible**, per-song and per-profile, persisted. The
   second run is quieter than the first. Otherwise you re-read the same forty
   findings forever and stop reading them at all.
3. **Findings are filtered by detail level** (§11.1). No complaints about
   material that is about to become slashes.
4. **Stable IDs**, so `explain F7` works in the CLI, the GUI, and over MCP.

Summaries of changes are always in musical terms — *"bars 40–44 notated as
triplets rather than swung sixteenths"* — never an XML diff.

---

## 16. Verification

Three independent mechanisms, all usable without sight.

**A/B audition.** Play the original performance, then play exactly what the
notation says, per section. You cannot check whether a page *looks* right, but
you can absolutely check whether it still *sounds* like what you meant.
Quantization errors that take a sighted person a squint are instantly obvious
by ear.

**Round-trip verification.** Render the output MusicXML back to MIDI and diff
against the source performance. `verify out.musicxml against original.mid` →
*"98.7% note match; 3 notes differ, all in bar 22."* An automated correctness
check that never requires eyes. Note this is only meaningful at **full** detail
level — a reduced chart is *supposed* to differ, and the verifier must know
that.

**The corpus.** Paired fixtures of *(performance MIDI → hand-corrected
reference MusicXML)*, one per instrument family and per pathology. Every bug
becomes a corpus entry; CI re-runs the whole set on every PR. This is the
project's real asset — everything else is replaceable — and it is what makes
the Python→Rust port safe.

**Idempotence.** Same input plus same profile equals byte-identical output.
Boring, and the foundation of being able to trust any of the above.

---

## 17. Licensing

**Decided: permissive core, GPL data separate.**

- `core`, `cli`, `gui` — MIT or Apache-2
- Instrument data — separate optional package, GPL-3, because MuseScore's
  `instruments.xml` is GPL-3. Alternatively read it from the user's existing
  MuseScore install.

Rationale: keeps the engine reusable by anyone, including commercial notation
tools, which maximizes how many people ultimately benefit. Vendoring the XML
directly would make the whole app GPL-3.

---

## 18. Repo and CI

- GitHub Actions matrix: macOS, Windows, Linux
- Corpus regression on every PR
- **Accessibility CI** — assert on the accessibility tree of both native UIs.
  An a11y regression suite would be a genuine first for a music notation tool.
- `CONTRIBUTING.md` leading with the accessibility rules, the way
  `accessible-reascripts` states its two design rules
- Issue templates that ask for the offending MIDI snippet, turning every bug
  report into a corpus entry automatically

---

## 19. Decided

| # | Decision |
|---|---|
| D1 | Emit MusicXML, not MIDI |
| D2 | Native per-platform GUI — SwiftUI + WinUI |
| D3 | Permissive core; GPL instrument data in a separate package |
| D4 | Name: **Copyist** |
| D5 | Python research bench → Rust shipped engine |
| D6 | Engine is a headless library; UIs are thin JSON-RPC clients |
| D7 | MCP server built last, over the same protocol |
| D8 | Quantize by scoring whole beats, grid chosen per beat |
| D9 | Gate time means articulation, never rests |
| D10 | Stream separation by hand physics, not pitch ranges |
| D11 | Hand span is a user-profile property, soft cost curve, calibrated by playing |
| D12 | Hand assignment and staff assignment are separate layers |
| D13 | ps13 for pitch spelling |
| D14 | Analyze first, ask only what's ambiguous |
| D15 | Findings are structured data with fixes attached, suppressible, stably IDed |
| D16 | Click-locked is the primary path; free tempo is gated and post-v1 |
| D17 | Detect quantize-then-humanize and undo it — grid is exact, quantization free |
| D18 | Detail level is a first-class per-instrument axis; reduction is a feature |
| D19 | Lead sheet output is v1: chord symbols, slash regions, fill/solo markings |
| D20 | Annotations come from markers first, text sidecar second, Whisper third |

---

## 20. Open questions

- **O1 — Which notation apps must be happy?** MuseScore alone permits tuning to
  its exact behavior and writing `.mscz` directly. Supporting Dorico and
  Sibelius too means staying on a conservative MusicXML subset and testing
  three importers forever.
- **O2 — REAPER as a second input path.** A ReaScript could read the *project*:
  regions, take markers, full tempo map, per-item settings — everything the
  MIDI export drops. Worth it, but after v1.
- **O3 — Matthew's comfortable vs. maximum reach.** Max is an eleventh (C to F).
  Comfortable value still to be calibrated.
- **O4 — GUI screen-by-screen layout**, especially the audition transport and
  the one-or-two-keystroke listen-and-lock flow for a low-confidence passage.
- **O5 — Voice separation within a hand** (melody vs. inner accompaniment in
  the same hand) is distinct from stream separation and is not yet designed.
- **O6 — Ableton locator export.** Unverified whether locators survive MIDI
  export. Test before promising it.
- **O7 — Chord symbol style.** Jazz vs. pop vs. Nashville conventions, and
  whether to follow the collaborator's preference per chart.
- **O8 — Corpus fixture one still needs a reference.** `expected.musicxml` is
  Copyist's own output frozen against regressions, which locks in current
  behaviour including current mistakes. The finished arrangement studied in
  §11.2 is not a substitute — it is the downstream chart, not a clean notation
  of the same notes. Either hand-engrave the fixture once and freeze that, or
  find material where a demo and a clean piano score genuinely correspond.
- **O9 — Repeat structure may be v1 after all.** §21 defers it, but the real
  chart uses `D.S. al Coda` and `To Coda`, so Matthew's actual deliverables
  depend on it. Revisit once section labels from markers (§12.3) are working —
  they may cover most of the need.
*(O10 is now built — see §22.)*

---

## 22. Built so far

| Area | State |
|---|---|
| MusicXML output (D1) | working; 100% round-trip on every fixture |
| Gate time as articulation (D9) | working |
| Stream separation by physics (D10, D11, D12) | working, greedy rather than the full DP |
| Timing classification and humanize reversal (D17) | working, self-calibrating (§7.5.2) |
| **ps13 spelling (D13)** | **working**, with one documented departure — see below |
| **Articulation from relative velocity (was O10)** | **working**: accent, marcato, tenuto from local velocity z-scores |
| **JSON protocol (§5.2)** | **working** — `prototype/engine.py` |
| **macOS GUI (D2)** | **builds and runs**; VoiceOver not yet verified at runtime |
| **Windows GUI (D2)** | **compiles in CI**; never run, NVDA not verified |
| **Chord symbols (D19, §12.1)** | **working** — template matching over duration-weighted profiles, always with a confidence and a finding |
| **Detail levels (D18, §11)** | **working** for `full`, `slashes`, `symbols`; `simplified` and `rhythmic-slashes` not built |
| **A/B audition (§16)** | **working** in the macOS app |
| Tuplets (§7.2) | not built — the reference chart used 48 |
| Transposing instruments (§10.3) | not built |
| Free tempo (§7.6) | not built, by design |
| MCP server (D7) | not built, by design — last |

### 22.1 Measured against 25 real files

The corpus fixtures are synthetic, small, and isolate one pathology each. They
are also, for those reasons, gentle. Running `prototype/stress.py` over the
complete set of MIDI files Microsoft shipped with Windows — the Passport
Designs demos from the Tandy Multimedia Extensions through the Windows 95 and
IE4 era, 25 files and 68,649 notes across every style those were meant to
demonstrate — found in one pass what months of synthetic fixtures had not.

**Two real defects, both invisible to the corpus:**

*Silent failure on six of twenty-five files.* `estimate_key` named keys with
sharps only, so it produced `A# major` and `D# major`; `convert()` had no such
entries, printed a message, and **returned**. The caller saw success, the file
came out empty, and nothing anywhere said so. Two vocabularies for the same
concept, and a failure path that lied. Both are now fixed and both have
invariant tests: unusable key names, and the function raises rather than
returns.

*Lost time on nine of twenty-five files.* A duration remainder smaller than a
64th could not be expressed by `decompose()` and was dropped, leaving measures
a few ticks short. The remainders existed because the FINAL chord in a stream
took its raw gate time as a duration instead of a grid value. Neither shows up
on fixtures that end cleanly. `decompose` is now exhaustively tested to
conserve time for every duration from 1 tick to 4 beats at three divisions.

**And a measurement worth more than either.** Round-tripping every file back
through MuseScore and diffing against the source:

| Timing verdict | Files | Mean note match | Range |
|---|---|---|---|
| `hard-quantized` | 6 | **99.1%** | 98.0 – 100.0% |
| `ambiguous` | 1 | 89.6% | — |
| `live` | 18 | **30.3%** | 1.8 – 86.9% |

| Grid detection | Files | Mean note match |
|---|---|---|
| grid found | 13 | 77.6% |
| no grid found | 12 | 18.4% |

That is not a defect report. It is the size of §7.6, measured. Copyist
reproduces a piece almost perfectly exactly when it says the grid is exact,
and badly when it says the material was played live — because the beat-scoring
cost model (§7.2) that live material requires **is not built**, and the
converter currently snaps to the detected grid, which is the naive approach
§7.1 exists to criticize.

The useful part is that the classifier predicts the failure. The one component
that is finished correctly tells you, in advance and per file, how much to
trust everything downstream of it. Until §7.2 lands, `live` should probably be
a warning in the UI rather than a silent best effort.

### 22.2 Multi-part support

Built in response to §22.1. `prototype/multipart.py` gives each instrument its
own part instead of merging a nineteen-track arrangement onto two piano staves
and applying a model of what one pair of hands can reach to a whole horn
section.

- **(track, channel) pairs become parts.** All 25 real files are format 1 with
  one instrument per track, so the rule is simple and it holds.
- **GM programs finally resolve instruments.** This was the real gap: every
  one of those files has *empty track names* and a correct program on every
  channel, so name-only resolution identified nothing in material that was
  fully labelled the whole time. Brandenburg now comes out Strings,
  Harpsichord, Violin; `jazz1` comes out Piano, Flute, Trumpet, Electric Bass,
  Jazz Guitar, Drum Kit.
- **Channel 10 is one kit**, however many tracks it was sequenced across —
  `prtytime` had eight, which would otherwise be eight "Drum Kit" staves and
  no drummer who could read them.
- **Transposing instruments** are written at written pitch with `<transpose>`
  (§10.3), and hand separation runs only for two-staff instruments.

**Result: 25/25 convert, zero unbalanced measures, and pitched-note round-trip
accuracy identical to the single-part path on every file, to the decimal.** The
score's structure changes completely while its content does not.

#### The metric lied first

Measured naively, multi-part looked like a 4.3-point regression — even on
hard-quantized files. It was not. A percussion staff conflates instruments by
position on purpose (an acoustic and an electric snare are the same line), so
the GM-pitch-to-staff map is many-to-one and cannot be inverted. Comparing
sounding pitch after a round-trip scores correct drum notation as loss. On
`Metal Mosh`, 239 of 251 "missing" notes were drums and every pitched channel
was at zero loss.

`stress.py` now excludes percussion from the comparison and says why. A metric
that punishes a correct change is worse than no metric, because it argues
against the fix.

### 22.3 Validated against 70 public-domain classical files

Mutopia Project engravings — Bach, Beethoven, Chopin, Mozart, Schubert,
Handel, Satie, Debussy, Joplin, Brahms — a completely different kind of
material from the sequenced demos in §22.1: engraved scores rendered to MIDI,
so mostly clean timing, real classical texture, and **ten different time
signatures** (4/4, 3/4, 2/4, 6/8, 12/8, 2/2, 3/2, 6/4, 9/8, 3/8).

**68/68 convert, zero failures, zero unbalanced measures.**

| Timing verdict | Files | Mean round-trip |
|---|---|---|
| `hard-quantized` | 55 | 92.8% |
| `humanized` | 2 | 73.2% |
| `live` | 11 | 59.4% |

The meter variety immediately justified a fix: `_structure()` hardcoded four
beats to a bar, so every 3/4, 6/8 and 7/8 file had its notes sorted into the
wrong metrical slots — corrupting the exact signal that statistic exists to
measure. The real time signature is now threaded through from the file.

#### Tuplets are the largest remaining accuracy gap, and now it is measured

One `hard-quantized` file came back at **11.1%**, which should be impossible —
if the grid is exact, the notes should survive. The outliers had one thing in
common:

| File | Onsets on triplet subdivisions | Round-trip |
|---|---|---|
| Debussy, *Arabesque No. 1* | 100% | **11.1%** |
| Chopin, Op. 10 No. 5 | 97.4% | 20.0% |
| Beethoven, Op. 2 No. 1, finale | 99.9% | 21.7% |
| Satie, *Gnossienne No. 2* | 0% | 100.0% |
| Schubert, *Gretchen* | 0% | 100.0% |

Copyist has no tuplet support: it snaps to the detected binary grid, which
annihilates triplet figuration. §7.2's cost model already describes tuplets as
a candidate with a fixed setup cost plus a per-note cost — it is simply not
built.

So the two open accuracy items are now both quantified rather than guessed:
**tuplets** cost 80 points on triplet-heavy repertoire, and **§7.2's live
quantizer** costs roughly 65 points on unquantized performance. Tuplets are
the better next target: the failure is total where it applies, the fix is
bounded, and the classifier already says `hard-quantized` on the affected
files, so it is currently confident and wrong — the worst combination.

**The ps13 departure.** The paper's context window is a hard 10 notes back and
42 forward, tuned on pieces of thousands of notes. On shorter material a
42-note forward window reaches straight across a modulation and spells the
first key with the second key's accidentals; and inside a hard window a note 42
away counts exactly as much as the note beside it, which is not what "local"
should mean. Context is therefore distance-weighted, with a forward bias kept.
Meredith's published 99.3% is **not** a claim about this implementation.
Measured here: 95.8% on a fixture that modulates every four bars (against 70.8%
for the best single key), 100% on a five-key holdout, zero double accidentals.
Parameters were chosen by sweep on one fixture and confirmed on the other, and
the good region is a broad plateau rather than a knife edge.

**Windows uses WPF, not WinUI 3.** Same reasoning that chose native over a
webview: WPF's UI Automation is mature and NVDA works well with its stock
controls, while WinUI 3 is newer with more accessibility gaps. Neither GUI
contains a custom control template or a custom AutomationPeer, which is the
usual way an accessible toolkit stops being accessible.

---

## 21. Not in v1

- **Free-tempo beat tracking.** Real requirement, secondary path, post-v1
  (§7.6).
- **Repeat structure detection** — recognizing that six choruses are the same
  and writing repeat barlines and D.S. Note that *section labels* from markers
  (§12.3) are v1 and deliver much of the readability win without the hard part.
- **Whisper annotation parsing.** Designed for (§12.3), built later.
- Rendering notation in-app.
- Fingering-level modelling (which intervals within the span are comfortable,
  not just how wide).

---

## References

- [MuseScore `instruments.xml`](https://github.com/musescore/MuseScore/blob/master/share/instruments/instruments.xml)
  · [documentation](https://musescore.org/en/handbook/developers-handbook/references/instrumentsxml-documentation)
- [MusicXML Standard Sounds](https://www.musicxml.com/for-developers/standard-sounds/)
  · [`sounds.xml`](https://github.com/w3c/musicxml/blob/gh-pages/schema/sounds.xml)
- [MusicXML: Chord Symbols and Diagrams](https://w3c.github.io/musicxml/tutorial/chord-symbols-and-diagrams/)
- [MuseScore: slash notation](https://handbook.musescore.org/alternative-notation/slash-notation)
- [Meredith, *The ps13 Pitch Spelling Algorithm*](http://www.titanmusic.com/papers/public/meredith-ps13-jnmr.pdf)
- [Nakamura et al., *Merged-Output HMM for Piano Fingering of Both Hands*, ISMIR 2014](https://eita-nakamura.github.io/articles/Nakamura_etal_MergedOutputHMMForPianoFingering_ISMIR2014.pdf)
- [*Detecting Hands in Piano MIDI Data*](https://dl.gi.de/bitstreams/38bd15cf-1a0c-41e5-a75d-7723b2f5710f/download)
- [*Three Methods for Pianist Hand Assignment*](https://www.researchgate.net/publication/255583586_THREE_METHODS_FOR_PIANIST_HAND_ASSIGNMENT)
- [Exporting MIDI from REAPER](https://reaper.blog/2021/06/export-midi/)
- [partitura](https://partitura.readthedocs.io/en/latest/introduction.html)
