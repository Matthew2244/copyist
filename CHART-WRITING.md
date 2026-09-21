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
- **Piano, organ and harp come out on the grand staff.** Play the part
  in with both hands and the build separates them by what a pair of
  hands can physically reach — a bass note you're still holding keeps
  that hand where it is. On any instrument, a note that keeps ringing
  under the line (a low guitar string, a pedal tone) prints as its own
  held voice instead of being chopped at the next attack, and the
  findings name the bars where that happened so you can proofread them.
- `meter:` takes any signature — 3/4, 6/8, 5/4, 12/8, whatever the
  tune is. Beats in chords and hits count in the meter's own pulses
  (in 6/8, `@4` is the fourth eighth). In a compound meter like 6/8 or
  12/8, `tempo:` is the dotted-quarter figure — the number you'd give
  the drummer — and the page prints it that way. Mid-chart tempo changes are one
  line in a section: `at bar 5: tempo 96` — and slowdowns and
  speed-ups in words (`molto rit.`, `accel.`, `a tempo`) print
  verbatim wherever you put a text.
- **The meter can change mid-tune** the same way: `at bar 1: meter 6/8`
  at the top of the section that goes to six, `at bar 1: meter 4/4`
  where it comes back — bar numbers are section-relative, like every
  `at bar`. Every part shows the new signature, and a resting player's
  multirest breaks there so nobody counts through a change they never
  saw. Record the tune with the meter changes in your DAW project and
  the exported demo carries them; the `new` interview reads them and
  writes the `at bar` lines for you, and `from demo` lines land on the
  right bars either way. Two things to know: a single `from demo`
  figure can't straddle a change (split it at the barline — the error
  tells you where), and going between 6/8 and 4/4 without declaring a
  new tempo keeps the quarter note steady, which the findings will
  mention in case that's not the feel you meant.
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
to bass, because singers are instruments too and nobody gets left out — plus a generic `voice` when a singer is just "the vocal." The drummer is in, and so is the whole percussion section — congas, bongos, timbales, cowbell, claves, shaker, tambourine, guiro, triangle, snare, bass drum, cymbals, tam-tam and more, plus a generic `percussion` chair for the aux table: percussion clef, no key signature, grooves, kicks and words (notation from a played demo is future work for the unpitched family). Chimes, crotales, steel pan and hand bells are pitched and play real lines. The cowbell is a family (cha-cha, mambo, bongo bell), the world section is seated (doumbek, frame drum, pandeiro, surdo, tabla, taiko and friends), the effects rack too (vibraslap, ratchet, thunder sheet, rainstick...), and "bells" means the glockenspiel, like every band room says it. And the band list speaks nicknames — `kit`, `vibes`, `upright bass`, `keys`, `rhodes`, `bone`, `bari`, `fiddle` — the same courtesy the bandstand words get.
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

- **A lick you'll use more than once gets a name.** Define it up top,
  place it anywhere by name:

      figure turnaround kick, 2 bars:
        from midi "greenline-trumpet.mid", bars 12-13

      section B, 12 bars, label "Solos", open
        trumpet: figure turnaround kick at bar 11, straight, marcato

  `from midi` runs your playing through the same door as any demo line
  — it comes out written for whichever part plays it, and the grid and
  phrasing words ride along. `from xml` lifts written bars exactly from
  an engraving ("play this exact"), articulations and all — lift into a
  like instrument, since the notes come over as written. And for a short
  lick you'd rather just SAY, `notes:` writes it in words — concert
  pitch, like everything spoken:

      figure bass break, 1 bars:
        notes: rest q, triplet( F2 e, A2 e, C3 e ), Eb3 q, E3 q

  Durations are w h q e s, a dot for dotted, + for tied, `rest <dur>`,
  and `triplet( ... )` for the triplet figures. The notes must fill the
  declared bars exactly, or the build tells you both counts. Define a
  figure and never place it, and the findings will tell you.
- **Singers get their words the same way — and you write them the way
  you'd say them.** A `lyrics:` line after a figure's source, or
  `lyrics "..."` riding a from-demo line:

      singer: from demo bars 2-13, straight, legato, lyrics "Greenline
      rolling home / now / windows shine / all night / rattle on /
      steel song / carry me / uptown / far / down the line /
      take me home / home"

  No hyphen-counting: Copyist splits the words into syllables itself
  and the findings name every split it made, so you can overrule any
  it got wrong — your own hyphens always win. Slashes group the words
  by PHRASE, and each group lands on one phrase of your melody (the
  phrases are wherever your line breathes — where a rest prints; a
  quick quarter-note breath rounds away at chart altitude, so a breath
  that should anchor a phrase wants a half-beat of real air, or skip
  the slashes and let the words ride note for note). Get
  a phrase wrong and the build names it: "the phrase at bar 4 has 3
  notes but 'windows shine on' gives 4 syllables." Don't know the
  shape? Put in anything ("la / la") and the refusal reads the whole
  melody back: "bar 2: 5 notes; bar 3: 1 note; ..." — then you write
  to it. An underscore holds a syllable over one more note (a
  melisma), and the read-aloud sings every word on its note — "F 4
  'Green', A flat 4 'line'" — so you hear exactly where each word
  landed before a singer ever does. Words riding in a from-xml figure
  come along automatically.
- **First and second endings** live inside a repeated section: the
  declared length is one pass, the way you'd say it on the stand —

      section A, 12 bars, label "Head", repeat 2x
        chords: F7, Bb7, F7, Cm7 F7, Bb7, Bdim7, F7, Am7 D7, Gm7, C7
        ending 1, 2 bars: chords: F7 D7, Gm7 C7
        ending 2, 2 bars: chords: F7, F7

  The page gets the brackets and repeat dots where players look, the
  read-back says "12 bars a pass, with 2 endings" and speaks each
  ending's changes, and the listen MP3 takes the first ending, jumps
  back, and takes the second — a trimmed listen lands where the band
  actually reaches that bar, not where the printed number sits.
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

## How much to write, and how the pages dress

    tenor: from demo bars 2-13, simplified
    guitar: from demo bars 2-5, rhythmic slashes

`simplified` keeps your line but smooths it — ornaments and flicks are
absorbed, the rhythm lands on the eighth, and the findings say exactly
what was let go. `rhythmic slashes` is the comping level: your played
RHYTHM prints on slash noteheads with the changes above, and the
voicings stay yours on the night.

And the chart says how its pages look:

    look: jazz, measure numbers

`jazz` is the big-band hand (MuseJazz), `handwritten` the looser
script (Petaluma), `engraved` the clean classical serif (Edwin) —
which is also what you get with no look: line at all; `plain` keeps
plain type. Copyist draws every page itself now and dresses the
words — title, chords, lyrics, texts — in the look's own face,
embedded in the PDF so it reads the same on any machine. Add
`landscape`, `staff 2.0` for bigger print — easier for low-vision
readers — and `measure numbers` for a number on every bar. One line,
every page and part agrees.

## The apps

On the Mac, **Copyist** lives in Applications: a menu of dialogs over
the same brain — build, check, open a part's read-aloud in TextEdit,
and the settings desk. On Windows, the `windows` folder holds
**Copyist.bat** — the same menu in native Windows dialogs (Python
from python.org is the one requirement). The terminal `chart` command
does everything either app does, and more.

## The settings desk, and shortcuts

Copyist keeps four defaults, and every one tells you what it is set
to before you change it:

    chart settings
    chart set composer=Matthew Whitaker
    chart set look=jazz          # charts without a look: line dress this way
    chart set notify=yes         # your phone hears every build land
    chart set open=yes           # the score PDF pops up when a build lands

`composer` prefills the interview so your name lands on every new
chart without typing it. The notify ping is quiet — a note you can
read later, not an alarm. And every command has a one-letter
shortcut: `chart tune.chart c` checks, `b` builds, `r` reads, `p`
lists the band, `d` diffs, `l` bounces the listen, `n` interviews.

## Borrowing lines — double, cue, and the build

    section C, 12 bars, label "Head out"
      trumpet: double tenor

    section B, 12 bars, label "Solos", open
      singer: cue trumpet
      build: add trumpet at 11

`double` puts another part's line on this part's page, rewritten for
THIS player's key and clef — the classic unison out-head is one line of
chart. `cue` prints another part's line small, labelled "(trumpet
cue)", never played and never counted in your range — it's there so you
can find your entrance. `build: add trumpet at 11` prints "+trumpet" in
every part at that bar, the montuno entrance cue. And `on pass 2: mute
cup` tags its instruction "(2x only)" inside a repeated section.

## Saying how it goes — the words you'd use on the bandstand

All of these ride on a `from demo` line, after commas:

    trumpet 1: from demo bars 10-17, eighths, marcato
    tenor: from demo bars 18-19, sixteenth triplets, scoop first, fall
    all: text "laid back" at bar 1
    trombone: dyn f at bar 1, dyn sfz at bar 8 beat 4+

- **Grid words** — `eighths`, `sixteenths`, `triplets`, `eighth
  triplets`, `sixteenth triplets`. Your word beats the math: if you say
  the bars are eighth notes, the page prints eighth notes.
- **Phrasing is yours to ask for, in your own words.** Add `legato`
  to a from-demo line and the slurs follow your playing — where you
  breathed, the slur breaks. Add `ghosts` and the notes you played way
  under the others print in parentheses, the way a funk bass part
  should. Add `straight` when you played swung but the page should
  show straight eighths — onsets snap to the eighth grid and the note
  lengths stay yours (`eighths` is different: it means the line IS
  eighth notes, and will shorten longer values to say so). None of
  this happens unasked, and if you ask for phrasing your take doesn't
  support, the findings say so instead of guessing. And when your
  `feel:` says swing or shuffle, the listen MP3 actually swings —
  the pages keep the straight-eighth convention with the feel marked
  in words, the way players expect.
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
The demo MIDI travels beside the chart, and anyone with the repo gets
byte-identical results from the same source — the chart is the truth,
the PDFs are just today's printout. The listen MP3 needs no other
software at all: Copyist plays its own pages, with real swing, honest
dynamics, and each part seated in its own spot in the stereo field.
Only the PDF step still asks MuseScore.

## The build has your back

Every build's findings open with each part's fate, section by section —
"trumpet — Head: your line; Solos: your line; Head out: doubles the
tenor" — so an accidental twelve-bar rest in the lead alto is read back
in text before it is ever printed, and a part that never plays a single
bar gets called out loudly in case that wasn't the plan. If your saved
read-alouds are older than the chart, check says so instead of letting
you proofread yesterday. And `--count-in` puts a bar of click in front
of the listen MP3 — high tick on one — so you can play along like it's
a session; add a number for more bars. The from-bar trim still lands on
the music, past the click.

## House rules the tools live by

- Ears first: every output exists in a spoken or listenable form.
- Your word beats statistics; your playing beats guesswork.
- The demo is ideas, not gospel — bends, vibrato and micro-timing stay
  with the players. What survives is the line.
- Nothing fails silently. If it compiled, it says what it wrote; if it
  refused, it says why in one sentence.
