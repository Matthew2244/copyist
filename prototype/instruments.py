#!/usr/bin/env python3
"""
Instrument identity — DESIGN.md 10.

Resolution chain: track name -> plugin alias -> GM program -> range fallback.

The GM program half was missing entirely until real files arrived. Every one
of the 25 Windows demo files has empty track names and a correct GM program on
every channel, so name-only resolution identified nothing at all in material
that was fully labelled the whole time.

`instrument-sound` values are MusicXML Standard Sounds, so Dorico, Sibelius
and Finale recognize the part too, not just MuseScore (§10.1).

Ranges here are sounding pitch. `transpose` is the chromatic interval from
sounding to WRITTEN, so a B-flat trumpet is +2: concert C is written D.
"""

# name, MusicXML sound, abbreviation, staves, transpose(semitones to written)
_P = lambda n, s, a, st=1, tr=0: (n, s, a, st, tr)

GM = {}


def _fill(lo, hi, spec):
    for p in range(lo, hi + 1):
        GM[p] = spec


# --- Piano and chromatic percussion
GM[0] = _P("Piano", "keyboard.piano", "Pno.", 2)
GM[1] = _P("Bright Piano", "keyboard.piano.grand", "Pno.", 2)
GM[2] = _P("Electric Grand", "keyboard.piano.electric", "E.Pno.", 2)
GM[3] = _P("Honky-tonk Piano", "keyboard.piano.honky-tonk", "Pno.", 2)
GM[4] = _P("Electric Piano", "keyboard.piano.electric", "E.Pno.", 2)
GM[5] = _P("Electric Piano", "keyboard.piano.electric", "E.Pno.", 2)
GM[6] = _P("Harpsichord", "keyboard.harpsichord", "Hpschd.", 2)
GM[7] = _P("Clavinet", "keyboard.clavichord", "Clav.", 2)
GM[8] = _P("Celesta", "keyboard.celesta", "Cel.", 2)
GM[9] = _P("Glockenspiel", "pitched-percussion.glockenspiel", "Glock.")
GM[10] = _P("Music Box", "pitched-percussion.music-box", "Mus.Box")
GM[11] = _P("Vibraphone", "pitched-percussion.vibraphone", "Vib.")
GM[12] = _P("Marimba", "pitched-percussion.marimba", "Mrm.")
GM[13] = _P("Xylophone", "pitched-percussion.xylophone", "Xyl.")
GM[14] = _P("Tubular Bells", "pitched-percussion.tubular-bells", "Tub.B.")
GM[15] = _P("Dulcimer", "pitched-percussion.dulcimer", "Dulc.")

# --- Organ
_fill(16, 20, _P("Organ", "keyboard.organ", "Org.", 2))
GM[21] = _P("Accordion", "keyboard.accordion", "Acc.", 2)
GM[22] = _P("Harmonica", "wind.reed.harmonica", "Hca.")
GM[23] = _P("Bandoneon", "keyboard.accordion.bandoneon", "Band.", 2)

# --- Guitar
GM[24] = _P("Nylon Guitar", "pluck.guitar.nylon-string", "Gtr.")
GM[25] = _P("Steel Guitar", "pluck.guitar.steel-string", "Gtr.")
GM[26] = _P("Jazz Guitar", "pluck.guitar.electric", "E.Gtr.")
GM[27] = _P("Clean Guitar", "pluck.guitar.electric", "E.Gtr.")
GM[28] = _P("Muted Guitar", "pluck.guitar.electric", "E.Gtr.")
_fill(29, 31, _P("Distortion Guitar", "pluck.guitar.electric", "E.Gtr."))

# --- Bass. Written an octave above sounding, universally.
GM[32] = _P("Acoustic Bass", "pluck.bass.acoustic", "A.Bs.", 1, 12)
GM[33] = _P("Electric Bass", "pluck.bass.electric", "E.Bs.", 1, 12)
GM[34] = _P("Electric Bass", "pluck.bass.electric", "E.Bs.", 1, 12)
GM[35] = _P("Fretless Bass", "pluck.bass.fretless", "Fr.Bs.", 1, 12)
_fill(36, 39, _P("Electric Bass", "pluck.bass.electric", "E.Bs.", 1, 12))

# --- Strings
GM[40] = _P("Violin", "strings.violin", "Vln.")
GM[41] = _P("Viola", "strings.viola", "Vla.")
GM[42] = _P("Violoncello", "strings.cello", "Vc.")
GM[43] = _P("Contrabass", "strings.contrabass", "Cb.", 1, 12)
_fill(44, 45, _P("Strings", "strings.group", "Str."))
GM[46] = _P("Harp", "pluck.harp", "Hp.", 2)
GM[47] = _P("Timpani", "drum.timpani", "Timp.")
_fill(48, 51, _P("Strings", "strings.group", "Str."))
_fill(52, 54, _P("Voice", "voice.aa", "Vox"))
GM[55] = _P("Orchestra Hit", "effect., ", "Hit")

# --- Brass
GM[56] = _P("Trumpet", "brass.trumpet.bflat", "Tpt.", 1, 2)
GM[57] = _P("Trombone", "brass.trombone", "Tbn.")
GM[58] = _P("Tuba", "brass.tuba", "Tba.")
GM[59] = _P("Muted Trumpet", "brass.trumpet.bflat", "Tpt.", 1, 2)
GM[60] = _P("Horn in F", "brass.french-horn", "Hn.", 1, 7)
_fill(61, 63, _P("Brass Section", "brass.group", "Brs."))

# --- Reeds
GM[64] = _P("Soprano Saxophone", "wind.reed.saxophone.soprano", "S.Sax.", 1, 2)
GM[65] = _P("Alto Saxophone", "wind.reed.saxophone.alto", "A.Sax.", 1, 9)
GM[66] = _P("Tenor Saxophone", "wind.reed.saxophone.tenor", "T.Sax.", 1, 14)
GM[67] = _P("Baritone Saxophone", "wind.reed.saxophone.baritone", "B.Sax.", 1, 21)
GM[68] = _P("Oboe", "wind.reed.oboe", "Ob.")
GM[69] = _P("English Horn", "wind.reed.english-horn", "E.Hn.", 1, 7)
GM[70] = _P("Bassoon", "wind.reed.bassoon", "Bsn.")
GM[71] = _P("Clarinet", "wind.reed.clarinet.bflat", "Cl.", 1, 2)

# --- Pipes
GM[72] = _P("Piccolo", "wind.flutes.flute.piccolo", "Picc.", 1, -12)
GM[73] = _P("Flute", "wind.flutes.flute", "Fl.")
GM[74] = _P("Recorder", "wind.flutes.recorder", "Rec.")
GM[75] = _P("Pan Flute", "wind.flutes.panpipes", "Pan Fl.")
_fill(76, 79, _P("Flute", "wind.flutes.flute", "Fl."))

# --- Synth lead, pad, effects
_fill(80, 87, _P("Synth Lead", "synth.group.synth", "Ld."))
_fill(88, 95, _P("Synth Pad", "synth.pad", "Pad", 2))
_fill(96, 103, _P("Synth Effects", "synth.effects", "FX"))

# --- Ethnic, percussive, sound effects
_fill(104, 111, _P("Plucked", "pluck.group", "Plk."))
_fill(112, 119, _P("Percussion", "drum.group", "Perc."))
_fill(120, 127, _P("Sound Effects", "effect.", "FX"))

DRUM_KIT = _P("Drum Kit", "drum.group.set", "Drs.")

TWO_STAFF_SOUNDS = ("keyboard.piano", "keyboard.organ", "keyboard.harpsichord",
                    "pluck.harp", "keyboard.accordion")


def resolve(program, is_drums, note_pitches, track_name="", aliases=None):
    """
    Returns a dict describing the part. Never returns None — an unidentifiable
    track still gets a usable staff rather than being dropped.
    """
    if is_drums:
        name, sound, abbr, staves, tr = DRUM_KIT
        return dict(name=name, sound=sound, abbrev=abbr, staves=1,
                    transpose=0, drums=True, clef="percussion",
                    source="channel 10")

    source = "GM program"
    spec = GM.get(program)
    if aliases and track_name:
        for alias, hit in aliases.items():
            if alias in track_name.lower() and hit[0]:
                spec = _P(hit[0], hit[1], hit[2])
                source = f"plugin name {alias!r}"
                break
    if spec is None:
        spec = _P("Instrument", "keyboard.piano", "Inst.")
        source = "unidentified"

    name, sound, abbr, staves, tr = spec

    # Clef from the actual range. An instrument's default clef is a starting
    # point; what the part really sits in beats it.
    if note_pitches:
        srt = sorted(note_pitches)
        median = srt[len(srt) // 2]
        lo, hi = srt[0], srt[-1]
    else:
        median, lo, hi = 60, 60, 60

    if staves >= 2 and (hi - lo) < 20:
        staves = 1              # a "piano" part with a 12th of range is a line

    if staves >= 2:
        clef = "grand"
    elif median < 55 or hi < 60:
        clef = "bass"
    elif median > 81:
        clef = "treble8va"
    else:
        clef = "treble"

    return dict(name=name, sound=sound, abbrev=abbr, staves=staves,
                transpose=tr, drums=False, clef=clef, source=source)


# General MIDI drum map -> (staff position as a display pitch, notehead).
# Positions follow standard percussion-staff convention: feet low, hands high,
# cymbals as crosses.
DRUM_MAP = {
    35: ("F", 4, "normal"), 36: ("F", 4, "normal"),      # kick
    37: ("C", 5, "x"),                                    # side stick
    38: ("C", 5, "normal"), 40: ("C", 5, "normal"),       # snare
    39: ("C", 5, "x"),                                    # hand clap
    41: ("A", 4, "normal"), 43: ("A", 4, "normal"),       # low toms
    45: ("D", 5, "normal"), 47: ("D", 5, "normal"),       # mid toms
    48: ("E", 5, "normal"), 50: ("E", 5, "normal"),       # high toms
    42: ("G", 5, "x"), 44: ("D", 4, "x"), 46: ("G", 5, "circle-x"),  # hats
    49: ("A", 5, "x"), 57: ("A", 5, "x"),                 # crash
    51: ("F", 5, "x"), 59: ("F", 5, "x"),                 # ride
    52: ("B", 5, "x"), 53: ("F", 5, "diamond"),           # china, bell
    54: ("E", 5, "x"), 56: ("B", 5, "triangle"),          # tambourine, cowbell
    55: ("A", 5, "x"),                                    # splash
    # hand percussion — a percussion part's own staff, higher = higher
    60: ("E", 5, "normal"), 61: ("C", 5, "normal"),       # bongos
    62: ("A", 4, "x"), 63: ("A", 4, "normal"),            # conga slap/open
    64: ("F", 4, "normal"),                               # low conga
    65: ("D", 5, "normal"), 66: ("B", 4, "normal"),       # timbales
    67: ("A", 5, "triangle"), 68: ("F", 5, "triangle"),   # agogo
    69: ("G", 5, "x"), 70: ("G", 5, "x"), 82: ("G", 5, "x"),  # shakers
    75: ("D", 5, "x"),                                    # claves
    76: ("E", 5, "x"), 77: ("C", 5, "x"),                 # woodblocks
    80: ("B", 5, "x"), 81: ("B", 5, "triangle"),          # triangle
}


def drum_position(pitch):
    return DRUM_MAP.get(pitch, ("B", 4, "x"))


# The same map's spoken half — what the read-aloud calls each hit.
DRUM_NAMES = {
    35: "kick", 36: "kick", 37: "side stick", 38: "snare", 40: "snare",
    39: "clap", 41: "floor tom", 43: "floor tom", 45: "mid tom",
    47: "mid tom", 48: "high tom", 50: "high tom", 42: "closed hat",
    44: "pedal hat", 46: "open hat", 49: "crash", 57: "crash",
    51: "ride", 59: "ride", 52: "china", 53: "ride bell",
    54: "tambourine", 55: "splash", 56: "cowbell",
    60: "high bongo", 61: "low bongo", 62: "conga slap",
    63: "open conga", 64: "low conga", 65: "high timbale",
    66: "low timbale", 67: "high agogo", 68: "low agogo",
    69: "cabasa", 70: "maracas", 82: "shaker", 75: "claves",
    76: "high woodblock", 77: "low woodblock",
    80: "muted triangle", 81: "open triangle",
}


# Drum maps other than General MIDI: note -> the GM note of the same kit
# piece, so the page's positions, heads and names and the listen's
# sounds all apply. Toontrack's layout (EZdrummer / Superior Drummer),
# read from the key chart that ships with his EZX Latin Cuban Drums
# (EZX-Keys.pdf, "EZdrummer line"); a piece's articulations fold to the
# piece: open-edge hats are an open hat, a rimshot is the snare.
DRUM_MAPS = {
    'toontrack': {
        # hi-hat: open tips and edges, the variable-CC hat, pedals
        12: 46, 13: 46, 14: 46, 15: 46, 16: 46, 20: 42, 21: 44, 22: 42,
        23: 44, 24: 46, 25: 46, 26: 46, 60: 46, 61: 42, 62: 42, 63: 42,
        42: 42, 44: 44, 46: 46, 119: 42, 120: 42, 121: 42,
        # kick
        34: 36, 35: 36, 36: 36,
        # snare: center, edge, rimshot, closed roll, sidestick, rim
        33: 38, 38: 38, 39: 38, 40: 38, 37: 37, 70: 37, 71: 37,
        # toms: floor, rack 2, rack 1 (centers, rims, shells, aliases)
        41: 43, 43: 43, 72: 43, 73: 43, 74: 43, 75: 43, 76: 43,
        45: 47, 47: 47, 77: 47, 78: 47, 79: 47, 80: 47,
        48: 48, 81: 48, 82: 48,
        # cymbals: crash 1, crash 2, stack, rides 1 and 2
        27: 49, 28: 49, 49: 49, 50: 49, 31: 57, 32: 57, 57: 57, 58: 57,
        52: 52, 54: 52, 55: 52, 29: 59, 30: 53, 51: 51, 53: 53, 59: 59,
        85: 53, 86: 51, 87: 51, 88: 53,
        # the rest of the Latin kit
        56: 56, 122: 56, 123: 56, 124: 56, 125: 56, 126: 56, 127: 56,
        66: 65, 68: 65, 69: 65, 67: 76,
    },
}
DRUM_MAP_NAMES = {'toontrack': 'toontrack', 'ezdrummer': 'toontrack',
                  'superior drummer': 'toontrack', 'ezd': 'toontrack',
                  'sd3': 'toontrack'}
def gm_for_words(text):
    '''"snare roll", "cross stick", "ride bell", "floor tom 2", "stack"
    -> the General MIDI drum note of that kit piece, or None. How a
    drummer names a piece, read into the piece the page can draw.'''
    import re
    t = ' ' + re.sub(r'[^a-z0-9 ]', ' ', text.lower()) + ' '

    def has(*ws):
        return any(f' {w} ' in t for w in ws)
    if has('kick', 'bass drum', 'bd'):
        return 36
    if has('side stick', 'sidestick', 'cross stick', 'rim click',
           'rimclick'):
        return 37
    if has('snare', 'sn'):
        return 38
    if has('hat', 'hh', 'hihat', 'hi hat'):
        if has('pedal', 'foot', 'chick', 'splash'):
            return 44
        if has('open', 'half', 'loose'):
            return 46
        return 42
    if has('ride'):
        return 53 if has('bell') else 59 if has('2', 'edge') else 51
    if has('china', 'stack', 'trash'):
        return 52
    if has('splash'):
        return 55
    if has('crash'):
        return 57 if has('2', 'right') else 49
    if has('floor'):
        return 41 if has('2', 'low') else 43
    if has('tom'):
        return 48 if has('1', 'high', 'hi', 'rack') else \
            45 if has('3', 'low') else 47
    if has('cowbell', 'bell'):
        return 56
    if has('tambourine', 'tamb'):
        return 54
    if has('clap'):
        return 39
    return None


# notes a General-MIDI kit never uses, so a take full of them was
# probably played on another map
NOT_GM_DRUMS = set(range(0, 35)) | set(range(82, 128))


def drum_name(pitch):
    return DRUM_NAMES.get(pitch, f"drum {pitch}")
