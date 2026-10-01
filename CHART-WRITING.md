# Writing a chart

This is the guide for the person writing the music, not the person
writing the code. A chart is a plain text file. Any screen reader can
read it, any editor can edit it, and it shares like any file, because
it says what you would say to the band. You type it the way you'd say
it, run one command, and out come the conductor score, a part per
player, a spoken version of every part, and a recording of exactly
what the pages say. The recording uses real recorded instruments when
the sample shelf is installed (`chart sounds` shows it) and a plain
synth otherwise, so you can proofread with your ears before a single
player sees it. Your slash bars play too: the listen realizes drums,
bass and comping from your own chord symbols, while the pages keep
their slashes.

The worked example below is an invented tune called *Uptown Local*.

## The header: who, what, where

    title: Uptown Local
    composer: Your Name
    key: F minor
    meter: 4/4
    tempo: 96
    demo: uptown-local-horns.mid
    countin: 1
    dynamics: by hand

- `demo:` names the MIDI file you played the horn lines into. The chart
  pulls real notes from it. Your playing is the documentation.
- **Piano, organ and harp come out on the grand staff.** Play the part
  in with both hands and the build separates them by what a pair of
  hands can physically reach; a bass note you're still holding keeps
  that hand where it is. On any instrument, a note that keeps ringing
  under the line (a low guitar string, a pedal tone) prints as its own
  held voice instead of being chopped at the next attack, and the
  findings name the bars where that happened so you can proofread them.
- `meter:` takes any signature: 3/4, 6/8, 5/4, 12/8, whatever the tune
  is. Beats in chords and hits count in the meter's own pulses (in
  6/8, `@4` is the fourth eighth). In a compound meter like 6/8 or
  12/8, `tempo:` is the dotted-quarter figure, the number you'd give
  the drummer, and the page prints it that way. Mid-chart tempo
  changes are one line in a section, `at bar 5: tempo 96`, and
  slowdowns and speed-ups in words (`molto rit.`, `accel.`,
  `a tempo`) print verbatim wherever you put a text.
- **The meter can change mid-tune** the same way: `at bar 1: meter 6/8`
  at the top of the section that goes to six, `at bar 1: meter 4/4`
  where it comes back. Bar numbers are section-relative, like every
  `at bar`. Every part shows the new signature, and a resting player's
  multirest breaks there so nobody counts through a change they never
  saw. Record the tune with the meter changes in your DAW project and
  the exported demo carries them; the `new` interview reads them and
  writes the `at bar` lines for you, and `from demo` lines land on the
  right bars either way. Two things to know: a single `from demo`
  figure can't straddle a change (split it at the barline; the error
  tells you where), and going between 6/8 and 4/4 without declaring a
  new tempo keeps the quarter note steady, which the findings will
  mention in case that's not the feel you meant.
- `countin: 1` says your DAW file opens with one count-in bar. From then
  on, you speak your DAW's bar numbers everywhere in the chart, and every
  spoken read-back uses them too. Only the printed page counts from one.
  Players never see your count-in.
- `dynamics: by hand` means you'll dictate the dynamics. Leave it out and
  the build reads your expression pedal (CC 11) instead and drafts marks
  for you to correct.
- **Accidentals spell the way a copyist spells them.** Say `key: D
  minor` rather than `key: F` for a minor tune: a minor key raises its
  sixth and seventh, so D minor's leading tone prints C sharp, never D
  flat. A note outside the key takes its spelling from the chord above
  it, so a G sharp under an E7 in C prints G sharp. A note the key
  signature already names keeps the key's spelling, whatever chord
  sits in the bar.
- **A transposing player never reads past six sharps or flats.** A
  tune in B major puts the alto sax in G sharp major, eight sharps, so
  Copyist respells the alto's part in A flat, the way published parts
  do; the notes, the signature and the chord symbols all move together.
  Every key from seven flats to seven sharps, major and minor, is
  checked through every transposing instrument, including clarinet in
  A, E flat clarinet, alto flute and trumpet in C.

## The band

    band:
      alto = alto sax, demo "alto"
      tenor = tenor sax, demo "tenor" octave -1
      trumpet 1 = trumpet, demo "tpt 1"
      trombone, demo "bone" octave -1

Each line: a label you'll use in the chart, the instrument (which sets
the transposition, clef, range and playback sound), and which track of
the demo holds that player's material.

A bare `bass` follows the chart's feel the way a bandleader means it:
the upright on swing, a waltz, a ballad, bossa, latin or nothing said;
the electric on funk, rock, pop, R&B, Motown, reggae, hip hop or
gospel. The findings say which, and `bass = upright` or `bass =
electric bass` settles it yourself. A bare `alto` or `tenor` is the sax.

The instrument table covers the whole ensemble world. Full woodwinds
and brass, strings with their own clefs, the rhythm section, all the
mallets. Every voice part from soprano to bass, because singers are
instruments too and nobody gets left out, plus a generic `voice` when
a singer is just "the vocal."

The drummer is in, and so is the whole percussion section: congas,
bongos, timbales, cowbell, claves, shaker, tambourine, guiro,
triangle, snare, bass drum, cymbals, tam-tam and more, plus a generic
`percussion` chair for the aux table. These live on the percussion
clef with no key signature, and they take grooves, kicks, words, and
real notation lifted straight from your playing (see `from demo`
below). Chimes, crotales, steel pan and hand bells are pitched and
play real lines. The cowbell is a family (cha-cha, mambo, bongo bell),
the world section is seated (doumbek, frame drum, pandeiro, surdo,
tabla, taiko and friends), the effects rack too (vibraslap, ratchet,
thunder sheet, rainstick...), and "bells" means the glockenspiel, like
every band room says it.

The band list speaks nicknames: `kit`, `vibes`, `upright bass`,
`keys`, `rhodes`, `bone`, `bari`, `fiddle`. The same courtesy the
bandstand words get. Polyphonic instruments (piano, guitar, vibes,
organ) keep their chords. `octave -1` corrects a track that was
recorded an octave above where it sounds. That's common, and easy to
spot: if your trombone sits above your trumpets on paper, that's a
recording convention, not a voicing.

## Sections: the form, the changes, who does what

    section A, 8 bars, label "the head"
      chords: Fm7, Bb7, Fm7, Fm7, Bbm7 Eb7@3, Abmaj7, Gm7b5 C7@3, Fm7
      trumpet 1: from demo bars 2-9
      trombone: from demo bars 2-9

    section B, 8 bars, label "tenor blows", open
      chords: Fm7 x8
      tenor: solo
      all: groove "greasy - stay out of the way"

- **Say how many times round the way you'd call it.** After the bars,
  in any order: `repeat 3x`, `repeat 3 times`, `play 3 times`, `x3`,
  `3 times`, or for a vamp `vamp 4 times` (`vamp 4x`). `till cue`,
  `open`, `vamp till cue` and `repeat till cue` go round until someone
  calls it. A word the header doesn't know gets a sentence listing
  what it takes.

- **Say who cues it.** `vamp till cue, drums cue`, `till cue, cue from
  the singer`, `the trumpet cues`, `piano cues`: any part, the drummer,
  the singer, or the bandleader (a nod, no sound). The pages print
  "vamp till cue (drums cues)" and the cue-giver's own page says "(you
  cue)". In the listen the section goes round a different number of
  times every take, and on the last time round the cue-giver plays the
  cue: the drummer fills, a piano, guitar or vibes runs up the next
  chord, the bass walks up into the next root, a horn or a singer plays
  a pickup into the downbeat. Nobody named, and the drummer usually
  sets it up anyway. Every read-aloud says who to listen for.

- **Cut to anywhere.** `then cut to shout` or `on cue, cut to coda`
  jumps to that section (by name or label) when this one's done,
  skipping what's between. `then cut back to head` (or `on cue, cut
  back to A`) goes back and plays from there once more, cuts and all,
  then carries on. Leave the name off (`then cut back`) and it lands on
  the nearest `at bar N: cut back to here` (or `cut to here`) mark that
  way. The pages print "On cue, to shout" or "Back to head", and the
  findings read the whole walk back in bar numbers.

- **Write bar ranges however you'd say them.** `bars 2-9`, `bars 2 to
  9`, `bars 2 through 9` and a typed dash all work, and one bar is just
  `bar 5`.

- **A lick you'll use more than once gets a name.** Define it up top,
  place it anywhere by name:

      figure turnaround kick, 2 bars:
        from midi "greenline-trumpet.mid", bars 12-13

      section B, 12 bars, label "Solos", open
        trumpet: figure turnaround kick at bar 11, straight, marcato

  `from midi` runs your playing through the same door as any demo line.
  It comes out written for whichever part plays it, and the grid and
  phrasing words ride along. `from xml` lifts written bars exactly from
  an engraving ("play this exact"), articulations and all; lift into a
  like instrument, since the notes come over as written. And for a short
  lick you'd rather just SAY, `notes:` writes it in words, concert
  pitch, like everything spoken:

      figure bass break, 1 bars:
        notes: rest q, triplet( F2 e, A2 e, C3 e ), Eb3 q, E3 q

  Durations are w h q e s, a dot for dotted, + for tied, `rest <dur>`,
  and `triplet( ... )` for the triplet figures. The notes must fill the
  declared bars exactly, or the build tells you both counts. Define a
  figure and never place it, and the findings will tell you.
- **Singers get their words the same way, and you write them the way
  you'd say them.** A `lyrics:` line after a figure's source, or
  `lyrics "..."` riding a from-demo line:

      singer: from demo bars 2-13, straight, legato, lyrics "Greenline
      rolling home / now / windows shine / all night / rattle on /
      steel song / carry me / uptown / far / down the line /
      take me home / home"

  No hyphen-counting: Copyist splits the words into syllables itself
  and the findings name every split it made, so you can overrule any
  it got wrong. Your own hyphens always win. Slashes group the words
  by PHRASE, and each group lands on one phrase of your melody. The
  phrases are wherever your line breathes, which is where a rest
  prints; a quick quarter-note breath rounds away at chart altitude,
  so a breath that should anchor a phrase wants a half-beat of real
  air, or skip the slashes and let the words ride note for note. Get
  a phrase wrong and the build names it: "the phrase at bar 4 has 3
  notes but 'windows shine on' gives 4 syllables." Don't know the
  shape? Put in anything ("la / la") and the refusal reads the whole
  melody back ("bar 2: 5 notes; bar 3: 1 note; ..."), then you write
  to it. An underscore holds a syllable over one more note (a
  melisma), and the read-aloud sings every word on its note, "F 4
  'Green', A flat 4 'line'", so you hear exactly where each word
  landed before a singer ever does. Words riding in a from-xml figure
  come along automatically.
- **First and second endings** live inside a repeated section. The
  declared length is one pass, the way you'd say it on the stand:

      section A, 12 bars, label "Head", repeat 2x
        chords: F7, Bb7, F7, Cm7 F7, Bb7, Bdim7, F7, Am7 D7, Gm7, C7
        ending 1, 2 bars: chords: F7 D7, Gm7 C7
        ending 2, 2 bars: chords: F7, F7

  The page gets the brackets and repeat dots where players look, the
  read-back says "12 bars a pass, with 2 endings" and speaks each
  ending's changes, and the listen MP3 takes the first ending, jumps
  back, and takes the second. A trimmed listen lands where the band
  actually reaches that bar, not where the printed number sits.
- **Fills and breaks** are said the way you'd call them on the stand:

      section A, 8 bars
        fill into bar 5 from beat 3
        at bar 7: break, 2 bars, fill into it
        fill into the next section

  The drummer fills exactly there and the band lands on the one. In a
  break the rhythm section hits the downbeat together and stops, and
  the soloist or the tune carries on alone until the band comes back.
  The drum part says Fill and every part says Break.
- Chords split a bar evenly unless you place them: `Eb7@3` is "E flat
  seven on beat three", and off-beats take any spelling you'd use,
  `4+`, `4.5`, or `and-of-4`. The format meets your habit.
- `from demo bars 2-9` lifts YOUR played line, bars 2 to 9 of your DAW,
  cleans it up (your lay-back is measured and kept as feel, not printed
  as wrong rhythms), and lands it at the same bars of the chart. If
  those bars sit outside the section you wrote it in, it lands at the
  top of that section instead and the findings say so; `at bar 3`
  moves it anywhere you like.
- **The same line on a drum or percussion part writes a real drum
  book.** Kick and snare on their own lines, cymbals with x heads, the
  open hat circled, the ride bell a diamond. When cymbals and drums
  both play, the page splits into the two voices drummers expect,
  cymbals stems up and kick, snare and toms stems down, and folds back
  to one voice wherever a family sits out. Durations read the way
  drummers read: an eighth-note hat pattern prints as eighths, a lone
  crash gets a beat and rests, and a drum hit never ties. A bar
  identical to the one before it prints as the repeat sign with the
  count over every fourth, so a long groove reads as a groove. Hand
  percussion has its own staff dialect, bongos to timbales to the
  shaker, and reads as one voice: a conga player's mutes and open
  tones share one line, the way conga parts are written. Add `ghosts` and your quiet snare notes print in
  parentheses, from your own played velocities. And the read-back
  speaks drummer, "beat 3, eighth together, snare and closed hat",
  never a pile of note names.
- `solo` prints "Solo" and puts slashes under the changes. The soloist
  reads slashes, never a page of empty bars, which look like
  unfinished engraving. Everyone else in the section just rests, and
  their wait collapses into a multirest with the section label (say
  "flute solo" in the label) telling them who's blowing while they
  count. `groove` prints slashes too, with your words above.
- A part you don't mention rests. The read-back tells you every part's
  fate per section, so an accidental eight-bar rest in the lead alto is
  heard in text before it is ever printed.

## How much to write, and how the pages dress

    tenor: from demo bars 2-13, simplified
    guitar: from demo bars 2-5, rhythmic slashes

`simplified` keeps your line but smooths it: ornaments and flicks are
absorbed, the rhythm lands on the eighth, and the findings say exactly
what was let go. `rhythmic slashes` is the comping level: your played
RHYTHM prints on slash noteheads with the changes above, and the
voicings stay yours on the night.

And the chart says how its pages look:

    look: jazz, measure numbers

`jazz` is the big-band hand (MuseJazz), `handwritten` the looser
script (Petaluma), `engraved` the clean classical serif (Edwin),
which is also what you get with no look: line at all; `plain` keeps
plain type. Copyist draws every page itself and dresses the words
(title, chords, lyrics, texts) in the look's own face, embedded in
the PDF so it reads the same on any machine. Add `landscape`,
`staff 2.0` for bigger print, easier for low-vision readers, and
`measure numbers` for a number on every bar. One line, every page
and part agrees.

## The apps

On the Mac, **Copyist** lives in Applications: a real app over the
same engine, with two designed looks (Dark Stage and Manuscript) or
the system's own. It has five tabs, and Command 1 to 5 go straight to
one: **Chart** (open, start or bring in a chart), **Build** (build,
check, what changed), **Listen and read** (start at any bar, tick the
players you want to hear alone, or pick a part to read aloud),
**Conversation** (tell Copyist the tune, name keyswitches and drum
notes) and **Settings**, which Command comma opens too. VoiceOver lands
on each tab's heading when you arrive, so it always says where you
are, then says once what the tab holds. The work lives in a Chart menu
with keys: Command B builds, Command K checks, Command D says what
changed, Command P plays the last listen, Command period stops. A
build says each step aloud as it goes (Settings turns that down to
just the finish), shows a real progress bar, and keeps going if you
change tabs or open a second window for another chart. Its transcript
is one line per thing said, so VoiceOver walks the findings a line at
a time. On Windows, the `windows` folder holds **Copyist.bat**: the
same five tabs in a native window NVDA and JAWS read well, Control 1 to
5 between them, Control B, K, D, L and R for the work, and the roadmap
conversation in a real console. Python from python.org is the one
requirement there. The terminal `chart` command
does everything either app does, and more.

## The settings desk, and shortcuts

Copyist keeps your defaults, and every one tells you what it is set
to before you change it:

    chart settings
    chart set composer=Matthew Whitaker
    chart set look=jazz          # charts without a look: line dress this way
    chart set notify=yes         # your phone hears every build land
    chart set open=yes           # the score PDF pops up when a build lands

`composer` prefills the interview so your name lands on every new
chart without typing it. The notify ping is quiet, a note you can
read later, not an alarm. The desk also holds `sounds_dir` (where the
sample shelf lives), `midi` (the folder your played files start in),
`quant` (how Copyist reads the rhythms you played), and `countin`
(offered
when a demo says nothing itself). And it says where finished files
go: `pages_to`, `listens_to` and `spoken_to` each name a folder for
that kind of file, and empty keeps everything with the build;
`braille_to` does the same for braille.

`exports` says what a build makes, any mix of eight things: `pages`
(the PDF charts), `listen` (the MP3), `braille` (a .brf file for each
part), `braille pages` (the braille drawn as dots), `read-alouds`,
`ireal` (the chart as an iReal Pro link, and a page to tap it from on
your phone), `midi` (the band as you hear it in the listen, one track
per player, swing and made-up parts included, ready for your DAW) and
`chords` (a plain chord sheet with barlines). Out of the box it is
pages, listen, braille and read-alouds; the rest are yours to add.
Anything iReal Pro can open, Copyist can read back: the link is proven
by bringing it in again, bar for bar.

    chart set exports=pages, braille       # charts and braille, no audio
    chart set exports=all
    chart tune.chart --exports "listen"    # just this once

In the Mac app, Settings has a switch for each one under **What a
build makes**, and every switch says whether it is on. The MP3 alone
and the braille alone each have their own button on the Build tab.

**The sample shelf** is the band's recorded instruments, about 34 GB,
installed where you choose and only when you ask:

    chart sounds list              every library: what it plays, size, licence, installed or not
    chart sounds install band      everything the band plays
    chart sounds install piano, kit   just those
    chart set sounds_dir=/Volumes/Samples/Copyist   put the shelf elsewhere
    chart set use_samples=no       play the plain built-in synth instead

Copyist fetches each library from its own project, unpacks it, makes
what its reader needs (WAV twins for FLAC, 16-bit copies of 24-bit
files; ffmpeg is needed for the FLAC ones) and builds its own extras
(tenor, saxello, vibraphone, trombone falls, organ) from them, then
writes CREDITS.txt on the shelf naming who made each. Singers sing on
the SoundFont's synth voice, sitting in the band where you can hear the
line without it taking over; it comes with the
band download. The sampled VocalSet choir is an optional extra. Every library is CC0,
CC-BY or MIT. In the Mac app it's the Sounds group in Settings: each
library with a switch, where it goes, and one button to install; on
Windows, "The sound shelf" on the Settings tab.

**What the listen makes up** is yours to switch off, each one on out
of the box: `listen_grooves` (the rhythm section playing the slashes),
`listen_solos`, `listen_backgrounds`, `listen_endings` (the band's own
ending when the chart names none), `listen_mutes`, `listen_brushes`
and `listen_builds` (the band building through the tune).

    chart set listen_solos=no      # soloists rest instead of blowing
    chart set listen_endings=no    # stop where the notes stop

Anything you write always plays; these only govern what the band
invents where the page leaves it to them, and a build with one off says
so in its findings. In the Mac app they are switches under **What the
listen makes up** in Settings; on Windows, the same corner of the
defaults desk.

Any one export can also take just some of the tune, some of the band,
and its own look:

    chart tune.chart --bars 9-24                  # those bars, as printed
    chart tune.chart --parts "trumpet 1, alto"    # just those parts
    chart tune.chart --parts score                # just the score
    chart tune.chart --parts parts                # every part, no score
    chart tune.chart --look handwritten           # this export's pages
    chart tune.chart preview --look engraved      # a sample page first

A bar range prints exactly those bars, numbered as on the full pages,
with the key, time and tempo carried in; its files are named for the
range, so the full ones stay. Picking parts for the listen gives just
those players; a bar range cuts it from the whole performance, so
repeats and a D.S. still play as written. In the Mac app, **Export…**
on the Build tab (Command E) asks all of it in one sheet: the whole
song or from and to bars, a switch for the score and for every part,
what to make, and the look, with **Show a sample page** drawing the
first bars in that look right in the sheet. On Windows, **Export**
(Control E) asks the same questions in turn.

And every command has a one-letter
shortcut: `chart tune.chart c` checks, `b` builds, `r` reads, `p`
lists the band, `d` diffs, `l` bounces the listen, `n` interviews,
`e` is the roadmap conversation.

## Keyswitches: the articulations you played

If your demo switches articulations with keyswitches, Copyist reads
them. The keys themselves (far below or above the instrument's range)
come out of the notes, so no stray low C prints, and each one's name
becomes what a copyist would write: staccato dots, marcato, tenuto,
slurs over the legato, "pizz." where it starts and "arco" where the bow
comes back, mutes, "sul pont.", tremolo strokes, trills, falls, doits,
scoops. The listen plays the strings' real pizzicato and tremolo
samples.

Tell it what the keys mean once. In the chart:

    keyswitches "My Violins":
      C1 legato
      D1 staccato
      E1 pizzicato

    band:
      violin, demo "strings.mid", keyswitches "My Violins"

Middle C is C4 (MIDI 60); if your library calls it C3, write the MIDI
number instead (`24 legato`), and the findings always name both. Or
save the map for every chart that uses that patch:

    chart keyswitches set "My Violins" F#1 tremolo
    chart keyswitches show "My Violins"
    chart keyswitches

Easiest of all: after a build, if any key has no name, the app shows
Name the keyswitches (or run `chart yourtune.chart keys`). It asks
about each key in turn ("violin: F#1 (MIDI 30) is in effect in bar 5.
What does it do?"), saves your answer in the chart's own list or a saved
map, links the part to it, and Enter skips one.

`chart keyswitches from-logic` brings in all of Logic Pro's own
articulation sets (Studio Strings, Horns and Bass) as ready maps, named
like "Logic Studio Strings - Studio Violins". A library's names can stay
as the library wrote them ("Violins - Spiccato", "SHORTS marcato"):
Copyist finds the musical word inside, ignores the sampler's own modes
("Expressive Long", "Down/Up (Auto)"), and prints anything else it
doesn't know as the word itself. A key you haven't named yet is listed
in the findings with the bars it covers.

**When you hit the key doesn't matter.** You play the take, and a
switch lands where it lands, in any library. Hold a note as long as
you want and trigger a fall, doit, shake, trill, tremolo, flutter,
growl, gliss or crescendo whenever you like: it marks the note you're
holding. It marks the same note if you pressed it just before, held it
down under the note, or hit it right as you let go, and it never
carries on to the notes after. Switches that change how a note starts
(staccato, marcato, legato, pizz., arco, mutes) count for a note if
you press them before it or up to an eighth into it, then stay in
effect like the sampler's. Pressed deeper into a held note, they're
getting ready for the next one.

## Drum takes from EZdrummer and Superior Drummer

Toontrack's drum instruments don't use the General MIDI drum map: their
note 39 is a snare roll where General MIDI has a hand clap, 40 is a
rimshot, the low notes are hi-hat openings. Tell Copyist the take's map
on the band line and it reads the kit that was played:

    drums = drum set, demo "take.mid", drummap "Toontrack"

(`EZdrummer` and `Superior Drummer` work as names too.) XLN Audio's
Addictive Drums 2 is built in the same way, from its own keymap:
`drummap "Addictive Drums 2"` (or `XLN`, `AD2`). Its six cymbal slots
read as crashes, since each AD2 kit loads its own cymbals, and its Flexi
slots read as "kit percussion" until you name them; Name the drum notes
asks only about those, and your answers add to the built-in map.
Most other drum
libraries (Tony Royster Jr., Addictive Drums, any Kontakt kit) keep
their map inside the plugin, so tell Copyist once: Name the drum notes
in the app, or `chart yourtune.chart drums`. It asks which library the
take was played on, then goes through each note the take uses ("note
39, played 20 times, first in bar 14. General MIDI calls it clap. What
is it on your kit?"); say it the way a drummer does, snare roll, cross
stick, ride bell, china, and Enter keeps the General MIDI name. The
answers are saved as that library's drum map and the part uses it from
then on. Name the stroke along with the piece when the kit has one: a
note you call "snare ghost" prints in parentheses every time, whatever
its velocity, and only that note, never the kick beside it. A flam
prints a slashed grace note, a drag two small ones, a rim shot a
slashed notehead, and a choke the comma after the cymbal. The
read-aloud says each one ("flam on the snare", "crash choked").
Hand percussion counts too: conga (open, slap, low), bongo, timbale,
shaker, cabasa, woodblock, claves, triangle, agogo and guiro. A drum
take that uses notes General MIDI doesn't have gets a
line in the findings pointing here.

## Road maps: D.S., D.C., the coda

Write them where they sit, as timed events in the section:

    section A, 8 bars
      chords: F7 x2, Bb7 x2, F7, C7, F7, C7
      at bar 1: segno
      at bar 6: to coda

    section B, 8 bars, repeat 2x
      chords: Bb7 x4, F7 x4
      at bar 8: d.s. al coda

    section coda, 4 bars
      chords: F7, Bb7, F7, F7
      at bar 1: coda

`d.s. al fine` with a `fine`, and `d.c.` for back to the top, work the
same way. The page prints the sign and the words, the band plays the
walk (repeats the first time, not after the jump), the read-aloud says
"the sign. The D.S. comes back to this bar", and the findings read the
whole walk back in bar numbers so you can check it before anyone plays
it. Forget the sign and Copyist tells you which one is missing.

## The tune-level words a working book prints

The header takes the credits a real book carries. `lyricist:` prints
"Lyrics by ...", `from:` prints *from "..."* under the title, `rev:`
adds the small revision date, and `number:` puts the setlist number
in brackets top right. Mid-tune, `at bar 12: key Eb` changes key,
and every part's page restates its own written signature right
there. Your trumpet player gets the new key in trumpet, not in
concert. The tempo words go straight after the bar too: `at bar 12: rit.`,
`at bar 16: a tempo`, `molto rall.`, `accel.`, `slow down`, `fade out`
print and play just as `text "rit."` does. `at bar 8: fermata` is the
hold at the end of a phrase: the
sign lands on that bar's last note or rest in every part, and the
listen holds time there for everybody at once, which is the whole
point of a fermata. On any part's line, `cresc bars 2-4` or
`dim bars 6-8` draws the hairpin and plays the swell, and
`dyn subito p` says it the way the page does. A `feel:` naming 16ths
("swing 16ths groove") swings the half-beat in the listen.

## Borrowing lines: double, cue, and the build

    section C, 12 bars, label "Head out"
      trumpet: double tenor

    section B, 12 bars, label "Solos", open
      singer: cue trumpet
      build: add trumpet at 11

**Explode**, the way MuseScore and Sibelius do it: play the voicings
on one track (piano, a horn played in chords, strings) and deal them
out:

    group section: trumpet, alto, tenor, bone
    section shout, 8 bars
      piano: from demo bars 33-40
      section: explode piano

The top note goes to the highest-reaching chair, the next down, and so
on, whatever order the group is typed in; a chord shorter than the
group doubles evenly when it divides and otherwise repeats its lowest
note; more notes than chairs drop the extras. Each chair is written for
its own horn, a note past an instrument's range moves an octave in (the
findings say so), and the findings say "exploded from the piano".
`divisi <part>` does the same and prints "div." for a string section.
If the source is one of the chairs (the trumpet track played in
chords, exploded across the horns), it keeps the top voice.

**Soli**, the arranger's staple: write the lead once and let the
section voice it from the chords. `saxes: soli on alto` (or `horns:
harmonize trumpet`) gives each chair its own voice under the lead,
highest-reaching chair on top: a chord tone in the melody is voiced
close below it, a passing note moves in parallel scale thirds, and a
major chord voices as a sixth unless the melody sits on the major 7th.
Four voices or more come out in drop 2 (the second voice down an
octave), and with five or more the bottom chair plays the chord's root
down in its own register, the big band's floor. Every voice sits in its
chair's comfortable range. Say `soli on alto, close` to keep it tight. If the lead is one of the chairs it keeps the
melody. The findings say "soli under the alto, voiced from the
changes"; a note past a horn's range moves an octave in and says so.

`double` puts another part's line on this part's page, rewritten for
THIS player's key and clef; the classic unison out-head is one line of
chart. Say the octave when the double sits off it: `tenor: double
trumpet an octave down` (or `an octave up`, `two octaves down`, `8va`,
`8vb`); the page, the listen, the findings and the read-aloud all move
with it, and the range report still tells you if that takes the horn
past its low note. Say an interval and the double harmonizes instead:
`alto: double flugel a sixth below`, `trombone: double trumpet a third
below`, `a 10th under`, `in thirds above`. Every note moves that many
steps along the scale of the key in force where the line starts, so the
harmony stays in the key; a chromatic note in the lead (a leading tone,
a blue note) harmonizes from the scale tone it bends. The findings and
the read-aloud say "doubles the flugel a sixth below". A horn or a singer coming back after a long rest gets a cue without
asking, the copyist's call for each entrance (made once per chart, so
the parts on every stand match build to build; only the listen is a
fresh take): after six to ten bars of rest,
or four when the entrance is off the beat, the last phrase before it
(from where the melody last breathed, one to four bars) of whoever is
most audible leading in, printed small and labelled so they can find
the way in; the findings say where each one went. A cue you place
yourself wins, and `cues: no` in the header turns them off. `cue` prints another part's line small, labelled "(trumpet
cue)", never played and never counted in your range. It's there so you
can find your entrance. `build: add trumpet at 11` prints "+trumpet" in
every part at that bar, the montuno entrance cue. And `on pass 2: mute
cup` tags its instruction "(2x only)" inside a repeated section.

## Saying how it goes: the words you'd use on the bandstand

All of these ride on a `from demo` line, after commas:

    trumpet 1: from demo bars 10-17, eighths, marcato
    tenor: from demo bars 18-19, sixteenth triplets, scoop first, fall
    all: text "laid back" at bar 1
    trombone: dyn f at bar 1, dyn sfz at bar 8 beat 4+

- **Grid words**: `eighths`, `sixteenths`, `triplets`, `eighth
  triplets`, `sixteenth triplets`. Your word beats the math: if you say
  the bars are eighth notes, the page prints eighth notes.
- **Phrasing is yours to ask for, in your own words.** Add `legato`
  to a from-demo line and the slurs follow your playing; where you
  breathed, the slur breaks. Add `ghosts` and the notes you played way
  under the others print in parentheses, the way a funk bass part
  should. Add `straight` when you played swung but the page should
  show straight eighths: onsets snap to the eighth grid and the note
  lengths stay yours (`eighths` is different: it means the line IS
  eighth notes, and will shorten longer values to say so). None of
  this happens unasked, and if you ask for phrasing your take doesn't
  support, the findings say so instead of guessing.
- **Trills and tremolos, played or written.** Play a trill into your
  demo and it comes out as one note with "tr" over it, going to the
  exact note your fingers went to: half step, whole step, a third,
  whatever you played. Play one note fast and repeated and it comes out
  as a tremolo; shake between two notes a fourth or more apart and it
  comes out as a fingered tremolo, the way string and keyboard parts
  write it. Sixteenth notes you meant as sixteenths stay sixteenths.
  This one does happen without asking, because it's how the notes you
  played are written, not phrasing added on top; the findings name
  every one, and `no trills` on the line turns it off. Typing notes,
  put the ornament after the duration: `E5 h tr` (the next note up in
  your key), `C5 h tr half`, `tr whole`, `tr minor 3rd`, `tr major
  3rd`, `tr 4th`, `tr to D#5`, `A4 h trem` (or `roll` for mallets),
  `F4 w trem to C5`. At the editing desk you can say it: "e5 half
  trill", "c quarter trill minor third", "a4 half tremolo". The
  read-aloud names each one: "trill a half step up, to F".
- **The bow, for strings.** `bass: arco at bar 9` and `bass: pizz at
  bar 17` print "arco" and "pizz." where a string player looks for them,
  the read-aloud says "arco, with the bow" and "pizz., plucked", and the
  listen changes the sound right there: the upright bass plays plucked
  until the page says arco, then bows (a short note under a staccato is
  a short bow stroke) until it says pizz. again. "bowed", "with the
  bow", "plucked", "pizzicato" and "fingered" (the bass player's word
  for it) work too, and the violins, violas and
  cellos read the same words the other way round, bowed until pizz.
- **Mutes, where they go on and off.** `trumpet: harmon mute at bar 9`
  and `open at bar 17` (or `mute cup` at the top of a section) print the
  mute where the player needs it, in their part and in the score, and
  the listen plays it: harmon thin and buzzy, cup soft and dark,
  straight bright and nasal, plunger and bucket muffled, and "con sord."
  on strings the veiled string mute. Nothing recorded exists for muted
  brass, so the band plays the open horn through the shape each mute
  cuts; it is close, not the real mute, and worth knowing.
- **The feel plays, in the band's own words.** `feel:` on the header
  or a section changes what the rhythm section plays under your slashes,
  not just the word on the page: `swing` walks, `two feel` puts the
  bass in half notes on 1 and 3, `ballad` holds long notes under a soft
  ride and brushes, `double time` doubles the walk and the ride,
  `half time` moves the backbeat to 3, `funk` brings sixteenth hats,
  ghost notes and a syncopated bass, and `1/2 time funk` does both,
  with the hats in eighths so the half-time pulse still gets its
  sixteenths. Funk is straight unless you say otherwise, even in a
  swing tune. `swung funk` (or `swing funk`, `funk shuffle`) swings it:
  the sixteenths at full time, and in `1/2 time swung funk` the
  eighths, which is the half-time shuffle. `bossa
  nova` plays the bossa bass, clave and comping, `samba` the surdo bass
  and sixteenths, and `latin`, `afro-cuban`, `mambo`, `songo` or `salsa`
  the tumbao on the and of 2 and on 4, with cascara and clave.
  `shuffle` (or `blues shuffle`) plays the shuffle, not swing: hats on
  every swung eighth, the snare ghosting the lets, the bass rocking
  root-3-5-6 up and back down. `second line` (or `New Orleans`) plays
  the parade snare and the sousaphone line, `reggae` or `one drop`
  drops the kick and rim onto 3 and skanks the chords on 2 and 4,
  `Motown` puts the snare on all four beats, and `hip hop` or `boom
  bap` plays the kick off 1 and the and of 3 (`swung hip hop` or
  `Dilla` swings its sixteenths). In 3/4, `waltz` is oom-pah-pah and
  `jazz waltz` swings: ding, ding-ga ding on the ride, the bass
  walking in three. `straight eighths`, `rock` and `pop` play a
  backbeat, and "straight" said outright beats "swing". Any word it
  doesn't know still prints, and the band plays straight time under it.
- **Solos play, and tell a story.** A line that says `solo` with
  nothing played in for it gets a soloist in the listen, planned whole
  before its first note: a short idea stated with space around it,
  answered, lifted and stretched; developed in sequences and longer
  lines as the extensions (9ths, 11ths, 13ths) come in; built to a peak,
  higher and busier, a riff or a run; then home, the idea once more and
  a long last note. Phrases cross barlines and breathe; a horn or a
  singer never plays longer than a breath, a singer scats simply, keys
  run longer lines, a bass solo stays low and spare. A repeated solo
  section is one story across every chorus. Soloists listen to each other: one
  may end on a long note, a short clipped phrase, or a line that spills
  over into the next player's first bar, and the next opens by
  answering the phrase it just heard, in its own register, and builds
  from there.
  The soloists are measured against the real players they learned
  from (prototype/bench_solos.py), and play like them: phrases as long
  as theirs with breaths as long as theirs, about two notes a beat at a
  medium tempo, sixteenth turns and double-time runs, triplet turns,
  lines that sometimes sit a whole eighth late so their passing notes
  land on the beat and their chord tones on the 'and', skips that
  outline the chord, and phrases that end on the 'and' about as often
  as on the beat, triplet arpeggios up the chord and triplet pickups
  into a line included. A solo always comes home: no phrase runs over its
  closing stretch. And whoever made up their part, a soloist who
  finished early included, comes back in for the band's last chord.
  Soloists speak the shared language too: inside their lines they reach
  for figures real players use (learned from the Weimar Jazz Database,
  each one kept only when several different players used it), over the
  chord they're on or across the change coming up, a ii-V or a V-I
  landing on the new chord. A bebop player reaches for them most, a
  lyrical one least; a figure only goes in where it joins the line
  smoothly on both sides, and every note is checked against the
  chart's own chords, so a figure learned over C7 is never played over
  C7b9.
- **The drummer changes implements.** `brushes`, `sticks`, `mallets`
  or `cross stick` in a drum line's words (`drums: groove "brushes"`)
  put them in the drummer's hands; a ballad gets brushes unless you say
  sticks. Brushes play the Swirly brush kit: the left hand stirs
  circles on the snare, the right taps the time. The same words written
  on a lifted drum part switch the kit too.
- **Mutes, written or on the spot.** A mute the chart names always
  plays. On a made-up solo or backgrounds the brass decide for
  themselves: a trumpet on a ballad may reach for a harmon or a cup, a
  trombone in a blues for the plunger, brass backgrounds behind a quiet
  solo go into cups together; the mute comes out for whatever's next. Soloists named in one section take turns in the order you call them, the
  section split between them. A pianist keeps left-hand shells under
  the line; a drummer takes a drum solo. The page keeps its slashes and
  the word, and a solo you played in from MIDI plays exactly as played,
  and the band reacts to it, not to a made-up one: they leave room where
  you're busy, fill where you breathe, and answer the phrase you
  actually played.
- **The band listens to the lead.** Whoever is making something up
  (the comping, backgrounds) hears the melody, any written line and the
  soloist, and leaves out a note a half step from what the lead is
  holding: the pianist drops the A from a Bbmaj7 while the melody sits
  on Bb. They stay under it too: with the melody up high (E4 and above),
  a voicing that would sit on top of it drops an octave, so nothing
  masks the lead. A low melody (a tenor down around Bb3) is voiced
  over, as usual. And nobody sits in the singer's spot: a comping note
  on the melody note or a step off it, in the same octave, moves an
  octave (up over a baritone, down under a soprano) or drops out, so
  the voice has its own room and nothing to fight for pitch. The bass
  keeps its line.
  The band listens to each other, not just the lead. The rhythm
  section plays in the order a band listens: the horns and singers
  first, then the bass, then the first chord player, then the second,
  each hearing what the ones before it really play in that bar. A
  chord player keeps its voicing above the bass line for as long as the
  chord rings, a walking bass that climbs included. A second comper
  never doubles the first comper's notes or sits a step off them: it
  finds its own spot for the whole voicing, usually an octave away, and
  only leaves a note to the other player when there's no room. Neither
  doubles a horn's or a singer's held note or rubs a step off it,
  unless it's catching the kicks with the section. The bass goes under
  a low written line, a bari or bass trombone. And when piano and guitar
  are both in the band and the chart doesn't say, the bandleader calls
  it per section: both comp, or one comps while the other lays out
  (likelier behind a singer, rare in a shout), a fresh call every take.
  The build names who laid out where; `guitar: groove` keeps both in.
  Behind a melody, a singer or a horn head, the band listens the way it
  does behind a soloist: the comping lays back while the line moves and
  comes forward when it holds or breathes, playing in its holes (a stab
  in the middle of a moving run is left out; one with the melody's
  attack, or on the one, supports it). The drummer hears the melody
  too: a fill waits for the phrase's last note, fills under a held note
  as always, is skipped when the line moves right to the barline, and
  never carries a fill over the barline into the melody's entrance.
  Backgrounds made up behind a soloist or a singer are voiced as one
  section, the way an arranger writes them: the top horn leads by step,
  each chair takes the next chord tone down without crossing the chair
  above, and with five or more horns the bari (or the bass trombone)
  holds the root at the bottom.
  The section's last look is an arranger's: no interval sits below its
  low limit (a third at A2 is mud, so the horn above the bottom takes a
  fifth or a seventh, the voice above moving up to make room), no two
  horns land on one note, no gap wider than an octave above the bottom,
  the 3rd and 7th always there. A horn whose note would rub with the
  soloist sits that hit out rather than jump an octave on its own and
  cross the horn next to it. Every chord player's comping voicing gets
  the same low-limit check (prototype/bench_backgrounds.py and
  bench_comping.py measure it).
  A walking bass lands a chord tone on beats 1 and 3 and passes on 2
  and 4; it doesn't lean on the 4th over a dominant, which would sound
  like a sus nobody wrote. The drummer hears the section's written hits (two or
  more horns or voices striking together) and catches the real hits: a
  short one with air after it, or a held one coming out of space (a
  long note that ends a moving phrase is a phrase end, and gets filled,
  not slammed). Kick and snare on the short ones; on the big ones the
  drummer's own choice in the moment: a crash, a choke, a hi-hat bark,
  open hat with crash and kick, the floor tom, two toms stepping down,
  the ride bell, snare and kick, or a quick lick landing the hit
  ("snare snare kick", "snare, high tom, floor tom, kick").
  Some bars the drummer plays the figure's shape on the toms, high tom
  for its top notes and the floor for its lowest. Often a snare set-up
  on the eighth before a hit out of a rest; one crash a bar at most.
  Sections, soloists and landings are marked the same way: a crash
  about half the time, otherwise another hit, the kick alone, or just
  the change in what they play. The laps of a vamp keep going without
  a crash each time round; the band coming back after a break always
  gets one. Passing notes go by without anyone voicing around them. A
  guitar beside a piano voices around the piano. Vibes the chart gives
  nothing leave the comping to the piano or guitar (two chord players
  comping at once muddy the changes; the findings say so, and `vibes:
  groove` puts them back in). A vibes, marimba or guitar solo is a
  single line; only a pianist or organist keeps a left hand under the
  solo. Every made-up solo knows the changes: each note fits the chord
  under it or steps into the next one as an approach, a riff moves with
  the chords as they go by, and a blues lick waits for a chord it
  belongs on (a dominant, a minor, a plain triad, never a major 7th).
- **Written lines are phrased, not typed in.** A horn or a singer
  reading a written line swells up to its highest note and eases off
  after, leans on an off-beat with space or a longer note after it, lets
  a short last note go, and in swing plays the on-beat eighths inside a
  run lighter so the line swings (never the phrase's peak). The band's
  last hit is the drummer's own in the moment too: crash, kick and
  snare, open hat with crash and kick, crash and floor tom, a lick into
  it; a held last chord always gets something that rings, and a short
  button may be choked.
- **The band plays like professionals.** Every chair is levelled
  before the mix (the libraries differ by as much as 45 dB raw), then
  set the way an engineer would: horns out front, trumpet just over the
  tenor, bass a few dB under, comping well under, the kit between; the
  bass and kick sit in the middle, the rest spread by role. A rhythm
  player taking a solo gets the fader pushed up. The pianist plays with
  two hands across the keyboard — a low left-hand shell, colour and
  rhythm above, on a ballad a spread tenth near the bottom and the
  rootless voicing high — in rootless A and B forms that move least,
  changing texture every couple of bars (stabs, left hand holding
  while the right answers, laying out, modal fourths where the harmony
  sits still), never the same twice running. Soloists land chord tones
  on the beat, the 3rd or 7th at each change, with approach notes
  between, and each has a personality (lyrical, bebop, bluesy,
  modern), the next one contrasting the last. The piano leaves room
  when the soloist is busy and answers when they breathe; the drummer
  drops bombs in the gaps, sets up each phrase, crashes in each new
  soloist, and fills from a whole vocabulary, never the same fill twice
  running. `listen_feather=no` stops the feathered kick in swing.
- **Soloists sing, and the band listens.** A made-up solo phrases the
  way a singer does: a phrase swells up its line and eases at the end,
  its peak leaned on; horns and voices scoop into a long opening note
  and may fall off or doit up at the end of a breath. When the soloist
  breathes, the piano or the drummer may pick up the phrase they just
  played and answer it. A drum solo is a story too: a theme developed,
  a groove, the kick leading, three against four.
- **Every build is a fresh take.** Nothing the band makes up plays the
  same way twice: a new build is a new take, and the findings name it.
  Like one? `chart set listen_take=<its number>` keeps it;
  `listen_take=same` keeps one take for every build.
- **Tight unless you say otherwise.** The band plays tight and
  confident. Say where it sits in a section's feel or as a word at a
  bar: `laid back` (or `lay back`, `behind the beat`) and the horns and
  comping sit behind the time, the bass a little less; `loose` gives it
  room; `on top` (or `pushing it`) leans ahead; `tight` locks it back
  in. A section that doesn't say goes back to tight.
- **A shout sounds like a shout.** On a held note at the end of a
  phrase in a shout, the brass and saxes make the section's call
  together: fall off it, or the trumpets shake it while the others
  hold, or just hold it; a mark the chart writes always wins.
- **The band lands the kicks together.** In a shout, the piano and the
  bass may play the horns' kicks with them (the piano punching the
  voicing, the bass the root, nothing between, so the hits have air),
  each player's call per shout; a soli line moving together isn't
  kicks, and there they comp and walk as usual.
- **The pianist strolls,** now and then: under a horn's solo the piano
  (or guitar) may lay out for the first half of the turn, the soloist
  with bass and drums alone, then come back in. Their call, about one
  turn in six; never in a trade, never under another chord player.
- **The drummer knows the form.** The bar before every road-map jump
  (a D.S., a D.C., the To Coda, a cut) gets a fill setting the band up,
  and the drum part says "Fill" there.
- **The piano leaves the bottom to the bass.** While the bass is
  playing, nothing the piano makes up goes below C3; with the bass out,
  the whole keyboard is the pianist's. The organ, which may be playing
  the bass itself, keeps its pedals.
- **Fills start and land anywhere.** A phrase-end fill starts on a
  beat or on the 'and', and lands where the drummer feels it: on the one, early on the 'and' of four, or late, carried
  over the barline onto the 'and' of one or beat two, the time picking
  up after. The landing is the drummer's call too: crash and kick,
  crash and snare, open hat and snare, open hat and kick, open hat with
  crash and kick, a choke with snare, snare and kick. A fill the chart
  writes lands where the chart says. After a fill the comping snare
  gives it a beat and a half before coming back in.
- **The count-off.** A tune starts the way a band starts one, in the
  moment: the drummer counts it in (a bar, two bars with the first in
  half time, or two beats up-tempo) on the hi-hat foot, the closed hat,
  the rim, the ride bell or the snare; or plays a simple pickup into
  bar one with no count; or counts up to a simple pickup (a few snare or tom strokes in the last
  beat or two, on the beat or starting off it) landing on bar one with
  the kick, crash and kick, crash and snare, or an open hat with the
  kick or snare; and sometimes nobody counts
  and the band just starts, more often on a ballad or a tune that opens
  on a vamp. `countoff: no` in the header starts it cold, `countoff:
  yes` always counts; `--count-in` puts the click there instead. The
  count-off is part of the song: in a swing tune its pickup swings
  like the band, and it's played at the tune's opening dynamic: a
  quiet tune is counted in softly and lands with no cymbal, a loud
  one is kicked off hard.
- **Two hands, two feet.** A drummer never hits three drums or cymbals
  at once. When the parts pile up, the drummer keeps what matters most
  (a crash, the snare, the kick, the hat foot) and drops the rest.
- **Everyone locks in, then builds.** Players start from a foundation
  and build from it, the way a band settles into a tune. The pianist
  picks a comping pattern for a four-bar phrase (a texture and a two-bar
  figure, a Charleston and a push, say), sits on it, lets the last bar
  turn it around, then keeps it, develops one bar of it, or now and then
  starts fresh; a new section starts fresh. A guitar comping in spots
  does the same. The swing drummer has a home ride pattern, a hi-hat
  foot habit and a feathered kick (or not) for the phrase, with a varied
  bar in the moment, and a snare comping idea it often carries through
  the phrase. Grooves (funk, Latin, second line) were already patterns.
  Listening still comes first: a busy soloist or melody thins the
  pattern to its first hit rather than replacing it, so it comes right
  back when the line breathes. Every choice is the player's in the
  moment, different every take.
- **The rhythm section plays like the players it learned from,** and
  is measured against them (prototype/bench_band.py). The swing
  drummer's hi-hat foot has real habits: 2 and 4, and often the chick
  on the 'ands' of 1 and 3 too; the kick drops on the 'ands' as well as
  the beats, feathered only some phrases; the snare comping spreads over
  the bar and stays lighter under a busy soloist. Swing fills are
  triplet-based, mostly snare and floor tom with the kick under the
  first stroke, a beat or two long and now and then most of a bar into
  a big new section; the buzz roll is a rare, shout-chorus sound. The
  walking bass lands on the root of a new chord about four times in
  five, the fifth or third the rest, the root always at a new section.
- **Grooves lock in and turn.** In funk, Latin, bossa, samba, baião
  and the other grooves the rhythm section locks onto its pattern, and
  at the end of a phrase it's each player's call: the bass may play the
  fifth and a half step into the next chord, or the next root early on
  the 'and' of 4; the comping may anticipate the next chord on the 'and'
  of 4. Then it's right back in the pocket.
- **Swing at every tempo.** The rhythm section plays the tempo the way
  players feel it: slow (under 100) with room for every skip on the ride,
  ghosted snare and a feathered kick; medium and medium-up as you'd
  expect; up tempo (220 and over) simpler, a plainer ride, lighter snare,
  the hat foot on 2 and 4, fewer skips in the bass, sparser comping.
- **Gypsy jazz.** Write `feel: gypsy jazz` (or `manouche`, or `django`):
  the guitar plays la pompe, a chord on every beat with a ghosted
  upstroke just before 2 and 4; the bass is in two on the head and
  walks under solos; a drummer, if there is one, is on brushes.
- **Baião and Afro 12/8.** `feel: baião` (or `forró`): the bass plays
  the 3+3+2, root, fifth, root, twice a bar; the triangle's sixteenths on
  the hi-hat, opening on each 'and'; the zabumba's low note on the kick
  on 1 and the 'a' of 1, its stick on the 'ands' of 2 and 4; the comping
  on the same 3+3+2. `feel: afro 12/8` in 6/8 or 12/8: the bembé bell on
  the ride bell, the kick on the dotted quarters, the hat foot on 2 and 4
  of the twelve, the toms answering now and then; the bass on the root,
  anticipating the fifth, and leading into the next chord.
- **Chokes where they belong.** A choked cymbal is a drum-solo sound
  and a last-hit sound, with the whole band landing together. Keeping
  time behind the band, in a landing after a fill, a section mark or a
  catch of the horns' backgrounds behind a soloist, it's rare: the
  drummer has to really feel it.
- **An open drum solo tells a story.** A long one is played idea by
  idea, about one every seven beats, each finishing with a breath: it
  starts patient, a motif, real space (big statements and the room
  ringing), snare and kick talking; develops; and builds to the big one,
  toms, triplets, a polyrhythm or a roll, before the cue.
- **A drummer finishes the thought.** In a drum solo, in time or out,
  each idea ends on a closing stroke (the kick, snare and kick, floor
  tom and kick) and breathes before the next one starts: the end of a
  four-bar phrase leaves a beat or two of air, with only the hat foot or
  a feathered kick keeping time, and out of time there's a beat or more
  between ideas. Ideas never run into each other. And no drum is struck
  faster than hands can really play it: a buzz roll is the fastest, about
  eighteen strokes a second; the same drum twice at once is one stroke.
- **A drum solo has colour.** Crashes and open hats land on top of the
  drummer's own strokes (an open hat with a tom or the snare, a crash
  with the kick or the snare, never a crash with a tom), mostly where a phrase starts or a
  beat lands, more as the solo builds.
- **Rolls at the speed of real hands.** A snare buzz roll is the
  fastest, about twenty strokes a second; an open roll on the toms or a
  cymbal about thirteen; at a fast tempo they drop to sextuplets or
  sixteenths instead of machine-gunning, the hands a touch uneven.
- **The drummer welcomes people in,** like an audience clapping: when
  a soloist starts (the first one too) and when the band arrives in a
  new section, more likely the bigger the arrival (a shout chorus):
  hits after the one, a fill between hits, a push, right away or a bar
  later, and sometimes not at all. Never every time; not on each turn of
  a trade.
- **Ride or hi-hat, the drummer's call.** In swing the drummer keeps
  time on the ride or on the hi-hat, firm enough to carry the band, in
  one of its ways (the ride's pattern on the closed hat, quarters
  leaning on 2 and 4, "tsss-chick" with the hat open on 1 and 3 and shut
  by the foot on 2 and 4, or quarters with the swung skips into 2 and
  4), the kick feathering light quarters under it if they like, choosing per section: the hat more often on the opening
  head, rarely under a solo, never on a shout, which stays on the ride.
  On a shout the drummer may chop wood too, their call per shout: the
  cross-stick on 2 and 4, on 4 alone, or a cross-stick on 2 answered by
  the high tom on 4 and its 'and'; chopping, the left hand stays on the
  rim, so the cross-stick pattern stays exactly the same every bar at
  one weight (the foundation), and anything else the bar would put on
  the snare goes to the kick (a fast run on the high tom). Behind
  somebody else's solo the drummer stays on the ride; riding the hat
  there is a rare choice. `on the hat` (or `closed hi-hat`), `ride` and
  `ride only` settle it.
- **The guitar in a small group** comps in spots like a pianist's left
  hand or plays four to the bar, choosing per section; with four horns
  or more it's a big band and the guitar plays four, Freddie Green.
- **Two or four, the bassist's call.** On a head the bass decides in
  the moment: often in two the first time through, less later, sometimes
  two for the first half and walking into the second. Behind a soloist
  the bass walks; dropping into two at the top of a solo is a rare call
  of the moment, never in a trade. Say it
  and it's settled: `two feel` or `in 2` for two, `walking`, `in 4` or
  `four feel` for four.
- **Bass range.** A four-string bass floors at its low E, and a made-up
  line on electric bass lives up the neck, visiting the low string
  rather than walking on it; write `5-string bass` for the low B.
- **The tune has a shape.** The band settles in at the top, warms
  through the heads, builds with each soloist (dropping back as the
  next one starts), peaks at a shout, and brings the out-head back down
  from it; a last vamp or tag usually goes out strong, sometimes brought
  down. Before a bigger section the whole band leans into it over the
  last two bars instead of jumping at the barline. Each take shades it a
  little differently. A section's own words
  win: `soft`, `quiet`, `bring it down`, or `big`, `loud`, `shout` in
  its name, label or feel.
- **The band builds through the tune.** Comping starts with two-note
  shells and a hit left out now and then, and opens into rootless
  voicings with the extensions as the tune goes on; time-keeping parts
  (Freddie Green quarters, a latin or funk pattern) never drop a beat.
  The drummer marks each new section with a crash and now and then
  fills into the next phrase, more as it builds, never every time.
- **Backgrounds, written or on the spot.** Give a horn notes behind
  the solo and they play as written. Say just `backgrounds` (or
  `horns: backgrounds`) and the page prints slashes under the changes
  while the listen makes them up the way a section does on the spot:
  each chord voiced across the horns on backgrounds, top horn on top,
  held soft as pads. Left unsaid, the section decides how in the
  moment, all together, fresh each take: pads, a riff, or short punches
  on the changes, and sometimes laying out till the soloist's second
  half. Say it and it's settled: `backgrounds pads`, `backgrounds riff`
  (one short figure the whole section shares), `backgrounds punches`,
  and `on cue` after any of them waits for the second half.
- **Trading.** `trade 4s: trumpet, tenor, drums` (or `trading eights`,
  `trade 2s between alto and bone`, just `trade 4s` for everybody:
  anyone in the band, bass and percussion too) turns a solo section into
  turns of that many bars, around and around in the order named. Each
  turn opens by answering what the last player just played; on the
  drummer's turn the whole band lays out, the classic fours with the
  drums, and the drummer solos with everything a drum solo has (opening
  by answering the last player's phrase, its rhythm on the drums and
  its shape up the toms; one idea a phrase, stated then developed, told
  as a story, grooves, the kick leading, three over four), keeping
  time underneath their own way for the turn: the hi-hat foot on two
  and four, on all four, a feathered kick, both, or nothing; a chord player or the bass between their own turns keeps
  comping, a horn waits. The pages print "trade 4s" and the order; each
  trader's part says solo.
- **Vamps.** `section vamp, 2 bars, vamp till cue` (or `open`, `open
  till cue`, `repeat till cue`) prints once between repeat signs with
  the words, and goes round a few times in the listen, about eight bars
  of it, a soloist over it playing something new each time round.
- **Words perform.** `rit.`, `rall.`, `slow down` (`molto` more,
  `poco` less) slow the band from the word to the next `a tempo`,
  tempo mark or the end; `accel.` speeds it up; `fade out` turns the
  whole band down to nothing by the last note. They work on words
  lifted from an engraving too.
- **Endings play, and they breathe.** On the last section, `ending:`
  names the steps in order, the way you'd call them:

      ending: hold, drums fill, last hit on cue
      ending: rit, hold, horns fall
      ending: hold, piano gliss, organ gliss, drums fill, last hit on cue
      ending: trash can, drums tag
      ending: cold
      ending: button, drums tag "floor tom, floor tom, bass drum"
      ending: drums dictate "Bb13(#11), A13(b9), G13(#11), A7(#9,b13)", count in, last hit
      ending: drums dictate, last hit, max roach ending
      ending: hold, count in, unison figure, last hit
      ending: hold, alto cadenza, drums fill, last hit
      ending: unison line, hold, go crazy, last hit
      ending: unison line, drum solo, go crazy, last hit on cue

  With the unison first, the band plays its line together right after
  the tune's last bar, then (with `drum solo`) the drummer alone, out of
  time, telling a story and cueing, then the held last chord, everybody
  going for it with `go crazy` (or just holding it and ringing, the
  band's call when you only say `hold`), then the hit, the drummer's
  way.
  The drummer's cues out of time are big and plain, never the same
  one twice running: three rising hits, a count, snare and kick
  hammering four, the toms walking down, a run up the
  toms, flams, a flam triplet, a choked crash and silence, a swell. Every
  player hears the same cue, at the drummer's own pace, and there's a
  beat to two of air after it so everyone gets ready; a band blowing
  through the cue keeps blowing through the air. Nobody counts the
  stretches out of time: the drum solo, the held chord and the going
  crazy run as long as they feel, never a tidy number of bars, and
  different every take.
  When the band plays a unison line, the drummer reads it with them:
  a big crash or open hat out of the gate, a hi-hat bark with the snare
  or kick on a short note with air after it, the hat foot closing it,
  the snare or kick catching the rest, space where the line breathes.
  A form that ends on its turnaround (the key's V7, the way a blues or
  a standard heads back to the top) resolves the last time through:
  the band holds the tonic, in the tune's own I chord (a blues ends on
  its I7), unless a written note still sounding at the end wouldn't fit
  it, and then the band holds the chord as written.
  An ending is out of time unless the chart puts it in time: the
  drummer's stretches alone, a fill in a fermata, a line over the held
  chord all push and pull in the player's own time; a count-off and the
  figure after it are in time because the chart says so.
  Only what you name happens: a hold with no hit rings and the band lets
  go together; no fill unless you ask. Nothing lands on the grid: the
  hold lasts as long as it feels, a little different in every tune,
  each player lands and lets go a hair apart, and `watch each other`
  (or `watch me`) pulls that in. The steps: `hold`, `roll`, `trash
  can`, `fill` or `<part> fills`, `<part> noodles` (over the last
  chord), `piano gliss` / `organ gliss` (a sweep up the keys into the
  last hit while the band holds; with a drum fill they land it
  together), `<part> falls` (or doits,
  scoops, plops; a group or `everyone` too), `last hit` (`on cue`, or
  `last hit, hold it` to let it ring under a fermata),
  `button`, `cold`, `rit`, `fade`, `drums tag` (the drummer's own
  little thing after the last note, or spelled out in quotes), `drums
  dictate` (the drummer plays alone, the band hits a chord on the
  drummer's call, back and forth, the chords in quotes or the band's
  own bVI, V, IV, V altered of the key), `count in` (the conductor
  counts the band back in on the last hit; with no count, the drummer
  cues the band onto the last chord and everyone goes for it until the
  drummer cues the hit), `unison figure` (after a count-off the whole
  band plays one line together, each in their own octave, and the
  drummer kicks it their own way), `max roach ending` or `drummer's
  last say` (the drummer's own last word after everyone's done, always
  landing on the kick: floor tom and kick, "snare snare kick", open hat
  with snare then the hat foot then kick, down the toms, a quick lick
  or spread out, never the same twice; write your own with `drums tag
  "open hat with snare, hat foot, kick"`, where `with` or `+` puts
  strokes together; and anyone may fall off the final hit in the
  moment, the keys sliding off it while the drummer has the last say), `<part> cadenza` (the band
  cuts off and that player goes alone, free; a `drums fill` named after
  it brings everyone back for the hit), and `as written` for nothing
  added. A player the ending names comes in for
  it. The pages print the steps over the last bar with a fermata when
  the band holds.

  **Say nothing and the band decides**, in the moment, from the feel,
  its own call in every tune: a ballad slows and rings, funk or latin
  usually stops on a hit, swing might hold and let go or hold and hit,
  now and then a trash can, and once in a while the drummer takes the
  whole ending. Holding into a hit, the setup is decided in the moment
  too: a drum fill, a gliss from the piano or organ, both together, or
  nothing but eye contact. Sometimes a drum tag. It never rewrites a
  written ending, the pages stay as you wrote them, and the findings
  say what the band chose so you can write it in if you like it.
  `ending: band's choice` asks for the same thing out loud, after any
  steps you do want (`hold, band's choice`).
- **Slashes on the page, the real part in the listen.** When the chart
  lifts from a score (`source:`) and a rhythm player's line says
  `groove`, the page prints slashes, but the listen plays what that
  score writes for the player in those bars: the bass line, the drum
  part, the voicings. Only a section the score leaves empty is made up
  from the chords. An open solo section with nothing lifted in it is
  placed by the sections on either side. The build's findings say
  which parts played the score and where.
- **The percussion section grooves too, each instrument its own way.**
  Congas, bongos, timbales, cowbell (or bell), claves, shaker, maracas,
  cabasa, tambourine, guiro, agogo, triangle and woodblock each play the
  feel on their own instrument when their line says `groove`: in a latin
  feel the congas play the tumbao, bongos the martillo, the bell the
  mambo pattern, claves the son clave (2-3, bar by bar) and the guiro
  the cha-cha stroke; bossa gets the bossa clave and light congas, samba
  sixteenth shakers and the agogo figure, funk and rock the tambourine
  on the backbeat, and a ballad keeps everyone light. In 6/8 the bells
  and sticks play the 6/8 bell. The listen plays real recordings of
  each (VCSL); timbales use the General MIDI sound, since nothing open
  recorded them. The drum set and cajon keep the kit's grooves.
- **Swing plays.** When your
  `feel:` says swing or shuffle, the listen MP3 actually swings;
  the pages keep the straight-eighth convention with the feel marked
  in words, the way players expect.
- **Articulation words**: `marcato` is short-but-fat on every note (the
  big-band daht). `short` makes the phrase's last note print short.
  `fall` drops off the last note. `scoop first`, `scoop last`, or
  `scoop bar 12 beat 3.5` put the slide where you bent it.
- **Dynamics**: `dyn mp`, `dyn f at bar 9`, `dyn sfz at bar 8 beat 4+`.
  Marks land under the note, including on off-beats and tuplet spots.
- **Say it your way, whatever music raised you.** The same mark has a
  different name in every tradition, and the parser meets them all:
  jazz says `daht` or `housetop`, classical says `marcato`, same
  housetop on the page. `falloff`, `fall off` and `fall` are one word;
  `slide` is a `scoop`; `ten.` is `tenuto`; note values spell out
  (`eighth notes`, `sixteenth note triplets`); dynamics take the long
  words (`dyn sforzando`, `dyn mezzo piano`) or the marks. Every-note
  articulations cover the traditions: `marcato` (short and fat),
  `staccato`, `tenuto` (full value), `accent`. The bends: `scoop` (in
  from below), `plop` (in from above), `doit` (up off the end), `fall`
  (down off the end). `cresc` and `dim`, or `crescendo`, `diminuendo`,
  `decrescendo`, print where you put them. And the rule that keeps
  every tradition welcome: any word the parser does not know still
  reaches the page verbatim through `text "..."`. Gospel's "push it",
  a string section's "sul tasto", anything. No one's language is
  blocked. Funk's `stabs` and gospel's `punchy` are the housetop too,
  and `quarters` pins a ballad figure to the beat.
- **Words on the page**: `text "harmon mute - stem out" at bar 9`,
  `mute cup`, `open`. Say anything; it prints verbatim. One catch: keep
  commas out of quoted text (use a dash). The comma is how instructions
  are separated.

## Bringing in what you have

    python3 prototype/chart.py import "Blue Rondo.mxl"

In the app it's the first card, Bring in a file, or drop the file on
the window. Whatever you're holding:

- **A score** (MusicXML, or the compressed .mxl most programs export)
  becomes a chart in its own folder in Copyist Charts, the score copied
  beside it. The band comes from its parts, the sections from its
  rehearsal marks (or the section words written over a bar, like
  "Intro" or "vamp 1"), the changes from its chord symbols, and the
  key, meter, tempo and credits from the score. Every part's bars are
  lifted exactly, so nothing is retyped. The key is the concert key
  even when the first part is an alto. It compiles the first time:
  every score in the author's own book does.
- **A MuseScore file** goes through MuseScore if it's installed.
- **A MIDI demo** goes to the interview below.
- **Words and chords** in any text format: see below.
- **Anything it can't read** (Sibelius, Finale, Dorico, Guitar Pro, a
  DAW project, audio, a picture) gets one sentence naming the way in,
  usually "export MusicXML" or "export the MIDI".

It never writes over a chart. A second version of a tune gets its
file's name, or a number.

### Words and chords, from any text

Plain text, Markdown, RTF, Word, OpenDocument, HTML, a PDF with real
text in it, and Pages (through the preview it keeps) all read. Copyist
works out what the words are:

- **A ChordPro song** (`[G]Evening comes down [C]slow`, with
  `{start_of_chorus}` and friends): the verses and choruses become
  sections, the chords their changes, the words kept beside them.
- **A chord sheet**, chords over the lyrics or in `| F | Bb |` bars:
  barlines set the bars exactly, `%` repeats a bar, `x2` repeats a
  line, and a title, "by" line, key, tempo and meter at the top come in
  too.
- **ABC notation**: the melody itself, as a written figure, with the
  chords in their places. Grace notes and ornaments ABC decorates with
  are left out, and the findings say so.
- **An iReal Pro link** (from a web page, a message, a document): the
  whole form, bar by bar, repeats and endings written out.
- **Just the words**: stanzas become sections waiting for a tune, a
  stanza that comes back is named Chorus, and the chart asks you to
  tell it the tune. With a chart already open, the app asks whether the
  words belong to it; `chart import words.docx --into "My Tune.chart"`
  does the same from the terminal, placing each stanza beside the
  section with its name, as comments, so no page changes until you
  place them.

When a sheet only says which chords, not how long, each chord gets one
bar and the findings say so, so you can give the real lengths at the
editing desk. Chords come in as written: 9sus4, 7b9b13, m13, maj13,
9#11 and power chords are all part of the chart language now.

## Starting from nothing

    python3 prototype/chart.py "Uptown Local.chart" new --demo horns.mid

The interview reads your demo first, then asks one question at a time:
title, key, meter, tempo, count-in. Key, meter and tempo are offered
from the file itself, and in 6/8 or 12/8 the tempo it offers is the
dotted-quarter figure, the one the page prints. The count-in is
detected when bar one is empty. Then it walks the tracks, each one
announced with its name, note count and range. A track already named
for its instrument ("trumpet", "congas", "Tenor Sax 2") offers that
instrument, so Enter is the whole answer; if the track sits an octave
off that instrument's real register it says so and proposes the
correction. The chart it writes opens with an
activity map, who plays which bars, so carving sections is reading,
not detective work.

**No demo yet? Start anyway.** Press Enter at the demo question (in
the app, New chart, Command Shift N) and Copyist asks the header, then
who's in the band, the way you'd say it: "trumpet, alto, 2 tenors,
bone, piano, bass and drums". Counts, plurals and nicknames all work,
a bare alto or tenor is the sax ("alto voice" for a singer), and the
parts take your own words as their names. Then you describe the tune.
Say "trumpet and saxes play the melody" with no demo to take it from
and Copyist asks for the melody as soon as the form is written: say it
in notes or play it in from a MIDI file. The first player gets the
line and the others double it, each written for their own horn. A
horn or singer named alone in a section ("alto") has the tune too;
slashes on a horn page were never what that meant. When A2 or A3 has
A's changes, Copyist offers A's melody, so an AABA head is said twice,
A and B, not four times. The percussion keeps playing whoever else you
name, the way the rhythm section does, unless you say it lays out.

## Describing the tune: the roadmap conversation

    python3 prototype/chart.py "Uptown Local.chart" edit

You don't have to carve the sections by hand. `edit` (shortcut `e`)
asks for the tune in one breath, the way you'd describe it to the
band:

    8 bar intro, head is 32 AABA, solos over the head twice,
    out on the last A

Say it the way you'd say it: "12 bar blues, head twice, solos, head
out" is one head played twice, solos over it, and out on the head. A
section named again keeps its length, and bare "solos" go over the
head (if the tune has several sections, Copyist asks which, offering
the head). A yes-or-no question takes only a yes or a no, so a
sentence typed into the wrong question is asked again, never taken as
a yes.

It places what it understood, reads the placement back, and asks one
question at a time about only the gaps. An AABA head offers to carve
itself into lettered 8s; a later A offers "same changes as A?"; solos
over a form ride that form's own changes; the out on the last A plays
the last A's changes without you typing them twice. A head out
over a carved head plays the whole head again, A, A, B, A, and Enter
at its who-plays question plays it the way the head went: the same
players, and the head's melody placed bar for bar, nothing asked
twice. If the chart
doesn't exist yet, the `new` interview runs first and the roadmap
picks up where it stops.

Chords go in three ways, and they mix freely:

- **Say them** the way you'd call them on the bandstand: `b flat
  seven 4 bars, e flat seven, c nine f seven at 3`. Or type the
  symbols; both land as a proper chords line, and a line that doesn't
  add up to the section says both counts and asks again.
- **Play them**: `play changes.mid` reads a MIDI file of you playing
  the changes, names what it hears, mid-bar changes included, and
  reads the whole progression back for your yes before anything is
  written.
- **Lift them**: `from demo` names the changes from a comping track of
  the chart's own demo, same read-back, same yes.

The breath can carry the tune itself, not just the sections: "in the
key of E flat, gospel at 72, intro 4, verse 16, chorus 16, verse 16,
chorus 16, tag 8 open" sets the key, the feel and the tempo in the
header, numbers the repeated names (verse, verse 2) so the second
verse can offer the first one's changes, and "waltz" or "in 6/8" sets
the meter. It knows the common forms cold: "blues in F", "minor
blues", "rhythm changes" (or "I Got Rhythm"), which carves itself into
A, A2, B, A3. Any key, sharp keys spelled sharp, always read back for
your yes. "Solos over the form" finds the form without you naming it.

Chords speak in numbers too, the way a rehearsal is actually run:
"two five one in C" is Dm7 G7 Cmaj7, "1, 4, 5, 1" lands in the chart's
own key, "flat seven" arrives as the borrowed dominant, and "four
minor" overrides the diatonic default. Minor keys get minor-key
degrees. And who-plays understands the bandstand: "everybody in",
"bass walks, piano comps", "trumpet lays out", "voice sings the
melody" (a from-demo lift of that section's own bars), "horns hits on
1, 2+, 4".

You can tell it the tune the way you'd tell a story: "it opens quiet
with a 4 bar piano intro, then a blues in G, solos over the form
twice, big shout 16, ends on the head." Openers ("it opens with",
"starts on"), connectors ("then", "after that", "finally") and
endings ("ends on the head") all read; a mood word (quiet, big,
mellow, burning) prints as the section's label, the way a real chart
says "(quiet)" beside the letter; and "bass in at 5" means just that:
the bass rests bars 1 to 4 and comes in at 5, with the "+bass" cue
over the entrance. The page, the listen and the read-aloud all agree.

Run `edit` on a chart that already has its form and you get the
editing desk instead of a fresh interview: `chords of <section>`,
`who plays in <section>`, `notes for <part> in <section>`,
`add shout 16 after B`, `cut <section>` (asked before it cuts),
`rename <section> to <name>`, `repeat <section> 3 times`,
`make <section> open`, `tempo 116`, `feel latin`, `transpose to C`
(the key and every chord symbol move; your played material stays as
played, and it says so), `read it back`, or `replace the form` to
start the roadmap over. Every move lands in the file at once and is
checked by the same compiler as always.

`notes for <part> in <section>` is the fix-it tool: say the line the
way a player says it, "rest half, D5 eighth, E flat eighth, up G
quarter tied to half", and it becomes a real figure at the bar you
name. Durations stick until you change them, octaves follow the line
(say "up" or "down" to force the leap), a line that stops short of
the barline offers to pad itself with rests, and "play lick.mid"
brings the same lick in from a file you played instead. The typed
notes grammar passes straight through if you'd rather write it.

Words it doesn't know, it never guesses. It asks once what to read the
word as, writes the answer to your own vocabulary file, and uses it
forever after. Your slang becomes part of your Copyist. That works
for whole progressions too: teach it that "train changes" means your
favorite line, and from then on it's one word at the chords question.

## The loop that replaces a copyist

    python3 prototype/chart.py "Uptown Local.chart"

That one command checks the chart, builds score and parts, renders the
PDFs, writes a spoken read-aloud for every part, and bounces the listen
MP3: the band playing exactly what the pages say, with your groove
bars realized into real time-keeping from the chord symbols. The
workflow that works:

1. Listen to the MP3. Anywhere it sounds wrong, the page is wrong.
2. Open the read-aloud for that part and find the bar. It speaks your
   DAW's bar numbers, at concert pitch, with every mark named.
3. Change the chart text. Run the command again.

The pages come out engraved like a pro part. Every section closes
with a double bar, the last bar gets the final bar, and in the parts a
stretch of waiting prints as one bar carrying its count: sixteen bars
of rest is one measure with a 16 over it, never sixteen empty bars. A
bar identical to the one before it prints as the one-bar repeat sign,
counted over every fourth, on any part that earns it. The conductor
score keeps every bar visible. A multirest breaks wherever a player
needs to see something (a rehearsal letter, a dynamic, a text) and may
close at a double bar.

Every build ends with a range report, each part's written peak and
low with their bars. The philosophy: floors are hardware, ceilings are
chops. A note below the horn folds up an octave; a high note is NEVER
destroyed, because a lead trumpet runs to written double C and beyond.
Instead the report flags it: "lead territory; know whose chops are on
the chair." Trombone lows below the staff get named as pedal territory.
The ranges come from the arranging literature, not guesses.
And when only your ears matter: `listen` skips the pages, `--from-bar
78` cuts an MP3 starting right where you want to proof, and `--solo
"bari,trombone"` isolates just those parts.

The build also prints findings: every place it moved a note into range,
unified a repeated phrase's cutoff, or noticed your timing sitting loose
on a grid. A finding is a question for your ear, not an apology.

## Braille

Every part a player reads — horns, strings, voice, bass, guitar, and
piano or organ on two staves — comes out as a braille music file, a
`.brf`, beside its PDF:

    python3 prototype/chart.py "Uptown Local.chart" braille

`braille` makes only that; a full build makes it too while `exports`
includes braille. The files follow BANA's *Music Braille Code 2015*
in the single-line layout a player reads from: the title and part,
the tempo, key and time heading, the music in numbered segments with
rehearsal letters on their own lines, chord symbols on a second line
under the notes they fall on, and pages of 40 cells by 25 lines, the
size a braille embosser or notetaker expects. Octave marks, accidentals,
ties, slurs, triplets and other groups, chords written as intervals,
two voices in a bar as an in-accord, repeats and endings, D.S. and the
coda, dynamics and every word on the page are all brailled by the
code's own rules.

Piano and organ come out in bar-over-bar parallels, the keyboard
layout: each parallel opens with its bar number, then the right hand's
line over the left hand's, every bar's music starting in the same
column in both, the chord symbols as a third line beneath. The hand
signs say which way intervals read (down in the right hand, up in the
left), every bar's first note in each hand carries its octave mark,
and the pedal marks ride in the left hand.

A part with lyrics comes out line by line, the way a singer reads:
a line of words at the margin, and under it, from the third cell, the
music those words are sung to. The words are whole words in
uncontracted braille, a word carried to the next line ends with a
hyphen, and notes sung to one syllable are joined by syllabic slurs.
Lines break where a phrase of words ends when there is a choice, so a
phrase stays together to memorize. When the part carries chord
symbols, they take a line of their own between the words and the
music, each chord placed by when it sounds: under its syllable when
played with it, two cells left when before it, after a hyphen when
during it, one cell past it when after it; a transcriber's note at
the top explains this.

Print slashes have no sign in braille music. Copyist writes the word
*slashes*, then a rest for each slash, with the changes underneath,
and a transcriber's note at the top of the part says so. When a part
has chords, the same note says which way its intervals read.

Before a build keeps any braille, a separate reader, written apart
from the braille writer on purpose, reads every file back by the
code's rules and compares it with the score note by note: pitch,
octave, accidental, value and dot. The build says so when every part
agrees and names the note when one does not. For a sung part it also
translates the words back to print and checks them against the lyrics,
and checks that every note is paired with the right syllable.
An organ's third staff (the pedal line) and verses after the first
are not brailled yet; the build names each one.

Percussion comes out too. A hand drum, a bell or a set of like drums
reads single-line, its notes named by where they sit on the staff as
if in bass clef, with a transcriber's note saying which note is which
drum. A drum kit, or a part mixing several instruments, is written as
a small ensemble score: a table of the instruments with their
abbreviations and notes, then one line per instrument, each opening
with its abbreviation, only the instruments that play in those bars
shown, the bars aligned, and a transcriber's rest (after dot 5) where
one instrument waits while the others play. Where a note head means
something (the open hi-hat, the ride's bell, a side stick, a muted
conga), a sign before the note carries it and the note at the top
explains it. Time slashes on a drum part say to keep time.

The braille page is standard braille paper, 11 by 11.5 inches, 40
cells by 25 lines, unless you say otherwise: `chart set
braille_page=letter` (34 by 25), `a4` (35 by 28), or any cells x lines
like `32x25`; `--paper` changes it for one build. Everything reflows to
fit and is proofread the same way.

To emboss, add the embosser in System Settings, Printers and Scanners,
then tell Copyist which printer it is:

    chart embossers                      # the printers this Mac knows
    chart set embosser=Index_Everest
    chart tune.chart emboss              # every part's braille
    chart tune.chart emboss --parts "trumpet 1"

`emboss` makes the braille, proofreads it, and sends each file to the
embosser as raw braille, the form BRF embossers take; anything the
proofreader disagrees with is held back rather than wasting paper.
Single or double-sided is the embosser's own setting. In the Mac app,
**Emboss** on the Build tab asks before it sends, and Settings has the
paper and the embosser under **Braille**. On Windows, open the .brf
files in the embosser's own software.

**Braille pages** draws the braille as dots, one PDF page for every
braille page, raised dots solid and the empty places in each cell
faint, with each cell's braille ASCII beneath it. It is for sighted
eyes: a teacher, a bandmate, a proofreader who wants to see what the
reader's fingers meet.

## Writing with other people

A chart is one small text file, so collaboration is whatever you already
use for text: a shared folder, email, or a git repository. Two writers
can work on different sections and merge; the history of a chart is the
history of decisions, in plain words anyone's screen reader can read.
The demo MIDI travels beside the chart, and anyone with the repo gets
byte-identical results from the same source. The chart is the truth,
the PDFs are just today's printout. And nothing else needs installing:
Copyist draws its own pages and plays them itself, with real swing,
honest dynamics, and each part seated in its own spot in the stereo
field.

## The build has your back

Every build's findings open with each part's fate, section by section,
"trumpet — Head: your line; Solos: your line; Head out: doubles the
tenor", so an accidental twelve-bar rest in the lead alto is read back
in text before it is ever printed, and a part that never plays a single
bar gets called out loudly in case that wasn't the plan. If your saved
read-alouds are older than the chart, check says so instead of letting
you proofread yesterday. And `--count-in` puts a bar of click in front
of the listen MP3, high tick on one, so you can play along like it's
a session; add a number for more bars. The from-bar trim still lands on
the music, past the click.

A DAW never runs out of air; a player does. The findings name any
written horn or vocal line that runs longer than a comfortable breath at
your tempo (about twelve seconds) with no rest of an eighth or more,
with its bars, so you can mark a breath or open a gap.

## House rules the tools live by

- Ears first: every output exists in a spoken or listenable form.
- Your word beats statistics; your playing beats guesswork.
- The demo is ideas, not gospel. Bends, vibrato and micro-timing stay
  with the players. What survives is the line.
- Nothing fails silently. If it compiled, it says what it wrote; if it
  refused, it says why in one sentence.
