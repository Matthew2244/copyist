# Copyist

**Turns what you played in a DAW into parts a band can read.**

You write in a DAW. You play the parts in by hand, because that's how the music
actually happens. Then you export MIDI, open it in notation software, and the
page is unreadable. Sixty-fourth rests everywhere, tied rhythms nobody could
count, accidentals fighting the key, both hands crushed onto one staff with the
clef flipping mid-bar to cope.

Copyist replaces that second step.

It's built accessibility first, by and for a blind composer, on a premise that
turns out to make the tool better for everybody: **you can't proofread a page
you can't see.** So Copyist tells you in words what's on the page, lets you
check it by ear, and verifies its own output instead of asking you to look.

> **Status: working prototype.** It builds real charts end to end, with no
> other software installed. Matthew uses it for actual work. Nobody else has
> tried it yet, so you would be the first, and hearing what breaks for you would
> genuinely help. Parts of the design are still unbuilt, and those gaps are
> listed in the docs rather than glossed over.

## It draws its own pages now

Copyist used to hand MusicXML to MuseScore and let MuseScore draw the page and
play it back. As of September 2026 both of those live inside Copyist, and it
needs no other software installed.

**The engraver** (`prototype/chartengrave.py`, pure standard library) draws every
part and the conductor score straight to PDF. Staves, clefs, keys, meters, beams,
ties, slurs, tuplets, articulations, ghost notes, slashes, rhythmic kicks, cues,
lyrics with melisma lines, chord symbols, dynamics, rehearsal boxes, repeats,
endings, and multirests that break wherever a player has to look up. A tie across
a barline is one true arc, and one broken at a system turn draws its outgoing
half to the edge and an incoming half to the landing note.

Pages are set in a real music font. Leland, MuseScore's OFL licensed SMuFL face,
is embedded in every PDF Copyist draws. Jazz charts get MuseJazz Text,
handwritten charts get Petaluma Script, everything else gets Edwin.

**The playback is Copyist's own too**, which means silence is genuinely silent.
The old renderer had an audible noise floor under empty bars.

One thing it still declines: grace notes in a lifted engraving. It refuses in a
sentence rather than guessing at them.

## What makes it different

**The output is a chart, not a transcription.** Every other tool in this space
maximizes fidelity. That's the wrong goal when the reader is a player who's going
to interpret the part anyway. Copyist throws detail away on purpose. Slashes,
chord symbols, "groove as demo". For that reader, less is usually more useful.

**Gate time means articulation, never rests.** Letting go of a key 70ms early
isn't a sixty-fourth rest. It's a staccato dot. That one rule removes most of the
visual noise from a hand-played part.

**Hands are separated by physics, not by a split point.** Hand span, movement
cost, continuity. Crossings come out right, because crossing is cheap when the
hands are already close. A fixed split at middle C gets that wrong every time.

**It emits MusicXML rather than MIDI.** MIDI can't express voices, spelling,
staff assignment, dynamics, articulation or pedal, so a MIDI workflow asks the
notation program to invent all of it, and it invents badly.

**It tells you what it did and what it's unsure about.** Findings come severity
first, each one carrying the settings change that would fix it, each one
suppressible so the second run is quieter than the first.

**It verifies itself.** Output is rendered back to MIDI and diffed against the
performance you played. That caught a bug in development that lost 33 notes while
the page still looked perfect.

## The front door

```bash
python3 prototype/chart.py yourtune.chart
```

There is also **Copyist.app** — a real Mac app over the same engine, built
from `app/` with `app/build.sh --install`. Two designed looks (Dark Stage
and Manuscript, or match the system — the user decides), the same big
actions as the CLI, a settings desk where every control states its value,
and the roadmap conversation held in a chat view: the app and the terminal
share one conversation engine over a JSON line protocol
(`COPYIST_PORCELAIN=1`), so they can never drift apart. The engine and
fonts are bundled inside the app, so it runs with nothing else installed;
a checkout at `~/copyist` wins at runtime so development stays live.

One command builds everything: the parts, the conductor score, a listening MP3,
a read-aloud of every part, a findings file, and a written range report for each
player. It also says what changed since your last build, by part and by bar, out
loud. If nothing changed it says that too.

```bash
python3 prototype/chart.py yourtune.chart new --demo demo.mid
```

`new` interviews a starter chart into existence. It reads your demo first, offers
the tempo and count-in it found, announces each track with its name, note count
and range, and proposes octave corrections from register evidence.

```bash
python3 prototype/chart.py yourtune.chart edit
```

`edit` is the roadmap conversation: describe the tune in one breath — "8 bar
intro, head is 32 AABA, solos over the head twice, out on the last A" — and it
writes the sections, asking one question at a time about only the gaps. Chords
arrive spoken the way you'd call them ("b flat seven 4 bars"), played (a MIDI
file of the changes, named and read back for your yes), or lifted from the
demo's comping. A word it doesn't know is asked about once, remembered in your
own vocabulary file, and never guessed.

```bash
python3 prototype/chart.py yourtune.chart listen --from-bar 65 --solo "bari,trombone"
```

Proof the ending without sitting through the whole tune, with only the two parts
you're arguing about. Bar numbers are your DAW's, not the page's, because that's
the number you have in your head.

`check` compiles without building. `read` speaks the chart. `parts` lists the
band. `diff` re-speaks what changed. Every one has a one letter shortcut.

`chart settings` is the defaults desk: your composer name for new charts, a
default look, a phone ping when a build lands, whether the score pops open.
Every setting states what it is currently set to before you change it, because
a screen reader user should never have to change something to learn what it was.

## The apps

The same brain answers to dialogs. On the Mac, compile `CopyistApp.applescript`
into an app (the file's header has the one-line command): a menu of dialogs —
build, check, open a part's read-aloud in TextEdit, the settings desk — every
one of them shaped for a screen reader, with Escape working everywhere it can.
On Windows, the `windows` folder holds `Copyist.bat`, the same menu in native
Windows dialogs (written on a Mac, honestly untested on real Windows — the
README in that folder says so too).

The MIDI analysis underneath is still there and still standalone:

```bash
python3 prototype/analyze.py yourfile.mid
python3 prototype/convert.py yourfile.mid -o out.musicxml --key "C# minor"
```

Nothing is required beyond stock Python 3. The MIDI parser, the engraver and
the audio are all standard library. ffmpeg is optional and only turns the
listening WAV into an MP3. Without it you get the WAV, and Copyist tells you
why and how to fix it.

## The band

112 instruments, with the doubles. Woodwinds from piccolo through bari including
english horn, alto flute and Eb clarinet. Brass including cornet, flugel,
euphonium and both trombones. Strings, the keyboard family, all the mallets,
timpani, six voice parts, drum set, and the entire percussion wing from three
different cowbells to a vibraslap.

It speaks the gig's own slang. Kit, vibes, keys, rhodes, bone, bari, fiddle,
upright bass, campana, darbuka. "Bells" means glockenspiel, because that's what
it means in a band room.

Two rules run through every pitched instrument. **Floors are hardware**: below
the horn's bottom note, Copyist folds the line up and tells you it did.
**Ceilings are chops**: a high note gets flagged "lead territory, know whose
chops are on the chair" and is never touched.

## Verified results

On the included fixture, ten bars of two-hand piano, 110 notes:

| | Result |
|---|---|
| Round-trip note accuracy | **100%** onset and pitch |
| Phantom rests removed | 42 |
| Clef changes | **0** (a plain MIDI import of comparable material produces six or more, mid-bar) |
| Humanized input vs click-locked input | **byte identical output**, though humanize shatters every chord into separate events |

The fixture is synthetic so the corpus carries no private music, but it was built
to reproduce pathologies measured on real DAW exports. That includes the finding
that REAPER's humanize moves notes independently and therefore breaks chords
apart, which is reversible once you know to look for it (DESIGN.md §7.5.1).

## Documentation

- **[DESIGN.md](DESIGN.md)**: the full design, the locked decisions and the open
  questions. Read this before proposing anything.
- **[CHART-FORMAT.md](CHART-FORMAT.md)**: the chart language, and an honest
  status of what's built.
- **[CHART-WRITING.md](CHART-WRITING.md)**: the writer's guide, in musician
  language, on an invented tune.
- **[CONTRIBUTING.md](CONTRIBUTING.md)**: the rules. Accessibility first.
- **[corpus/](corpus/)**: test fixtures. Every bug becomes one of these.

Try it on something you played. If the page comes out wrong, that is worth
knowing about, and a bad page is a better bug report than a description of one.
Open an issue with the MIDI if you can share it, or with the findings file if
you cannot.

## License

MIT for the engine. Instrument data derived from MuseScore is GPL-3 and lives in
a separate optional package, so the core stays reusable by anybody, commercial
notation tools included. See DESIGN.md §17.
