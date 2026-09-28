# Copyist on Windows

Double-click **Copyist.bat**. It opens the same Copyist that runs on
the Mac, in a window with five tabs, the Mac app's five: **Chart**,
**Build**, **Listen and read**, **Conversation** and **Settings**.
**Ctrl+1** to **Ctrl+5** jump straight to a tab and put focus on the
tab strip, so NVDA and JAWS say the tab and its place ("Build tab, 2
of 5"); **Ctrl+Tab** steps through them as in any Windows tab control.
The work has keys too: **Ctrl+B** builds, **Ctrl+Shift+B** makes just
the braille, **Ctrl+K** checks, **Ctrl+D**
says what changed, **Ctrl+L** listens, **Ctrl+R** reads a part aloud,
**Ctrl+O** opens a chart, **F5** asks how a build is going and **F1**
lists the keys. Every button says its key after its name. The line at
the top says which chart you are working on, so nothing asks again.
The controls are plain WinForms, the ones NVDA and JAWS read best.
"Tell me the tune", the roadmap conversation, opens a real console.
That last one opens a real console window, because the conversation
is interactive and screen readers already read consoles natively.
Describe the tune in one breath and Copyist writes the sections.

**Teach Copyist** names what your libraries play, in the same kind of
console. If a demo used keyswitches Copyist has no name for, or a
drum kit whose notes aren't General MIDI, it asks about each one
("note 39, played 20 times, first in bar 5 — what is it on your
kit?") and saves the answers, so every chart from that patch or kit
reads right from then on. When a finished build needs this, "How is
the build going" offers it for you. **Bring in a file** takes a
score, a MIDI demo, or words and chords in almost any format, then
offers the next step: the roadmap conversation for words with no
form yet, or a build. Every console waits for a key before it
closes, so the last thing said is still there to read.

You need **Python 3** from [python.org](https://www.python.org)
(tick "Add python.exe to PATH" in the installer). Optional extras:
**ffmpeg** (`winget install ffmpeg`) turns the listen file into an
MP3 — without it you still get a WAV. MuseScore is not needed for
anything; Copyist draws every page itself.

The terminal works too, exactly like the Mac:

    python prototype\chart.py "My Tune.chart"
    python prototype\chart.py settings

Everything the engine learned lately is here too, because both doors
run the same engine: the roadmap conversation, played demos lifted
into real parts, and drum charts that come out like drum books — two
voices, x heads on the cymbals, repeat signs through the groove.
Builds run in the background, so the menu comes straight back while
the band renders; "How is the build going" answers whenever you ask,
on a button press, never a timer that talks over your screen reader.
And settings can send finished files wherever you like — a folder
each for pages, listens and read-alouds.

**Honesty note:** this front end was written on a Mac and has not yet
been run on a real Windows machine. It parses clean under PowerShell
7, and the core compiler and engraver are plain Python, written
platform-neutral. If anything misbehaves on real Windows, that is a
bug worth reporting.
