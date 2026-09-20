# The Copyist chart format

**Status:** living specification. **The listening audio is Copyist's own as of 2026-09-20** — no MuseScore in the check-listen-read loop; MuseScore remains only for PDF pages, and retiring that too is the stated direction. Designed 2026-08-30 against the measured
corpus; substantially implemented as of 2026-09-20 (the compiler, the demo
door §3.4.1, the bars grammar with groups, the working chord-quality set,
hits, articulations, dynamics, engraved page output, and the read-aloud
contract of §4). Meters: any
N over 1, 2, 4, 8 or 16 compiles (waltzes, 6/8, 5/4 — verified), with
`at bar N: tempo X` mid-chart tempo changes; a compound meter counts in
its denominator pulses, prints its `tempo:` as a dotted-quarter
metronome mark, and plays back at the matching speed; the `new`
interview asks the meter (defaulting to the demo's own time signature)
and counts bars with it. Per-bar meter changes (`at bar N: meter`, §3.6)
compile as of 2026-09-20: every part restates the time signature at the
change, chords spread against each bar's own meter, multirests break
where a player must look up, the demo door locates figures by the demo
file's own time signatures (a figure may not cross a change — the error
says where to split), the listen trim walks the meter and tempo maps
bar by bar, and a compound↔simple change with no new tempo is a
finding. Named figures compile as of 2026-09-20: `figure <name>, N
bars:` sourced `from midi` (the demo pipeline, written for whichever
part places it, riding the same quant and phrasing words) or `from xml`
(written bars lifted verbatim, the source's divisions carried per
measure and the part's own restated after); placed with `figure <name>
[at bar N]`, unused definitions are a finding, and every mistake —
undefined name, wrong length, missing part — is one sentence. Inline `notes:` figures compile too (same day): the 3.4 grammar — pitch-name durations w h q e s with dots, ties with +, rest, triplet( ... ) — shaped internally as a resolved demo range, so the page, the prose and the player need nothing new, and the legato and articulation words ride along; notes that do not fill the declared bars refuse with both counts. Beat-length figures are still ahead, and lyrics sing as of the
same day: a `lyrics:` line after a figure's source, or a
`lyrics "..."` piece on any from-demo line — written the way the writer
says them: unhyphenated words syllabify themselves (each split reported
for veto; explicit hyphens win), slashes anchor word groups to the
melody's own rest-separated phrases (a mismatch names the phrase and
its bar, and a wrong phrase count reads the whole melody's shape back),
underscores hold a melisma, and the read-aloud sings each word on its
note. Volta endings compile as of
2026-09-20 (`ending N, M bars:
chords: ...` inside a repeated section — brackets, repeats and the
final discontinue land where a player looks, and the read-aloud speaks
"8 bars a pass, with 2 endings... First ending: ..."). Phrasing is the
writer's word (2026-09-20): `legato` reads
the played gates into slurs that break where the writer breathed,
`ghosts` reads velocities into parenthesized noteheads, `straight`
puts onsets on the eighth grid while durations stay as played (a
shuffle notated straight — `eighths` still means a line OF eighth
notes), and a swing or shuffle `feel:` makes the LISTENING document
genuinely swing in playback while the pages stay convention. Asking
for phrasing the playing does not support is a finding, never a
silent no-op. Keyboard-family parts (piano, organ, harp, celesta) from a
demo print on the grand staff — hands split by the engine's physics
model (DESIGN.md §8), with a note a hand is still holding anchoring the
split — and a note that keeps ringing under later movement (a guitar's
low string, a pedal tone) prints as its own voice instead of being cut
at the next onset, with a finding naming the bars. The directive family
lands the same day: `double <part>` re-renders another part's resolved
line for the target's own transposition, `cue <part>` prints it
cue-size with its "(<part> cue)" label and Copyist's own player never
sounds it (MuseScore always did), `build:` fans "+who" entrance cues to
every part, `on pass N:` tags its words "(Nx only)", and `as demo` is
symbols-level slashes wearing the words. Detail levels complete the
same day: `simplified` (a from-demo word or band-line default) smooths
the played line to the eighth and absorbs ornament noise, saying what
it absorbed; `rhythmic slashes` prints the line's rhythm on slash
noteheads with the chords above — silent in playback like every slash,
and its range report stays quiet since the page shows no pitches
(`slashes` and `symbols` on a band line redirect to `groove` and
`as demo`, which already print those levels). And the `look:` header
dresses the pages — jazz/handwritten (MuseJazz) or engraved, plus
landscape, `staff <size>` for larger print, and `measure numbers` —
validated at check, applied at render, absorbed by the engraver when it
comes. Still ahead: per-pass NOTES for `on pass`.
**Read DESIGN.md first.** This document extends it: where DESIGN.md turns a
performance into a chart, this format lets a chart be *written* directly — as
text — and compiled into the same MusicXML the engine already emits.

---

## 1. What this is

A chart is a plain text file (`.chart`, UTF-8) that a blind composer can read
and write with a screen reader, kept in git, and compiled deterministically
into a conductor score and per-instrument parts (MusicXML). The listening
audio is Copyist's own — chartaudio synthesizes the listening document
directly, no external renderer — and PDF pages come from MuseScore's
command line for now (verified working headless; a Copyist engraver is
the stated direction, 2026-09-20).

The format was designed against a measured corpus, not guessed: eleven real
scores from the author's book (eight big-band charts engraved by Jeremy Hegg,
Guy Barker's 24-part orchestral *Emotions*, Michael McElroy's vocal
arrangement of *Tomorrow*, and the *Finally Free* string arrangement), plus
27 originals batch-exported from Sibelius. Every construct below exists
because those scores use it; §9 is the coverage table.

The reader of a compiled part is a collaborator, not a machine (DESIGN.md §11).
Most of a chart is chords, slashes and words. Fully notated material enters by
*reference* to MIDI, MusicXML or audio-derived sources — the existing Copyist
engine — or, for short figures, inline.

## 2. Design rules

1. **One statement per line, and every line is speakable.** A screen reader
   reads line by line; each line must make sense read aloud, in order, without
   sight of any other line. No layout-as-meaning, no ASCII art, no alignment.
2. **Words over symbols.** The only structural punctuation is the comma
   (list separator), the colon (introduces content), `@` (read "at"), `x`
   (read "times"), and `+` after a beat number (read "and"). Chord symbols use
   their ordinary spellings.
3. **Every length is declared, and the compiler enforces it.** A section says
   how many bars it is; its contents must add up. A chart that does not add up
   does not compile, and the error is a sentence naming the section and the
   count. This is the accessibility feature: bar arithmetic is proofread by
   the machine, not by eye.
4. **Never silently guess** (DESIGN.md principle 3). An unknown chord quality,
   an unresolvable instrument, a reference to a missing figure — all errors,
   never best-effort.
5. **Bar numbers inside a section are section-relative.** Inserting a section
   never renumbers the rest of the chart.
6. **Tempo comes from the composer.** Never from detection (measured finding:
   detection fails on dense material), and it may be omitted entirely — the
   2024 *Matt's Blues* engraving carries no metronome mark and is correct.
7. **Same input, same output, byte for byte** (DESIGN.md principle 6).

Comments: a line whose first non-blank character is `#` is ignored. There are
no end-of-line comments, so `F#7` is never at risk.

## 3. File anatomy

In order: a **header**, a **band** block, any number of named **chords** and
**figure** definitions, an optional **pickup**, the **sections** in
performance order, and an optional **output** block. Blank lines are free.

### 3.1 Header

Key–value lines, one per line:

    title: Matt's Blues
    composer: Matthew Whitaker
    arranger: Jeremy Hegg
    key: Bb
    meter: 4/4
    tempo: 132
    feel: swing

- `key` is the concert key; written keys per part come from the instrument
  database (DESIGN.md §10). `tempo` is a number, or words (`rubato`,
  `Slow, freely` — both appear in *Lush Life*), or absent.
- `feel` is printed verbatim at the top (`Swing`, `Latin`, `Afro-Cuban feel`
  are all in the corpus) and tells the compiler how to interpret eighths.
- `source: "<file.musicxml>"` names the chart's default engraving — the
  score that `as engraved` directives (§3.6) lift from. Optional; only
  charts derived from an existing score need it.

### 3.2 Band

One instrument per line. The label before `=` is the part name; the name
after it resolves through the instrument database, which supplies clef,
transposition and range. No `=` means the label is the instrument.

    band:
      alto 1 = alto sax
      trumpet 2 = trumpet
      voice = soprano
      guitar
      bass = electric bass, tuning Bb0 Eb1 Ab1 Db2 Gb2
      drums = drum set, detail symbols

- `detail <level>` sets that part's default detail level (DESIGN.md §11):
  `full`, `simplified`, `rhythmic-slashes`, `slashes`, `symbols`. Defaults
  come from the instrument profile (rhythm section → slashes, melodic → full).
- `tuning` overrides the range check — the five-string tuned a half-step
  down is a real bass in this band.
- Built-in groups resolve automatically from the band list: `saxes`,
  `trumpets`, `trombones`, `horns` (all winds), `rhythm` (guitar, piano,
  bass, drums), `all`. Custom: `group shout team: trumpet 1, alto 1`.

### 3.3 Chord progressions

Defined once, used by name — a solo form is written one time:

    chords solo blues: Bb7, Eb7, Bb7 x2, Eb7 x2, Bb7, Dm7 G7@3, Cm7, F7, Bb7, F7

**The bars grammar** (used by every `chords:` line):

- **Commas separate bars.** The line above is twelve bars.
- **`xN` after a bar means that bar lasts N bars total.** `Bb7 x2` is two
  bars of B-flat seven. A parenthesized group repeats whole:
  `( F7, Bb7 ) x4` is eight bars.
- **Chords within one bar** are separated by spaces and split the bar evenly
  unless placed. `Dm7 G7` in 4/4 is two beats each.
- **`@beat` places a chord explicitly**: `C9 F7@3 Bb7@4+` reads "C nine,
  F seven at three, B flat seven at four-and" — beats 1, 3, and the and of
  four. An off-beat eighth may be spelled any of three ways — `4+`, `4.5`,
  or `and-of-4` — all equivalent (decided by Matthew 2026-08-30: the format
  should meet each writer's habit, not impose one). Documentation and
  shipped examples use `4+`; the read-aloud view always speaks "the and of
  four" regardless of source spelling.
- **`nc`** is no chord. A bar that continues the previous chord restates it;
  the printer suppresses repeated symbols the way an engraver would, so the
  source stays explicit and the page stays clean.
- Chord spelling: root with `b` or `#`, then quality: `7 9 11 13 maj maj7
  maj9 maj7#11 m m7 m9 m11 m6 m69 m7b5 mmaj7 dim dim7 sus2 sus4 7sus4 aug
  6 69 add9 madd9 7b5 7#5 7b9 7#9 7#11 7#9#11 7b13 13b9 alt`, plus slash
  bass (`C7/E`). Jazz shorthand normalizes: `C-7` is `Cm7`, `min` is `m`,
  `sus` is `sus4`, `7alt` is `alt`, `aug7` is `7#5`. This list covers
  every quality in the measured corpus plus the working jazz set;
  anything outside it is an error until added deliberately.

### 3.4 Figures — notated material

A figure is named, has a declared length, and gets its notes from one of
three sources, in descending order of preference:

    figure head hits, 6 bars:
      from xml "Scores XML/Matt's Blues.musicxml", part "Trumpet 1", bars 15-20

    figure bass line, 12 bars:
      from midi "demos/mattsblues.mid", track "Bass", bars 1-12

    figure pickup lick, 3 beats:
      notes: rest e, C5 e, A4 e, C5 e, A4 e, F4 e

- **`from xml`** lifts bars from existing MusicXML — the Sibelius book, a
  collaborator's Finale export — verbatim, including articulation, dynamics
  and lyrics. This is how "play this exact" usually works.
- **`from midi`** runs the full existing Copyist pipeline (timing
  classification, quantization, spelling, articulation) on the referenced
  bars, and its findings surface in the chart build like any conversion.
- **`notes:`** is the inline escape hatch for short material. Pitch is name,
  accidental, octave (`Bb4`, `F#3`); duration letters are `w h q e s`
  with `.` for dotted; tied durations join with `+` inside one note
  (`C5 q+e` — "C five, quarter plus eighth"); `rest <dur>`;
  `triplet( F4 e, A4 e, C5 e )`. Deliberately minimal: anything long or
  intricate should come in by reference, where the engine's machinery and
  verification already work.
- **A figure is one line — one part's material.** When a whole ensemble
  should play its *own* engraved lines (a thirteen-horn soli is thirteen
  different parts, not one line in unison), use the `as engraved` directive
  (§3.6) instead: each targeted part lifts its own identically-named part's
  bars from the header's `source:` score, so the passage is exact per
  player without naming thirteen figures. Part names match by normalized
  comparison (case-insensitive, transposition words dropped); an ambiguous
  match is an error, never a guess.
- `lyrics:` may follow a figure's source for vocal parts: syllables split
  with hyphens, melisma extended with an underscore, aligned to the notes in
  order (`lyrics: To-mor-row, to-mor-row_`). Lyrics riding in referenced
  XML come along automatically (Michael McElroy's *Tomorrow* carries 1,385
  syllables — the reference path is the realistic one).

### 3.4.1 The demo door — `from demo` (first built for *Subway Psalm*)

When a chart is composed from a played demo rather than encoded from an
engraving, naming a figure per phrase gets heavy. `from demo` is the
lighter door: the header names the demo once, each band member names its
track, and a directive lifts any bar range of that part's own line through
the conversion pipeline.

    demo: horns.MID                        # header, next to source:

    band:
      tenor = tenor sax, demo "sx 3" octave -1
      flute, demo "flute.MID"              # a .mid value is its own file

    section E, 16 bars
      tenor: from demo bars 58-60, from demo bars 64-65
      bari: from demo bars 50-65, eighths
      trumpet 1: from demo "tp 1 mute" bars 36-41

- The demo and the chart share one bar grid, so `from demo bars N` lands on
  chart bar N; `at bar N` (section-relative) moves it.
- A quoted name right after `from demo` overrides the band default — how a
  muted-passage track sits next to the open track for one player.
- `octave -1` on the band line corrects a track recorded an octave off its
  sounding pitch (voicing stacks expose this: a trombone above the
  trumpets is a recording convention, not a voicing).
- **The demo is ideas, not gospel.** Conversion measures the player's
  systematic lay-back per phrase (median offset) and removes it — the
  finding reports the milliseconds; the feel stays with the player. The
  grid is chosen per beat (§7.2.1's tuplet chooser), one voice is enforced
  per horn, slivers of daylight between legato notes close, and
  out-of-range notes fold by octaves into the part's range, each with a
  finding naming the bar.
- **`eighths` / `sixteenths` / `triplets` / `eighth triplets` /
  `sixteenth triplets`** on the directive are the writer's word beating
  the statistics: they restrict the per-beat grid ("triplets" is the
  permissive swing family; the two named-triplet forms are strict, with
  no binary escape hatch). "These bars are eighth notes" is authorship,
  not measurement, and the format records it.
- **Articulation is authorship too**: `fall` (falloff on the last note),
  `short` (staccato on the last note, and its printed length caps at an
  eighth — a note the writer calls short prints short whatever the demo's
  gate held), `marcato` (the housetop on every note — "short and fat"),
  and the jazz bend set — `scoop` (in from below), `plop` (in from
  above), `doit` (up off the end), `fall` (down off the end) — placed
  with `first` / `last` / `bar N beat B`; place by the demo's own
  pitch-bend data when in doubt. Instructions accept bandstand synonyms
  (falloff, housetop/daht, slide, spelled-out dynamics and note values),
  normalized before parsing: the format meets each writer's habit.
- **`dyn <mark> [at bar N] [beat B]`** prints a dynamic (pp..ff and sfz;
  B accepts `4+` spellings or decimals for tuplet positions). With
  **`dynamics: by hand`** in the header the pedal-derived marks switch
  off entirely: once the writer dictates, only the writer speaks.
- **`countin: N`** (header) drops the demo's count-in bars from the page:
  demo bar N+1 prints as bar 1, and every default placement shifts with
  it. Directives keep speaking the DAW's bar numbers — the numbers the
  writer is looking at.
- **Dynamics come from the expression pedal** unless dictated. CC 11 is
  read per figure: each playing bar's median level maps to p/mp/mf/f/ff
  and a mark prints wherever the level changes. The findings say what was
  derived, and the read-aloud view speaks the marks, so the writer
  corrects them by ear like everything else.
- **Cutoffs are ensemble events.** A sustained note's release snaps to
  the eighth grid (a beat nobody attacks in counts as binary), and a
  repeated sustained note at the same bar position and pitch unifies to
  one canonical release — the same phrase gets the same cutoff. A note
  running legato into the next onset is a tie, not a cutoff.
- **The build writes one extra document, "<title> — for listening"**:
  identical except slash regions render as real rests, because major
  renderers play slash noteheads. The proofing MP3 comes from it; every
  printed page keeps its slashes.
- **Everything spoken uses the writer's own bar numbers.** With
  `countin:` set, findings and the read-aloud add the count-in back, so
  the writer hears the numbers their DAW shows; only the printed page
  counts from one.

### 3.5 Pickup

    pickup 3 beats: piano, figure pickup lick, text "(piano pickups)"

At most one, before the first section. The compiler emits a real implicit
bar — *Matt's Blues* opens with exactly this.

### 3.6 Sections

    section A, 12 bars, label "head"
      feel: 1/2 Time Funk
      chords: Bb7, Eb7, F7 Cb7@3, Bb7, Eb7 Bbm7@3, Eb7, C9 F7@3 Bb7@4+, Bb7 x2, Bb7 E13@4+, E13 x2
      horns: figure head hits A
      rhythm: groove

The header is: `section <name>[, <N> bars][, label "<text>"][, repeat Nx]
[, open]`.

- **`name` is the rehearsal mark**, and it may be a letter, a number, or a
  word — the corpus uses all three styles (A–K in *Matt's Blues*, bar
  numbers in *Jeannine* and *Take a Break*, "head" / "shout!" / "piano solo"
  as names). `label` adds the human title printed beside the mark.
- **`repeat Nx`** prints repeat barlines around the section. **`open`**
  prints an open repeat ("solos (open)", "on cue" until cued off).
- **Endings** (the volta brackets *Jeannine* uses 144 of): the declared
  section length is ONE PASS — the body plus one ending — because that
  is how a musician counts it ("letter B is 8 bars"). Endings declare
  their own bars, must all be the same length, and must number 1 up to
  the repeat count, one per pass. The printed page carries the body and
  every ending; Copyist's own playback takes ending K on pass K, and a
  from-bar trim lands where the PLAYER reaches that bar, repeats
  included.

      section B, 8 bars, repeat 2x
        chords: F7, Bb7, F7, F7, Bb7, Bb7
        ending 1, 2 bars: chords: C7, F7
        ending 2, 2 bars: chords: C7 Bb7@3, F7

- **Directive lines** are `target: instruction[, instruction ...]` where
  target is a part label, a group, or `all`. Instructions:

  | Instruction | Prints |
  |---|---|
  | `groove` | slashes under this section's chords |
  | `groove "half-time funk"` | the same, with the words above the first bar |
  | `figure <name> [at bar N]` | the notated figure, from that section-relative bar (default 1) |
  | `as engraved bars A-B [at bar N]` | each targeted part's own bars A–B of the `source:` score, exact |
  | `hits on 1, 2+, 4` | rhythmic-slash kicks on those beats (bar prefix: `hits bar 3 on 2+, 4`) |
  | `solo` / `solo open` | solo changes shown, "Solo" / "solos (open)" printed |
  | `backgrounds, on cue` | the figure marked "backgrounds on cue" |
  | `tacet` | whole-section multirest in the part |
  | `as demo` | "as demo" over slashes — symbols-level (DESIGN.md §11) |
  | `double <part>` | this part plays another part's line (printed full size) |
  | `cue <part>` | another part's line printed cue-size, not played — "(Piano cue)" |
  | `text "words" [at bar N]` | the words, verbatim, at that (section-relative) bar |
  | `mute cup` / `mute harmon` / `open` | technique text at its position |
  | `on pass 2: <instruction>` | the instruction on that repeat pass only — prints "(2x only)" |

  A part not named in a section follows its band-block default: rhythm
  section grooves, everything else is tacet. **The compiler lists every
  part's resolved behavior per section in its findings**, so an accidental
  twelve-bar rest in the lead alto is read back in text before it is ever
  printed.

- **Timed events inside a section** use section-relative bars:

      at bar 9: text "Swing--"
      at bar 5: meter 5/4
      at bar 7: tempo 96
      build: add saxes at 3, add trombones at 11

  `build:` prints the "+saxes" style entrance cues *Jeannine*'s montuno
  uses. Tempo words (`molto rall.`, `a tempo`, `Colla Voce`, `Tempo I`)
  go through `text` — they are performance language, printed verbatim.

- `use chords <name> [xN]` cites a named progression instead of an inline
  `chords:` line.

### 3.7 Output

    output:
      score
      parts: each
      pdf: yes

Optional; these are the defaults. Transposition to written pitch is always
automatic from the instrument database — a B-flat trumpet part comes out in
the right key or the build fails, never silently concert. Multirests in
parts are automatic. Pedal marks are **never** emitted in ensemble parts
(measured: zero in every ensemble piano part in the corpus; DESIGN.md §11.3).

## 4. Validation contract

`copyist chart check` must enforce, with one-sentence errors:

1. Every section's contents sum to its declared length; endings likewise.
2. Every `figure`/`chords` reference resolves; unused definitions are warned.
3. Every directive target resolves to the band block.
4. Every chord parses against the quality list; every note is inside its
   instrument's range (honoring `tuning`), or a finding says which bar.
5. `on pass N` only inside a repeated section; `ending N` numbers complete.
6. Every `from xml` / `from midi` file exists, the part exists, the bars are
   in range, and the referenced length equals the declared figure length.
7. Section-relative bars in `at bar N` are within the section.
8. Build is idempotent, and findings (DESIGN.md §15) carry anything reduced,
   guessed, or worth hearing about — filtered by detail level as always.

`copyist chart read <file> --part "alto 1"` renders any part as prose — the
part as the player will experience it, section by section, in sentences.
That is the blind proofread, and it is a first-class output, not a debug
aid. Built: `prototype/chartread.py`, which resolves the chart with the
same plan builder the compiler uses, so the prose and the printed page
cannot disagree. Chords are spoken as a musician says them ("B flat
seven"), off-beats are always "the and of four" whatever the source
spelling, and the whole answer is written in one pass — a screen reader
restarts on every write.

## 5. What is deliberately absent

- **Segno, coda, D.S., D.C.** — zero occurrences across all eleven measured
  scores; every chart writes its form out linearly (with section repeats and
  voltas). The section model can grow a `goto`-style construct later without
  breaking anything, but it is not v1 (this revises O9's worry downward:
  the 13-part reference chart in DESIGN.md §11.3 used D.S., but the current
  book does not).
- **Pedal marks** — see §3.7.
- **Nested repeats, in-bar meter tricks, cross-staff inline notation** — the
  inline `notes:` grammar stays small on purpose; the reference path exists
  precisely so text never has to express what MusicXML already can.

## 6. How it attaches to the engine

New: the chart parser and the section/part resolver. Reused as-is: the
instrument database and transposition (§10), chord symbol emission (§12.1),
slash regions (§12.2), detail levels and reduction (§11), the MusicXML
writer, findings (§15), and — for `from midi` — the entire conversion
pipeline including its verification. The listen file is synthesized by
Copyist itself (prototype/chartaudio.py — stdlib wavetable synth, real
swing, honest dynamics, sample-exact meter and tempo maps). MuseScore CLI
still renders the PDFs headless (verified 2026-08-30; it may crash *after*
writing a valid PDF — judge by the output file, not the exit code) until
Copyist's own engraver exists.

## 7. The worked example

`Matt's Blues.chart` (kept with the private chart library, not in this
repository) expresses the full 147-measure 2024 big-band chart in this
format. Its chord timeline was machine-verified against the source
MusicXML's 118 harmony events at eighth-note resolution — the verifying
script is `prototype/chartcheck.py`, which doubles as the reference
implementation of the bars grammar in §3.3.

`prototype/chartc.py` is the first compiler increment, built against that
example: it compiles the chart to a conductor score plus seventeen parts,
all rendering through MuseScore headless. Verification runs both ways with
the same checker — the chart against the original engraving, and the
compiled score against the chart — so the compiled output's harmony
timeline provably matches the source engraving transitively. Everything the
increment does not implement fails with a one-sentence error naming the
construct, never a partial page (the docstring lists them).

## 8. Decided (all three settled by Matthew, 2026-08-30)

- **Q1 — beat spelling: accept all three.** `2+`, `2.5` and `and-of-2` are
  equivalent on input, because the format is meant for more writers than one
  and each will bring a habit. Canonical in docs and examples: `2+`. The
  read-aloud view always speaks "the and of two."
- **Q2 — continuation bars restate the chord, with `xN`.** No `same`
  shorthand: `E13 x8` is explicit, short, and audible without looking back
  up the line. The printer still prints a symbol only where it changes.
- **Q3 — `open` sections end with printed text only.** "solos (open)" /
  "on cue" on the page, the band handles the cue live — exactly what the
  real charts do. No cue-target modeling.

## 9. Coverage against the measured book

| Measured in the corpus | Construct |
|---|---|
| 3,306 chord symbols | chords grammar §3.3 |
| Slash regions (97–238 per chart) | `groove`, detail levels |
| Repeats with volta endings (*Jeannine*: 180/144) | `repeat Nx`, `ending N` |
| Rehearsal letters, bar-number marks, named sections | section `name` + `label` |
| "1/2 Time Funk", "Swing", "Latin", "2-feel" | `feel:`, `groove "…"` |
| "solo", "solos (open)", "on cue", "drum solo" | `solo`, `open`, `backgrounds, on cue` |
| "+saxes / +bones / +trumpets" (montuno build) | `build: add … at N` |
| "1x only", "3x-4x play upper part" | `on pass N:` |
| Cup/Harmon mutes, "open" | `mute`, `open` |
| "Colla Voce", "molto rall.", "Tempo I", "Slow, freely" | `tempo:` words, `text` |
| Meters 2/4, 4/4, 5/4, 7/8; mid-chart changes | `meter:`, `at bar N: meter` |
| Tuplets (26–182 per chart) | referenced figures; inline `triplet(…)` |
| "(Piano cue)" cue-size notes (*Finally Free*) | `cue <part>` |
| Multirests in parts | automatic |
| "(noodle a bit)", "(float above it all)", "as is..." | `text`, verbatim always |
| Vocal parts with lyrics (*Tomorrow*: SAT, 1,385 syllables) | `lyrics:`, XML reference |
| Kicks over slashes | `hits on …` |
| A five-string bass tuned Bb0–Gb2 | `tuning` on the band line |
| Pickup bar ("(piano pickups)", 3 beats) | `pickup` |
