# Copyist on Windows

Double-click **Copyist.bat**. It opens the same Copyist that runs on
the Mac, with native Windows dialogs that NVDA and JAWS read well:
build a chart, check it, open a part's read-aloud in Notepad, the
settings desk, and "Tell me the tune", the roadmap conversation.
That last one opens a real console window, because the conversation
is interactive and screen readers already read consoles natively.
Describe the tune in one breath and Copyist writes the sections.

You need **Python 3** from [python.org](https://www.python.org)
(tick "Add python.exe to PATH" in the installer). Optional extras:
**ffmpeg** (`winget install ffmpeg`) turns the listen file into an
MP3 — without it you still get a WAV — and **MuseScore 4** covers the
one thing Copyist does not draw itself yet (grace notes inside lifted
engravings).

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
