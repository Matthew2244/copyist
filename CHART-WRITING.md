# Writing a chart

This is the guide for the person writing the music, not the person
writing the code. A chart is a plain text file — readable by any screen
reader, editable in any editor, shareable like any file — that says what
you would say to the band. You type it the way you'd say it, run one
command, and out come the conductor score, a part per player, a spoken
version of every part, and a robot recording of exactly what the pages
say, so you can proofread with your ears before a single player sees it.

The worked example below is an invented tune called *Uptown Local*.

## The header — who, what, where

    title: Uptown Local
    composer: Your Name
    key: F minor
    meter: 4/4
    tempo: 96
    demo: uptown-local-horns.mid
    countin: 1
    dynamics: by hand

- `demo:` names the MIDI file you played the horn lines into. The chart
  pulls real notes from it — your playing is the documentation.
- `countin: 1` says your DAW file opens with one count-in bar. From then
  on, you speak your DAW's bar numbers everywhere in the chart, and every
  spoken read-back uses them too. Only the printed page counts from one —
  players never see your count-in.
- `dynamics: by hand` means you'll dictate the dynamics. Leave it out and
  the build reads your expression pedal (CC 11) instead and drafts marks
  for you to correct.

## The band

    band:
      alto = alto sax, demo "alto"
      tenor = tenor sax, demo "tenor" octave -1
      trumpet 1 = trumpet, demo "tpt 1"
      trombone, demo "bone" octave -1

Each line: a label you'll use in the chart, the instrument (which sets
the transposition, clef, range and playback sound), and which track of
the demo holds that player's material. The instrument table covers the
whole ensemble world — full woodwinds and brass, strings with their own
clefs, rhythm section, mallets, and all five voice parts from soprano
to bass, because singers are instruments too and nobody gets left out.
Polyphonic instruments (piano, guitar, vibes, organ) keep their chords. `octave -1` corrects a track that
was recorded an octave above where it sounds — common, and easy to spot:
if your trombone sits above your trumpets on paper, that's a recording
convention, not a voicing.

## Sections — the form, the changes, who does what

    section A, 8 bars, label "the head"
      chords: Fm7, Bb7, Fm7, Fm7, Bbm7 Eb7@3, Abmaj7, Gm7b5 C7@3, Fm7
      trumpet 1: from demo bars 2-9
      trombone: from demo bars 2-9

    section B, 8 bars, label "tenor blows", open
      chords: Fm7 x8
      tenor: solo
      all: groove "greasy - stay out of the way"

- Chords split a bar evenly unless you place them: `Eb7@3` is "E flat
  seven on beat three", and off-beats take any spelling you'd use —
  `4+`, `4.5`, or `and-of-4`. The format meets your habit.
- `from demo bars 2-9` lifts YOUR played line, bars 2 to 9 of your DAW,
  cleans it up (your lay-back is measured and kept as feel, not printed
  as wrong rhythms), and lands it at the same bars of the chart.
- `solo` prints "Solo" with the changes. `groove` prints slashes.
- A part you don't mention rests. The read-back tells you every part's
  fate per section, so an accidental eight-bar rest in the lead alto is
  heard in text before it is ever printed.

## Saying how it goes — the words you'd use on the bandstand

All of these ride on a `from demo` line, after commas:

    trumpet 1: from demo bars 10-17, eighths, marcato
    tenor: from demo bars 18-19, sixteenth triplets, scoop first, fall
    all: text "laid back" at bar 1
    trombone: dyn f at bar 1, dyn sfz at bar 8 beat 4+

- **Grid words** — `eighths`, `sixteenths`, `triplets`, `eighth
  triplets`, `sixteenth triplets`. Your word beats the math: if you say
  the bars are eighth notes, the page prints eighth notes.
- **Articulation words** — `marcato` is short-but-fat on every note (the
  big-band daht). `short` makes the phrase's last note print short.
  `fall` drops off the last note. `scoop first`, `scoop last`, or
  `scoop bar 12 beat 3.5` put the slide where you bent it.
- **Dynamics** — `dyn mp`, `dyn f at bar 9`, `dyn sfz at bar 8 beat 4+`.
  Marks land under the note, including on off-beats and tuplet spots.
- **Say it your way — whatever music raised you.** The same mark has a
  different name in every tradition, and the parser meets them all:
  jazz says `daht` or `housetop`, classical says `marcato` — same
  housetop on the page. `falloff`, `fall off` and `fall` are one word;
  `slide` is a `scoop`; `ten.` is `tenuto`; note values spell out
  (`eighth notes`, `sixteenth note triplets`); dynamics take the long
  words (`dyn sforzando`, `dyn mezzo piano`) or the marks. Every-note
  articulations cover the traditions: `marcato` (short and fat),
  `staccato`, `tenuto` (full value), `accent`. The bends: `scoop` (in
  from below), `plop` (in from above), `doit` (up off the end), `fall`
  (down off the end). `cresc` and `dim` — or `crescendo`,
  `diminuendo`, `decrescendo` — print where you put them. And the rule
  that keeps every tradition welcome: any word the parser does not
  know still reaches the page verbatim through `text "..."` — gospel's
  "push it", a string section's "sul tasto", anything. No one's
  language is blocked. Funk's `stabs` and gospel's `punchy` are the
  housetop too, and `quarters` pins a ballad figure to the beat.
- **Words on the page** — `text "harmon mute - stem out" at bar 9`,
  `mute cup`, `open`. Say anything; it prints verbatim. One catch: keep
  commas out of quoted text (use a dash) — the comma is how instructions
  are separated.

## Starting from nothing

    python3 prototype/chart.py "Uptown Local.chart" new --demo horns.mid

The interview reads your demo first, then asks one question at a time —
title, key, tempo (offered from the file itself), count-in (detected
when bar one is empty) — and walks the tracks: each one announced with
its name, note count and range, you name the instrument, and if the
track sits an octave off that instrument's real register it says so and
proposes the correction. The chart it writes opens with an activity
map — who plays which bars — so carving sections is reading, not
detective work.

## The loop that replaces a copyist

    python3 prototype/chart.py "Uptown Local.chart"

That one command checks the chart, builds score and parts, renders the
PDFs, writes a spoken read-aloud for every part, and bounces the listen
MP3 — robot horns playing exactly what the pages say. The workflow that
works:

1. Listen to the MP3. Anywhere it sounds wrong, the page is wrong.
2. Open the read-aloud for that part and find the bar — it speaks your
   DAW's bar numbers, at concert pitch, with every mark named.
3. Change the chart text. Run the command again.

The pages come out engraved like a pro part: every section closes
with a double bar, the last bar gets the final bar, and in the parts a
stretch of waiting prints as one bar carrying its count — sixteen bars
of rest is one measure with a 16 over it, never sixteen empty bars. The
conductor score keeps every bar visible. A multirest breaks wherever a
player needs to see something — a rehearsal letter, a dynamic, a text —
and may close at a double bar.

Every build ends with a range report — each part's written peak and
low with their bars. The philosophy: floors are hardware, ceilings are
chops. A note below the horn folds up an octave; a high note is NEVER
destroyed, because a lead trumpet runs to written double C and beyond —
instead the report flags it: "lead territory; know whose chops are on
the chair." Trombone lows below the staff get named as pedal territory.
The ranges come from the arranging literature, not guesses.
And when only your ears matter: `listen` skips the pages, `--from-bar
78` cuts an MP3 starting right where you want to proof, and `--solo
"bari,trombone"` isolates just those parts.

The build also prints findings — every place it moved a note into range,
unified a repeated phrase's cutoff, or noticed your timing sitting loose
on a grid. A finding is a question for your ear, not an apology.

## Writing with other people

A chart is one small text file, so collaboration is whatever you already
use for text: a shared folder, email, or a git repository. Two writers
can work on different sections and merge; the history of a chart is the
history of decisions, in plain words anyone's screen reader can read.
The demo MIDI travels beside the chart, and anyone with the repo and
MuseScore gets byte-identical pages from the same source — the chart is
the truth, the PDFs are just today's printout.

## House rules the tools live by

- Ears first: every output exists in a spoken or listenable form.
- Your word beats statistics; your playing beats guesswork.
- The demo is ideas, not gospel — bends, vibrato and micro-timing stay
  with the players. What survives is the line.
- Nothing fails silently. If it compiled, it says what it wrote; if it
  refused, it says why in one sentence.
