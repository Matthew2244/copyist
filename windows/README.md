# Copyist on Windows

Double-click **Copyist.bat**. It opens the same Copyist that runs on
the Mac, with native Windows dialogs that NVDA and JAWS read well:
build a chart, check it, open a part's read-aloud in Notepad, and the
settings desk.

You need **Python 3** from [python.org](https://www.python.org)
(tick "Add python.exe to PATH" in the installer). Optional extras:
**ffmpeg** (`winget install ffmpeg`) turns the listen file into an
MP3 — without it you still get a WAV — and **MuseScore 4** covers the
one thing Copyist does not draw itself yet (grace notes inside lifted
engravings).

The terminal works too, exactly like the Mac:

    python prototype\chart.py "My Tune.chart"
    python prototype\chart.py settings

**Honesty note:** this front end was written on a Mac and has not yet
been run on a real Windows machine. The core compiler and engraver
are plain-Python and platform-neutral by design. If anything
misbehaves, that is a bug worth reporting.
