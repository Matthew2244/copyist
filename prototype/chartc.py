#!/usr/bin/env python3
"""chartc — compile a .chart file (CHART-FORMAT.md) into MusicXML.

First increment, built against the Matt's Blues worked example. Implements:
header, band block, chord progressions and the full bars grammar, pickup,
sections with labels/repeats, `as engraved` lifts (each part's own bars from
the source engraving, exact), `groove` slash generation with chord symbols,
tacet, solo/backgrounds/text annotations, and score + per-part emission.

Second increment adds the demo door (CHART-FORMAT.md 3.4.1): a `demo:`
header, per-band demo tracks with octave correction, `from demo bars A-B
[at bar N]` directives with `eighths`/`triplets` quantization hints and
`fall`, `mute <name>`/`open` technique text, extended chord qualities with
degree emission, per-part attributes (key, clef, transposition) for charts
with no source engraving, and a real metronome mark. Conversion itself
lives in chartdemo.py.

Deliberately not built yet (each one errors in a sentence rather than
guessing): named `figure` blocks and inline `notes:` figures, volta
endings, `double`, `cue`, `build:`, `on pass`.

Usage: chartc.py <file.chart> [-o outdir]
"""
import os
import re
import sys
import argparse

import chartdemo
import instruments
import chartgroove

BEATS = 4          # the 4/4 default; parse_meter unlocks the rest


def parse_meter(text):
    """'6/8' -> (6, 8). The denominator must divide a whole note."""
    m = re.fullmatch(r'(\d{1,2})\s*/\s*(1|2|4|8|16)', str(text).strip())
    if not m:
        fail(f"cannot read meter '{text}' — write it like 3/4 or 6/8")
    num, den = int(m.group(1)), int(m.group(2))
    if not 1 <= num <= 24:
        fail(f"meter {num}/{den}: {num} beats in a bar is not a bar")
    return num, den

# Horn identity for demo-sourced parts: written transposition in
# semitones, FOLD range, clef, key-signature offset, COMFORTABLE range.
# All ranges are sounding pitch. The philosophy, from the composer:
# floors are hardware (a note below the horn folds up), ceilings are
# chops (a lead player screams to written double C and beyond, so the
# fold ceiling sits at the documented extremes and high notes get
# FLAGGED, never destroyed). Checked against the arranging literature:
# lead trumpet books run to written C7; trombone pedal Bb1 is common in
# commercial scoring; every modern bari has the low A (sounding C2);
# sax altissimo starts above written F#.
def _inst(transpose, fold, clef, foff, comf, poly=False, grand=False):
    return {'transpose': transpose, 'fold': fold, 'clef': clef,
            'foff': foff, 'comf': comf, 'poly': poly, 'grand': grand}


HORNS = {
    # woodwinds
    'piccolo':           _inst(-12, (73, 108), 'G', 0, (74, 103)),
    'flute':             _inst(0,  (59, 98),  'G', 0, (60, 96)),
    'oboe':              _inst(0,  (58, 93),  'G', 0, (58, 89)),
    'clarinet':          _inst(2,  (50, 96),  'G', 2, (50, 89)),
    'bass clarinet':     _inst(14, (34, 82),  'G', 2, (37, 74)),
    'bassoon':           _inst(0,  (34, 76),  'F', 0, (34, 72)),
    'soprano sax':       _inst(2,  (56, 92),  'G', 2, (56, 84)),
    'alto sax':          _inst(9,  (49, 88),  'G', 3, (49, 80)),
    'tenor sax':         _inst(14, (44, 86),  'G', 2, (44, 76)),
    'baritone sax':      _inst(21, (36, 78),  'G', 3, (37, 68)),
    # brass
    'trumpet':           _inst(2,  (54, 98),  'G', 2, (54, 82)),
    'c trumpet':         _inst(0,  (54, 96),  'G', 0, (54, 80)),
    'flugelhorn':        _inst(2,  (54, 91),  'G', 2, (54, 80)),
    'french horn':       _inst(7,  (35, 77),  'G', 1, (41, 74)),
    'trombone':          _inst(0,  (34, 82),  'F', 0, (40, 70)),
    'bass trombone':     _inst(0,  (31, 74),  'F', 0, (34, 67)),
    'tuba':              _inst(0,  (26, 65),  'F', 0, (29, 60)),
    # strings
    'violin':            _inst(0,  (55, 105), 'G', 0, (55, 96)),
    'viola':             _inst(0,  (48, 88),  'C', 0, (48, 81)),
    'cello':             _inst(0,  (36, 81),  'F', 0, (36, 69)),
    'double bass':       _inst(12, (28, 60),  'F', 0, (28, 50)),
    # rhythm
    'guitar':            _inst(12, (40, 88),  'G', 0, (40, 76), poly=True),
    # a four-string's floor is its low E; the low B is a five-string's
    'electric bass':     _inst(12, (28, 60),  'F', 0, (31, 55)),
    'five-string bass':  _inst(12, (23, 60),  'F', 0, (26, 55)),
    'piano':             _inst(0,  (21, 108), 'G', 0, (21, 108), poly=True,
                               grand=True),
    'vibraphone':        _inst(0,  (53, 89),  'G', 0, (53, 89), poly=True),
    'organ':             _inst(0,  (24, 96),  'G', 0, (24, 96), poly=True,
                               grand=True),
    # orchestral doubles and colors
    'english horn':      _inst(7,  (52, 81),  'G', 1, (52, 79)),
    'alto flute':        _inst(5,  (55, 91),  'G', -1, (55, 88)),
    'eb clarinet':       _inst(-3, (55, 96),  'G', 3, (55, 91)),
    'a clarinet':        _inst(3,  (49, 93),  'G', -3, (49, 86)),
    'cornet':            _inst(2,  (54, 94),  'G', 2, (54, 82)),
    'euphonium':         _inst(0,  (34, 70),  'F', 0, (40, 67)),
    'harp':              _inst(0,  (24, 103), 'G', 0, (24, 103), poly=True,
                               grand=True),
    'celesta':           _inst(-12, (60, 108), 'G', 0, (60, 108), poly=True,
                               grand=True),
    'marimba':           _inst(0,  (45, 96),  'G', 0, (45, 96), poly=True),
    'xylophone':         _inst(-12, (65, 108), 'G', 0, (65, 108), poly=True),
    'glockenspiel':      _inst(-24, (79, 108), 'G', 0, (79, 108), poly=True),
    'timpani':           _inst(0,  (38, 60),  'F', 0, (41, 55)),
    'banjo':             _inst(0,  (48, 88),  'G', 0, (50, 81)),
    'mandolin':          _inst(0,  (55, 88),  'G', 0, (55, 84)),
    'accordion':         _inst(0,  (41, 96),  'G', 0, (41, 96), poly=True),
    'harmonica':         _inst(0,  (48, 84),  'G', 0, (48, 84)),
    # pitched percussion colors
    'chimes':            _inst(0,   (60, 77),  'G', 0, (60, 77)),
    'crotales':          _inst(-24, (84, 108), 'G', 0, (84, 108)),
    'steel pan':         _inst(0,   (57, 89),  'G', 0, (57, 89), poly=True),
    # drums, hand percussion and the aux cabinet: percussion clef, no
    # key — grooves, kicks and words, and `from demo` writes real kit
    # notation (instruments.DRUM_MAP positions and noteheads)
    'drums':             _inst(0,  (0, 127),  'percussion', 0, (0, 127),
                               poly=True),
    'congas':            _inst(0,  (0, 127),  'percussion', 0, (0, 127),
                               poly=True),
    'bongos':            _inst(0,  (0, 127),  'percussion', 0, (0, 127),
                               poly=True),
    'timbales':          _inst(0,  (0, 127),  'percussion', 0, (0, 127),
                               poly=True),
    'cowbell':           _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'claves':            _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'shaker':            _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'maracas':           _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'tambourine':        _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'guiro':             _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'cabasa':            _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'triangle':          _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'woodblock':         _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'temple blocks':     _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'castanets':         _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'agogo':             _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'djembe':            _inst(0,  (0, 127),  'percussion', 0, (0, 127),
                               poly=True),
    'cajon':             _inst(0,  (0, 127),  'percussion', 0, (0, 127),
                               poly=True),
    'snare drum':        _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'bass drum':         _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'suspended cymbal':  _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'crash cymbal':      _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'tam-tam':           _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'sleigh bells':      _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'mark tree':         _inst(0,  (0, 127),  'percussion', 0, (0, 127)),
    'percussion':        _inst(0,  (0, 127),  'percussion', 0, (0, 127),
                               poly=True),
    # hand bells are pitched — a whole choir of them
    'hand bells':        _inst(0,  (48, 96),  'G', 0, (48, 96), poly=True),
    # voices — nobody left out
    'voice':             _inst(0,  (48, 84),  'G', 0, (50, 79)),
    'soprano':           _inst(0,  (60, 84),  'G', 0, (60, 81)),
    'mezzo':             _inst(0,  (57, 81),  'G', 0, (57, 79)),
    'alto voice':        _inst(0,  (53, 77),  'G', 0, (55, 74)),
    'tenor voice':       _inst(12, (48, 72),  'G', 0, (48, 69)),
    'baritone voice':    _inst(0,  (41, 67),  'F', 0, (43, 65)),
    'bass voice':        _inst(0,  (40, 64),  'F', 0, (40, 62)),
}

KEY_FIFTHS = {'c': 0, 'g': 1, 'd': 2, 'a': 3, 'e': 4, 'b': 5, 'f#': 6,
              'c#': 7, 'f': -1, 'bb': -2, 'eb': -3, 'ab': -4, 'db': -5,
              'gb': -6, 'cb': -7}

# MusicXML Standard Sound and 1-based GM program, so renderers play a
# horn chart with horns rather than the default piano.
SOUNDS = {
    'piccolo':        ('Piccolo', 'wind.flutes.flute.piccolo', 73),
    'flute':          ('Flute', 'wind.flutes.flute', 74),
    'oboe':           ('Oboe', 'wind.reed.oboe', 69),
    'clarinet':       ('Clarinet', 'wind.reed.clarinet.bflat', 72),
    'bass clarinet':  ('Bass Clarinet', 'wind.reed.clarinet.bass', 72),
    'bassoon':        ('Bassoon', 'wind.reed.bassoon', 71),
    'soprano sax':    ('Soprano Saxophone', 'wind.reed.saxophone.soprano', 65),
    'alto sax':       ('Alto Saxophone', 'wind.reed.saxophone.alto', 66),
    'tenor sax':      ('Tenor Saxophone', 'wind.reed.saxophone.tenor', 67),
    'baritone sax':   ('Baritone Saxophone', 'wind.reed.saxophone.baritone', 68),
    'trumpet':        ('Trumpet', 'brass.trumpet.bflat', 57),
    'c trumpet':      ('Trumpet in C', 'brass.trumpet.c', 57),
    'flugelhorn':     ('Flugelhorn', 'brass.flugelhorn', 57),
    'french horn':    ('Horn in F', 'brass.french-horn', 61),
    'trombone':       ('Trombone', 'brass.trombone', 58),
    'bass trombone':  ('Bass Trombone', 'brass.trombone.bass', 58),
    'tuba':           ('Tuba', 'brass.tuba', 59),
    'violin':         ('Violin', 'strings.violin', 41),
    'viola':          ('Viola', 'strings.viola', 42),
    'cello':          ('Cello', 'strings.cello', 43),
    'double bass':    ('Double Bass', 'strings.contrabass', 44),
    'guitar':         ('Guitar', 'pluck.guitar.electric', 27),
    'electric bass':  ('Electric Bass', 'pluck.bass.electric', 34),
    'five-string bass': ('5-String Bass', 'pluck.bass.electric', 34),
    'piano':          ('Piano', 'keyboard.piano', 1),
    'vibraphone':     ('Vibraphone', 'pitched-percussion.vibraphone', 12),
    'organ':          ('Organ', 'keyboard.organ', 17),
    'english horn':   ('English Horn', 'wind.reed.english-horn', 70),
    'alto flute':     ('Alto Flute', 'wind.flutes.flute.alto', 74),
    'eb clarinet':    ('Eb Clarinet', 'wind.reed.clarinet.eflat', 72),
    'a clarinet':     ('Clarinet in A', 'wind.reed.clarinet.a', 72),
    'cornet':         ('Cornet', 'brass.cornet', 57),
    'euphonium':      ('Euphonium', 'brass.euphonium', 58),
    'harp':           ('Harp', 'pluck.harp', 47),
    'celesta':        ('Celesta', 'keyboard.celesta', 9),
    'marimba':        ('Marimba', 'pitched-percussion.marimba', 13),
    'xylophone':      ('Xylophone', 'pitched-percussion.xylophone', 14),
    'glockenspiel':   ('Glockenspiel', 'pitched-percussion.glockenspiel', 10),
    'timpani':        ('Timpani', 'drum.timpani', 48),
    'banjo':          ('Banjo', 'pluck.banjo', 106),
    'mandolin':       ('Mandolin', 'pluck.mandolin', 25),
    'accordion':      ('Accordion', 'keyboard.accordion', 22),
    'harmonica':      ('Harmonica', 'wind.reed.harmonica', 23),
    'chimes':         ('Chimes', 'pitched-percussion.tubular-bells', 15),
    'crotales':       ('Crotales', 'pitched-percussion.crotales', 10),
    'steel pan':      ('Steel Pan', 'pitched-percussion.steel-drums', 115),
    'drums':          ('Drum Set', 'drum.group.set', 1),
    'congas':         ('Congas', 'drum.conga', 1),
    'bongos':         ('Bongos', 'drum.bongo', 1),
    'timbales':       ('Timbales', 'drum.timbale', 1),
    'cowbell':        ('Cowbell', 'metal.cowbell', 1),
    'claves':         ('Claves', 'wood.claves', 1),
    'shaker':         ('Shaker', 'rattle.shaker', 1),
    'maracas':        ('Maracas', 'rattle.maraca', 1),
    'tambourine':     ('Tambourine', 'drum.tambourine', 1),
    'guiro':          ('Guiro', 'wood.guiro', 1),
    'cabasa':         ('Cabasa', 'rattle.cabasa', 1),
    'triangle':       ('Triangle', 'metal.triangle', 1),
    'woodblock':      ('Woodblock', 'wood.wood-block', 1),
    'temple blocks':  ('Temple Blocks', 'wood.temple-block', 1),
    'castanets':      ('Castanets', 'wood.castanets', 1),
    'agogo':          ('Agogo', 'metal.bells.agogo', 1),
    'djembe':         ('Djembe', 'drum.djembe', 1),
    'cajon':          ('Cajon', 'drum.cajon', 1),
    'snare drum':     ('Snare Drum', 'drum.snare-drum', 1),
    'bass drum':      ('Bass Drum', 'drum.bass-drum', 1),
    'suspended cymbal': ('Suspended Cymbal', 'metal.cymbal.suspended', 1),
    'crash cymbal':   ('Crash Cymbal', 'metal.cymbal.crash', 1),
    'tam-tam':        ('Tam-tam', 'metal.tamtam', 1),
    'sleigh bells':   ('Sleigh Bells', 'metal.bells.sleigh-bells', 1),
    'mark tree':      ('Mark Tree', 'metal.bells.mark-tree', 1),
    'percussion':     ('Percussion', 'drum.group', 1),
    'hand bells':     ('Hand Bells', 'metal.hi-bell', 15),
    'voice':          ('Voice', 'voice.vocals', 54),
    'soprano':        ('Soprano', 'voice.soprano', 53),
    'mezzo':          ('Mezzo-soprano', 'voice.mezzo-soprano', 53),
    'alto voice':     ('Alto', 'voice.alto', 53),
    'tenor voice':    ('Tenor', 'voice.tenor', 54),
    'baritone voice': ('Baritone', 'voice.baritone', 54),
    'bass voice':     ('Bass', 'voice.bass', 54),
}


# How musicians actually say it: each instruction accepts the words of
# the bandstand, normalized before parsing. Ordered longest-first.
PIECE_SYNONYMS = [
    (r'^fall ?off$', 'fall'),
    (r'^(housetop|rooftop|daht)$', 'marcato'),
    (r'^(ten|ten\.)$', 'tenuto'),
    (r'^(accents|accented)$', 'accent'),
    (r'^(stabs?|punchy|punched)$', 'marcato'),
    (r'^triplet eighths$', 'eighth triplets'),
    (r'^triplet sixteenths$', 'sixteenth triplets'),
    (r'^quarter notes$', 'quarters'),
    (r'^crescendo\b', 'cresc'),
    (r'^(diminuendo|decrescendo|decresc)\b', 'dim'),
    (r'^slide\b', 'scoop'),
    (r'^(swung|swing) sixteenths$', 'sixteenth triplets'),
    (r'^sixteenth note triplets$', 'sixteenth triplets'),
    (r'^eighth note triplets$', 'eighth triplets'),
    (r'^eighth notes$', 'eighths'),
    (r'^sixteenth notes$', 'sixteenths'),
    (r'^straight eighth notes$', 'eighths'),
    (r'^straight sixteenth notes$', 'sixteenths'),
]

DYN_WORDS = [('sforzando', 'sfz'), ('fortissimo', 'ff'),
             ('pianissimo', 'pp'), ('mezzo forte', 'mf'),
             ('mezzo piano', 'mp'), ('forte piano', 'fp'),
             ('forte', 'f'), ('piano', 'p')]


# The bell cabinet, the world section and the effects rack: every one
# an unpitched percussion chair (clef, channel 10, grooves/kicks/words),
# added in one sweep so the aux table never has to ask permission.
_MORE_PERC = {
    'cha-cha bell':  ('Cha-cha Bell', 'metal.cowbell'),
    'mambo bell':    ('Mambo Bell', 'metal.cowbell'),
    'bongo bell':    ('Bongo Bell', 'metal.cowbell'),
    'almglocken':    ('Almglocken', 'metal.almglocken'),
    'bell tree':     ('Bell Tree', 'metal.bells.bell-tree'),
    'finger cymbals': ('Finger Cymbals', 'metal.cymbal.finger'),
    'bell plate':    ('Bell Plate', 'metal.bells.bell-plate'),
    'vibraslap':     ('Vibraslap', 'rattle.vibraslap'),
    'flexatone':     ('Flexatone', 'metal.flexatone'),
    'ratchet':       ('Ratchet', 'rattle.ratchet'),
    'whip':          ('Whip', 'wood.slapstick'),
    'anvil':         ('Anvil', 'metal.anvil'),
    'brake drum':    ('Brake Drum', 'metal.brake-drums'),
    'thunder sheet': ('Thunder Sheet', 'metal.thundersheet'),
    'rainstick':     ('Rainstick', 'rattle.rainstick'),
    'ocean drum':    ('Ocean Drum', 'drum.ocean-drum'),
    'log drum':      ('Log Drum', 'drum.log-drum'),
    'sandpaper blocks': ('Sandpaper Blocks', 'wood.sand-block'),
    'washboard':     ('Washboard', 'wood.washboard'),
    'spoons':        ('Spoons', 'wood.spoons'),
    'doumbek':       ('Doumbek', 'drum.doumbek'),
    'frame drum':    ('Frame Drum', 'drum.frame-drum'),
    'riq':           ('Riq', 'drum.riq'),
    'pandeiro':      ('Pandeiro', 'drum.pandeiro'),
    'surdo':         ('Surdo', 'drum.surdo'),
    'tamborim':      ('Tamborim', 'drum.tamborim'),
    'cuica':         ('Cuica', 'drum.cuica'),
    'tabla':         ('Tabla', 'drum.tabla'),
    'udu':           ('Udu', 'drum.udu'),
    'bata':          ('Bata', 'drum.bata'),
    'shekere':       ('Shekere', 'rattle.shekere'),
    'caxixi':        ('Caxixi', 'rattle.caxixi'),
    'repinique':     ('Repinique', 'drum.repinique'),
    'bodhran':       ('Bodhran', 'drum.bodhran'),
    'taiko':         ('Taiko', 'drum.taiko'),
}
for _n, (_disp, _sid) in _MORE_PERC.items():
    HORNS[_n] = _inst(0, (0, 127), 'percussion', 0, (0, 127),
                      poly=_n in ('tabla', 'bata', 'taiko', 'surdo'))
    SOUNDS[_n] = (_disp, _sid, 1)


# What players call their instruments — normalized before lookup, the
# same courtesy the directive words get.
INSTRUMENT_ALIASES = {
    'bari sax': 'baritone sax', 'bari': 'baritone sax',
    'sop sax': 'soprano sax',
    'horn': 'french horn', 'f horn': 'french horn',
    'clarinet in a': 'a clarinet', 'clarinet in bb': 'clarinet',
    'bb clarinet': 'clarinet', 'clarinet in eb': 'eb clarinet',
    'e flat clarinet': 'eb clarinet', 'alto flute in g': 'alto flute',
    'trumpet in bb': 'trumpet', 'bb trumpet': 'trumpet',
    'trumpet in c': 'c trumpet',
    'horn in f': 'french horn',
    'bone': 'trombone', 't-bone': 'trombone',
    'flugel': 'flugelhorn', 'picc': 'piccolo',
    'upright bass': 'double bass', 'string bass': 'double bass',
    # on a bandstand "upright" alone is the bass player
    'upright': 'double bass', 'stand-up bass': 'double bass',
    'standup bass': 'double bass', 'stand up bass': 'double bass',
    'upright piano': 'piano',
    'acoustic bass': 'double bass', 'contrabass': 'double bass',
    'bass': 'electric bass', 'bass guitar': 'electric bass',
    '5-string bass': 'five-string bass', '5 string bass': 'five-string bass',
    'five string bass': 'five-string bass', '5-string': 'five-string bass',
    '5 string': 'five-string bass', 'five-string': 'five-string bass',
    'keys': 'piano', 'keyboard': 'piano', 'rhodes': 'piano',
    'hammond': 'organ', 'b3': 'organ',
    'vibes': 'vibraphone', 'fiddle': 'violin',
    'violoncello': 'cello',
    'drum set': 'drums', 'drum kit': 'drums', 'kit': 'drums',
    'vocals': 'voice', 'vocal': 'voice', 'lead vocal': 'voice',
    'singer': 'voice',
    'conga': 'congas', 'bongo': 'bongos', 'timbale': 'timbales',
    'tubular bells': 'chimes', 'wind chimes': 'mark tree',
    'steel drums': 'steel pan', 'steel drum': 'steel pan',
    'pans': 'steel pan',
    'gong': 'tam-tam', 'tamtam': 'tam-tam',
    'sus cymbal': 'suspended cymbal', 'crash': 'crash cymbal',
    'snare': 'snare drum', 'kick drum': 'bass drum',
    'wood block': 'woodblock',
    'perc': 'percussion', 'aux': 'percussion',
    'aux percussion': 'percussion', 'hand percussion': 'percussion',
    'bells': 'glockenspiel',       # concert-band speak
    'orchestra bells': 'glockenspiel',
    'handbells': 'hand bells',
    'campana': 'bongo bell', 'timbale bell': 'mambo bell',
    'chacha bell': 'cha-cha bell', 'cha cha bell': 'cha-cha bell',
    'darbuka': 'doumbek', 'dumbek': 'doumbek',
    'slapstick': 'whip', 'wind machine': 'thunder sheet',
    'clackers': 'ratchet',
}


_TIMES = {'once': 1, 'twice': 2, 'one': 1, 'two': 2, 'three': 3,
          'four': 4, 'five': 5, 'six': 6, 'eight': 8}


def _count(word):
    return _TIMES.get(word) or int(word)


_ELECTRIC_FEELS = ('funk', 'rock', 'pop', 'r&b', 'rnb', 'soul', 'motown',
                   'reggae', 'one drop', 'hip hop', 'boom bap', 'dilla',
                   'gospel', 'fusion', 'disco', 'backbeat', 'straight 8',
                   'straight eighth', 'country', 'blues rock')


def bass_for_feel(feel):
    """A bare 'bass' on the band list, by the chart's feel: the upright
    for swing, waltz, ballad, bossa, latin and anything unsaid; the
    electric for funk, rock, pop, R&B, Motown, reggae, hip hop, gospel.
    The header's feel decides; a chart with no header feel goes by the
    sections' feels, electric if most of them are electric."""
    f = (feel or '').lower()
    return 'electric bass' if any(w in f for w in _ELECTRIC_FEELS) \
        else 'double bass'


def section_header(name, tail, loc):
    """The words after 'section NAME', comma by comma, in any order, the
    way a bandleader calls the form: '8 bars', 'label "Shout"', how many
    times round ('repeat 3x', 'play 3 times', 'x3', 'vamp 4 times'),
    'open' or 'till cue' (with 'vamp' for a vamp), who gives the cue
    ('drums cue', 'cue from the singer'), and where it goes after
    ('then cut to coda', 'on cue, cut to shout')."""
    sec = {'name': name, 'bars': None, 'label': None, 'repeat': 0,
           'open': False, 'vamp': False, 'cue_from': None, 'cut_to': None,
           'cut_back': False, 'cut': False}
    lab = re.search(r',\s*label "([^"]*)"', tail)
    if lab:
        sec['label'] = lab.group(1)
        tail = tail[:lab.start()] + tail[lab.end():]
    n = r'(\d+|once|twice|one|two|three|four|five|six|eight)'
    pieces = [p.strip().lower() for p in tail.split(',')]
    i = 0
    while i < len(pieces):
        p = pieces[i]
        i += 1
        if not p:
            continue
        if p == 'on cue' and i < len(pieces) and re.match(
                r'(?:then )?(?:cut|go|jump|skip)\b', pieces[i]):
            p = 'on cue ' + pieces[i]       # "on cue, cut to shout"
            i += 1
        m = re.fullmatch(r'(\d+) bars?', p)
        if m:
            sec['bars'] = int(m.group(1))
            continue
        m = (re.fullmatch(r'(?:repeat|play|vamp|repeat it)(?: it)? ' + n +
                          r'(?:x| times?)?', p)
             or re.fullmatch(n + r'(?:x| times)', p)
             or re.fullmatch(r'x' + n, p))
        if m:
            sec['repeat'] = _count(m.group(1))
            if sec['repeat'] < 2 and not p.startswith('vamp'):
                sec['repeat'] = 0              # "play once" is no repeat
            if p.startswith('vamp'):
                sec['vamp'] = True
                sec['repeat'] = max(sec['repeat'], 2) if \
                    sec['repeat'] > 1 else 0
            continue
        m = re.fullmatch(r'(open|vamp|repeat|play)?\s*(?:(?:till|until) '
                         r'(?:the )?cue|on cue)?', p)
        if m and p:
            if p in ('repeat', 'play'):
                fail(f"{loc}: section {name}: say how many times, like "
                     f"'{p} 3 times', or 'till cue'")
            sec['open'] = True
            sec['vamp'] = sec['vamp'] or p.startswith('vamp')
            continue
        m = (re.fullmatch(r'(?:the )?([\w ]+?)(?:\'s)? cues?(?: (?:it|out|'
                          r'the band))?', p)
             or re.fullmatch(r'(?:on |at )?(?:the )?cue (?:from|by) '
                             r'(?:the )?([\w ]+)', p))
        if m:
            sec['cue_from'] = m.group(1).strip()
            continue
        m = re.fullmatch(r'(on cue )?(?:then )?(?:cut|go|jump|skip)'
                         r'( back)?(?: to (?:the )?(?:letter )?'
                         r'([\w .-]+))?', p)
        if m:
            sec['cut'] = True
            sec['cut_to'] = (m.group(3) or '').strip() or None
            sec['cut_back'] = bool(m.group(2))
            if m.group(1):
                sec['open'] = True
            continue
        fail(f"{loc}: section {name}: cannot read '{p}'. A section "
             "takes 'N bars', 'label \"...\"', how many times ('repeat "
             "3 times', 'vamp 4x'), 'till cue' or 'vamp till cue', who "
             "cues it ('drums cue', 'cue from the singer'), and where it "
             "goes ('then cut to <section>', 'on cue, cut back to A')")
    if sec['bars'] is None:
        fail(f"{loc}: section {name} must declare its length")
    if sec['open'] and sec['repeat']:
        fail(f"{loc}: section {name} is both till cue and "
             f"{sec['repeat']} times: pick one")
    if sec['cue_from'] and not sec['open']:
        fail(f"{loc}: section {name}: {sec['cue_from']} cues it, but it "
             "does not go round till a cue. Add 'till cue' (or 'vamp "
             "till cue')")
    return sec


def canonical_instrument(name):
    n = name.strip().lower()
    return INSTRUMENT_ALIASES.get(n, n)


def normalize_piece(piece):
    for pat, repl in PIECE_SYNONYMS:
        piece = re.sub(pat, repl, piece)
    if piece.startswith('dyn '):
        for word, mark in DYN_WORDS:
            piece = re.sub(r'\b%s\b' % word, mark, piece)
    return piece


def parse_key(text):
    """'Eb minor' -> (fifths, mode); 'e flat minor' works too."""
    text = (text.strip().lower().replace(' flat', 'b')
            .replace(' sharp', '#'))
    m = re.fullmatch(r'([A-Ga-g][b#]?)\s*'
                     r'(major|minor|maj|min|mi|m)?', text)
    if not m:
        fail(f"cannot read key '{text}'")
    root = m.group(1).lower()
    mode = m.group(2) or 'major'
    # the compact spellings every writer types: Bm, Ebmin, F#mi
    mode = {'m': 'minor', 'mi': 'minor', 'min': 'minor',
            'maj': 'major'}.get(mode, mode)
    # G#, D# and A# are real minor keys (five, six, seven sharps); as
    # majors they fall outside seven fifths and are refused below
    roots = dict(KEY_FIFTHS, **{'g#': 8, 'd#': 9, 'a#': 10, 'fb': -8})
    if root not in roots:
        fail(f"cannot read key root '{m.group(1)}'")
    fifths = roots[root] + (-3 if mode == 'minor' else 0)
    if not -7 <= fifths <= 7:
        fail(f"key '{text}' needs {fifths} fifths — respell it")
    return fifths, mode
XMLHEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 '
           'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n')

CHORD_KINDS = {
    '7': ('dominant', '7'), '9': ('dominant-ninth', '9'),
    '11': ('dominant-11th', '11'), '13': ('dominant-13th', '13'),
    'maj': ('major', ''), 'maj7': ('major-seventh', 'maj7'),
    'm': ('minor', 'm'), 'm7': ('minor-seventh', 'm7'),
    'm9': ('minor-ninth', 'm9'), 'm6': ('minor-sixth', 'm6'),
    '6': ('major-sixth', '6'), 'dim': ('diminished', 'dim'),
    'dim7': ('diminished-seventh', 'dim7'),
    'm7b5': ('half-diminished', 'm7b5'),
    'sus4': ('suspended-fourth', 'sus4'),
    '7sus4': ('suspended-fourth', '7sus4'),
    'aug': ('augmented', 'aug'),
    'maj9': ('major-ninth', 'maj9'),
    'm11': ('minor-11th', 'm11'),
    '7#9': ('dominant', '7#9', [(9, 1, 'add')]),
    '7b9': ('dominant', '7b9', [(9, -1, 'add')]),
    '7#9#11': ('dominant', '7#9#11', [(9, 1, 'add'), (11, 1, 'add')]),
    '7#11': ('dominant', '7#11', [(11, 1, 'add')]),
    '13#11': ('dominant-13th', '13#11', [(11, 1, 'add')]),
    '13sus': ('dominant-13th', '13sus', [(4, -1, 'subtract')]),
    '7#9b13': ('dominant', '7#9b13', [(9, 1, 'add'), (13, -1, 'add')]),
    '69': ('major-sixth', '69', [(9, 0, 'add')]),
    'm69': ('minor-sixth', 'm69', [(9, 0, 'add')]),
    'alt': ('dominant', 'alt'),
    '13b9': ('dominant-13th', '13b9', [(9, -1, 'alter')]),
    'sus2': ('suspended-second', 'sus2'),
    'add9': ('major', 'add9', [(9, 0, 'add')]),
    'madd9': ('minor', 'madd9', [(9, 0, 'add')]),
    'mmaj7': ('major-minor', 'mmaj7'),
    'maj7#11': ('major-seventh', 'maj7#11', [(11, 1, 'add')]),
    '7#5': ('augmented-seventh', '7#5'),
    '7b5': ('dominant', '7b5', [(5, -1, 'alter')]),
    '7b13': ('dominant', '7b13', [(13, -1, 'add')]),
    # the ones real lead sheets and iReal charts use most that were
    # being simplified away on import (2026-09-27)
    '9sus4': ('dominant-ninth', '9sus4', [(3, 0, 'subtract'),
                                          (4, 0, 'add')]),
    '7b9b13': ('dominant', '7b9b13', [(9, -1, 'add'), (13, -1, 'add')]),
    '7b9#11': ('dominant', '7b9#11', [(9, -1, 'add'), (11, 1, 'add')]),
    '9#11': ('dominant-ninth', '9#11', [(11, 1, 'add')]),
    '13#9': ('dominant-13th', '13#9', [(9, 1, 'alter')]),
    'm13': ('minor-13th', 'm13'),
    'maj13': ('major-13th', 'maj13'),
    'maj9#11': ('major-ninth', 'maj9#11', [(11, 1, 'add')]),
    'm7b9': ('minor-seventh', 'm7b9', [(9, -1, 'add')]),
    '5': ('power', '5'),
    # what 1,460 real iReal jazz charts still needed (2026-09-27 tally):
    # the altered dominants first, then the rest of the tail
    '7#9#5': ('augmented-seventh', '7#9#5', [(9, 1, 'add')]),
    '7b9#5': ('augmented-seventh', '7b9#5', [(9, -1, 'add')]),
    'maj7#5': ('major-seventh', 'maj7#5', [(5, 1, 'alter')]),
    'mb6': ('minor', 'mb6', [(6, -1, 'add')]),
    '7b9sus4': ('suspended-fourth', '7b9sus4', [(7, -1, 'add'),
                                                (9, -1, 'add')]),
    '7b9b5': ('dominant', '7b9b5', [(5, -1, 'alter'), (9, -1, 'add')]),
    '9#5': ('augmented-ninth', '9#5'),
    '7#9b5': ('dominant', '7#9b5', [(5, -1, 'alter'), (9, 1, 'add')]),
    'm#5': ('minor', 'm#5', [(5, 1, 'alter')]),
    'm9b5': ('half-diminished', 'm9b5', [(9, 0, 'add')]),
    '9b5': ('dominant-ninth', '9b5', [(5, -1, 'alter')]),
    'mmaj9': ('major-minor', 'mmaj9', [(9, 0, 'add')]),
}

# jazz shorthand for qualities: the dash minor, min and mi spellings
# (the 8-Bit Big Band books write Ami7 and Bmi9), bare sus
QUAL_SYNONYMS = {'-': 'm', '-7': 'm7', '-9': 'm9', '-11': 'm11',
                 '-6': 'm6', 'min': 'm', 'min7': 'm7', 'min9': 'm9',
                 'mi': 'm', 'mi7': 'm7', 'mi9': 'm9', 'mi11': 'm11',
                 'mi6': 'm6', 'sus': 'sus4', '7sus': '7sus4',
                 '9sus': '9sus4', 'min13': 'm13', 'mi13': 'm13',
                 '7b9sus': '7b9sus4', 'm(b6)': 'mb6', 'm(maj9)': 'mmaj9',
                 'maj7+5': 'maj7#5', 'maj7(#5)': 'maj7#5', 'aug9': '9#5',
                 '7alt#5': '7#9#5',
                 '13sus4': '13sus',
                 '-13': 'm13', 'ma13': 'maj13', 'ma9': 'maj9',
                 'ma7': 'maj7',
                 'M7': 'maj7', 'm(maj7)': 'mmaj7', 'aug7': '7#5',
                 '7alt': 'alt'}

STEP = set('ABCDEFG')


def fail(msg):
    sys.exit("chartc: " + msg)


# ------------------------------------------------------------- parsing

def parse_beat(tok):
    m = re.fullmatch(r'(\d+)\+', tok)
    if m:
        return int(m.group(1)) + 0.5
    m = re.fullmatch(r'and-of-(\d+)', tok)
    if m:
        return int(m.group(1)) + 0.5
    m = re.fullmatch(r'(\d+)(\.5)?', tok)
    if m:
        return int(m.group(1)) + (0.5 if m.group(2) else 0.0)
    fail(f"cannot read beat '{tok}'")


def split_chord(sym):
    """'Bb7' -> ('B', -1, '7'); 'nc' -> None; bass slash split off."""
    if sym == 'nc':
        return None
    bass = None
    if '/' in sym:
        sym, bass = sym.split('/', 1)
    m = re.fullmatch(r'([A-G])([b#]?)(.*)', sym)
    if not m or m.group(1) not in STEP:
        fail(f"cannot read chord '{sym}'")
    step, acc, qual = m.groups()
    qual = qual or 'maj'
    qual = QUAL_SYNONYMS.get(qual, qual)
    if qual not in CHORD_KINDS and '(' in qual:
        # engravers parenthesize alterations — D7(#9) is D7#9
        bare = qual.replace('(', '').replace(')', '')
        bare = QUAL_SYNONYMS.get(bare, bare)
        if bare in CHORD_KINDS:
            qual = bare
    if qual not in CHORD_KINDS:
        fail(f"chord quality '{qual}' (in '{sym}') is not in the supported list")
    alter = {'b': -1, '#': 1, '': 0}[acc]
    return (step, alter, qual, bass)


def parse_bars(text, where):
    parse_bars.prev_sym = None      # /C reaches back within one line
    # engraver's alterations with commas, D7(#9,b13) or D7(b9, #11),
    # belong to their chord: the commas are not barlines
    text = re.sub(r'(?<=[0-9A-Za-z#])\(((?:\s*[b#]\d+\s*,?)+)\)',
                  lambda m: '(' + re.sub(r'[\s,]', '', m.group(1)) + ')',
                  text)
    # a parenthesized group repeats whole: ( F7, Bb7 ) x4 is eight
    # bars. A group stands at a bar boundary, so D7(#9) x2 — an
    # alteration in engraver's parentheses — is never mistaken for one.
    text = re.sub(r'(?:(?<=^)|(?<=,))\s*\(\s*([^()]*?)\s*\)\s*x(\d+)',
                  lambda m: ", ".join([m.group(1)] * int(m.group(2))),
                  text)
    bad = re.sub(r'\((?:[b#]\d+)+\)', '', text)  # alterations are fine
    if '(' in bad or ')' in bad:
        fail(f"unmatched parenthesis in {where} — a group is "
             "( chords ) xN, nothing nested")
    bars = []
    for raw in text.split(','):
        raw = raw.strip()
        if not raw:
            fail(f"empty bar in {where}")
        reps = 1
        m = re.fullmatch(r'(.*?)\s+x(\d+)', raw)
        if m:
            raw, reps = m.group(1).strip(), int(m.group(2))
        toks = raw.split()
        bar = []
        for tok in toks:
            if '@' in tok:
                sym, beat = tok.split('@', 1)
                bar.append([parse_beat(beat), sym])
            else:
                bar.append([None, tok])
        # a bare slash chord carries the previous chord over a new
        # bass — the guitar book's /C means "same chord, C in the
        # bass"
        for item in bar:
            m2 = re.fullmatch(r'/([A-G][b#]?)', item[1])
            if m2:
                if parse_bars.prev_sym is None:
                    fail(f"{where}: '{item[1]}' needs a chord before "
                         "it to carry over that bass note")
                item[1] = parse_bars.prev_sym.split('/')[0] \
                    + '/' + m2.group(1)
            elif item[1] != 'nc':
                parse_bars.prev_sym = item[1]
        # unplaced chords keep beat None here; the spread against the
        # bar's own meter happens once the meter map exists (a two-chord
        # bar in 5/4 splits at beat 3.5, not 3)
        for _ in range(reps):
            bars.append([(b, split_chord(s)) for b, s in bar])
    return bars


NOTE_DUR = {'w': 96, 'h': 48, 'q': 24, 'e': 12, 's': 6}


def parse_notes(text, loc):
    """The inline escape hatch (CHART-FORMAT.md 3.4): 'rest e, C5 e,
    A4 q+e, triplet( F4 e, A4 e, C5 e )' -> (items, grids, ticks).
    items are (ticks, concert_midi_or_None); grids mark triplet beats so
    the page names them in tuplet language. Deliberately minimal —
    anything long or intricate comes in by reference."""
    def dur_of(tok, scale_num=1, scale_den=1):
        total = 0
        for piece in tok.split('+'):
            m = re.fullmatch(r'([whqes])(\.?)', piece)
            if not m:
                fail(f"{loc}: cannot read duration '{tok}' — "
                     "w h q e s, with . for dotted and + for tied")
            t = NOTE_DUR[m.group(1)]
            if m.group(2):
                t = t * 3 // 2
            total += t * scale_num // scale_den
        return total

    def one(tok, sn=1, sd=1):
        m = re.fullmatch(r'rest ([whqes.+]+)', tok)
        if m:
            return (dur_of(m.group(1), sn, sd), None)
        m = re.fullmatch(r'([A-Ga-g])([b#]?)(-?\d)\s+([whqes.+]+)'
                         r'(?:\s+((?:tr|trill|trem|tremolo|roll)\b.*))?',
                         tok)
        if not m:
            fail(f"{loc}: cannot read note '{tok}' — like Bb4 q, "
                 "rest e, C5 q+e, or E5 h tr")
        base = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7,
                'a': 9, 'b': 11}[m.group(1).lower()]
        alt = {'b': -1, '#': 1, '': 0}[m.group(2)]
        midi = base + alt + (int(m.group(3)) + 1) * 12
        if m.group(5):
            return (dur_of(m.group(4), sn, sd), midi,
                    trill_spec(m.group(5), midi, loc))
        return (dur_of(m.group(4), sn, sd), midi)

    items, grids, pos = [], {}, 0
    for tok in re.split(r',(?![^(]*\))', text):
        tok = tok.strip()
        if not tok:
            fail(f"{loc}: empty item in notes:")
        m = re.fullmatch(r'triplet\(\s*(.*?)\s*\)', tok)
        if m:
            if pos % 24:
                fail(f"{loc}: a triplet group must start on the beat")
            inner = [t.strip() for t in m.group(1).split(',')]
            letters = {re.sub(r'[^whqes]', '', t)[-1:] for t in inner}
            if letters - {'e', 's'} or len(letters) != 1:
                fail(f"{loc}: a triplet group holds eighths or "
                     "sixteenths, one kind per group")
            sub = 3 if letters == {'e'} else 6
            start = pos
            for t in inner:
                ticks, midi = one(t, 2, 3)
                items.append((ticks, midi))
                pos += ticks
            if (pos - start) % 24:
                fail(f"{loc}: a triplet group must fill whole beats")
            for b in range(start // 24, pos // 24):
                grids[b] = sub
            continue
        item = one(tok)
        items.append(item)
        pos += item[0]
    return items, grids, pos


TRILL_WORDS = {'half': 1, 'half step': 1, 'semitone': 1, 'm2': 1,
               'whole': 2, 'whole step': 2, 'tone': 2, 'M2': 2,
               'aug 2nd': 3, 'augmented 2nd': 3, 'augmented second': 3,
               'minor 3rd': 3, 'minor third': 3, 'm3': 3,
               'major 3rd': 4, 'major third': 4, 'M3': 4,
               '4th': 5, 'fourth': 5, 'perfect 4th': 5, 'P4': 5,
               'tritone': 6, 'aug 4th': 6, '5th': 7, 'fifth': 7,
               'P5': 7}


def trill_spec(text, midi, loc):
    """'tr' / 'tr half' / 'tr minor 3rd' / 'tr to G5' -> the trill's
    target: ('key',) for the next note up in the key, ('up', n) for n
    semitones (an augmented second stays a second on the page), or
    ('to', midi) for an exact note. Every word states its interval, so
    nothing is guessed."""
    word = re.match(r'(tr|trill|trem|tremolo|roll)\b', text.strip()).group(1)
    rest = re.sub(r'^(tr|trill|trem|tremolo|roll)\b\s*', '', text.strip())
    if word in ('trem', 'tremolo', 'roll'):
        # a bowed or mallet tremolo on one note, or a fingered tremolo
        # between two: `trem`, `roll`, `trem to E5`
        if not rest:
            return ('trem',)
        m = re.fullmatch(r'to ([A-Ga-g])([b#]?)(-?\d)', rest)
        if not m:
            fail(f"{loc}: cannot read the tremolo '{text}' — trem, "
                 "roll, or trem to E5")
        base = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7,
                'a': 9, 'b': 11}[m.group(1).lower()]
        alt = {'b': -1, '#': 1, '': 0}[m.group(2)]
        to = base + alt + (int(m.group(3)) + 1) * 12
        if to == midi:
            return ('trem',)
        return ('ftrem', to, m.group(1).upper())
    if not rest:
        return ('key',)
    m = re.fullmatch(r'to ([A-Ga-g])([b#]?)(-?\d)', rest)
    if m:
        base = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7,
                'a': 9, 'b': 11}[m.group(1).lower()]
        alt = {'b': -1, '#': 1, '': 0}[m.group(2)]
        to = base + alt + (int(m.group(3)) + 1) * 12
        if to == midi:
            fail(f"{loc}: a trill to the note itself is no trill")
        return ('to', to, m.group(1).upper())
    n = TRILL_WORDS.get(rest) or TRILL_WORDS.get(rest.lower())
    if n:
        if rest.lower() in ('aug 2nd', 'augmented 2nd',
                            'augmented second'):
            return ('second', n)
        return ('up', n)
    fail(f"{loc}: cannot read the trill '{text}' — tr, tr half, "
         "tr whole, tr minor 3rd, tr major 3rd, tr 4th, or tr to G5")


def key_at(keys, bar):
    """The (fifths, mode) governing a printed bar."""
    cur = keys[0][1]
    for b, k in keys:
        if b <= bar:
            cur = k
    return cur


def meter_at(meters, bar):
    """The (num, den) governing a printed bar, from the chart's meter map
    — a sorted list of (first_bar, (num, den))."""
    cur = meters[0][1]
    for b, m in meters:
        if b <= bar:
            cur = m
    return cur


def seconds_before(chart, printed_bar):
    """Seconds of rendered audio before printed bar N — the trim point for
    a from-bar listen. Mirrors what the pages tell MuseScore: the last
    sound tempo governs until the next one, a compound bar's written tempo
    is a dotted quarter, and every bar is as long as its own meter says.
    Returns None when the header tempo is words."""
    hdr = chart['header']
    try:
        tempo = float(hdr.get('tempo', 120))
    except ValueError:
        return None
    meters = chart['meters']

    def qbpm_of(t, m):
        return t * (1.5 if m[1] == 8 and m[0] % 3 == 0 else 1.0)

    qbpm = qbpm_of(tempo, meter_at(meters, 1))
    tempo_at = {}
    start = 1
    for sec in chart['sections']:
        for bar, kind, text in sec['events']:
            if kind == 'tempo':
                tempo_at[start + bar - 1] = float(text)
        start += sec['bars']
    secs = 0.0
    pk = chart.get('pickup')
    if pk:
        secs += pk['beats'] * (4.0 / meter_at(meters, 1)[1]) * 60.0 / qbpm
    for b in range(1, printed_bar):
        n, d = meter_at(meters, b)
        if b in tempo_at:
            qbpm = qbpm_of(tempo_at[b], (n, d))
        secs += (n * 4.0 / d) * 60.0 / qbpm
    return secs


def parse_chart(path):
    chart = {'header': {}, 'band': [], 'chords': {}, 'sections': [],
             'groups': {}, 'figures': {}, 'pickup': None,
             'keyswitches': {}}
    cur = None          # current section
    cur_fig = None      # current figure block
    mode = None         # 'band' or None
    for lineno, line in enumerate(open(path, encoding='utf-8'), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        loc = f"line {lineno}"
        indented = line[0] in ' \t'

        if not indented:
            mode, cur = None, None
            if s == 'band:':
                mode = 'band'
                continue
            if s == 'output:':
                mode = 'output'
                continue
            m = re.match(r'keyswitches "([^"]+)":\s*$', s)
            if m:
                mode = 'ks'
                cur_ks = chart['keyswitches'].setdefault(
                    m.group(1).strip().lower(), {})
                continue
            m = re.match(r'chords ([\w ]+?):\s*(.+)$', s)
            if m:
                chart['chords'][m.group(1).strip()] = parse_bars(
                    m.group(2), f"chords {m.group(1)}")
                continue
            m = re.match(r'group ([\w ]+?):\s*(.+)$', s)
            if m:
                chart['groups'][m.group(1).strip()] = \
                    [x.strip() for x in m.group(2).split(',')]
                continue
            m = re.match(r'figure ([\w ]+?),\s*(\d+) (bars?|beats?):\s*$', s)
            if m:
                if m.group(3).startswith('beat'):
                    fail(f"{loc}: beat-length figures ride on inline "
                         "notes:, which is not built yet — declare bars")
                mode = 'figure'
                chart['figures'][m.group(1).strip()] = cur_fig = {
                    'bars': int(m.group(2)), 'kind': None, 'loc': loc,
                    'used': False}
                continue
            if re.match(r'figure ', s):
                fail(f"{loc}: a figure is 'figure <name>, <N> bars:' "
                     "with its source on the next, indented line")
            m = re.match(r'pickup (\d+(?:\.\d+)?) beats'
                         r'((?:,\s*as engraved)?)(?::\s*(.*))?$', s)
            if m:
                texts = re.findall(r'text "([^"]*)"', m.group(3) or '')
                # a pickup may be a beat and a half (a dotted-quarter
                # lead-in); whole beats stay whole numbers
                pb = float(m.group(1))
                chart['pickup'] = {'beats': int(pb) if pb == int(pb)
                                   else pb,
                                   'engraved': bool(m.group(2)),
                                   'texts': texts}
                continue
            m = re.match(r'section ([\w .-]+?)((?:,.*)?)$', s)
            if m:
                cur = dict(section_header(m.group(1).strip(), m.group(2),
                                          loc),
                           content=None, feel=None, directives=[],
                           events=[], endings=[])
                chart['sections'].append(cur)
                continue
            m = re.match(r'(\w+):\s*(.+)$', s)
            if m and m.group(1) in ('title', 'composer', 'arranger', 'key',
                                    'meter', 'tempo', 'feel', 'source',
                                    'demo', 'countin', 'dynamics', 'look',
                                    'lyricist', 'from', 'rev', 'number'):
                chart['header'][m.group(1)] = m.group(2).strip().strip('"')
                continue
            fail(f"{loc}: cannot read '{s}'")

        # indented lines
        if mode == 'band':
            m = re.match(r'([\w ]+?)(?:\s*=\s*([\w ]+?))?'
                         r'(?:,\s*detail (\w[\w-]*))?'
                         r'(?:,\s*tuning ([\w ]+))?'
                         r'(?:,\s*demo "([^"]+)"(?:\s+octave (-?\d+))?)?'
                         r'(?:,\s*keyswitches "([^"]+)")?'
                         r'(?:,\s*drummap "([^"]+)")?\s*$',
                         s)
            if not m:
                fail(f"{loc}: cannot read band line '{s}'")
            inst = (m.group(2) or m.group(1)).strip()
            if inst.lower() == 'bass':
                # which bass is decided by the feel, after the header
                chart.setdefault('_bare_bass', []).append(
                    m.group(1).strip())
            if canonical_instrument(inst) not in HORNS:
                # on a band list a bare alto or tenor is the sax, as the
                # interview has it; the singer is "alto voice"
                if inst.lower() in ('alto', 'tenor'):
                    inst = inst + ' sax'
                else:
                    fail(f"{loc}: '{inst}' is not an instrument Copyist "
                         "knows. Say what it is after an equals sign, "
                         f"like '{m.group(1).strip()} = alto sax'")
            chart['band'].append({'label': m.group(1).strip(),
                                  'instrument': inst,
                                  'detail': m.group(3),
                                  'tuning': m.group(4),
                                  'demo': m.group(5),
                                  'demo_octave': int(m.group(6) or 0),
                                  'keyswitches': m.group(7),
                                  'drummap': m.group(8)})
            continue
        if mode == 'output':
            continue        # defaults only in this increment
        if mode == 'ks':
            k, word = parse_ks_line(s, loc)
            cur_ks[k] = word
            continue
        if mode == 'figure':
            m = re.match(r'lyrics:\s*(.+)$', s)
            if m:
                if not cur_fig['kind']:
                    fail(f"{loc}: lyrics: follows the figure's source "
                         "line")
                # quotes around the words are the writer's fence,
                # not lyrics — strip a matched pair
                lyr = m.group(1).strip()
                if len(lyr) > 1 and lyr[0] == lyr[-1] and lyr[0] in '"\'':
                    lyr = lyr[1:-1]
                cur_fig['lyrics'] = lyr
                continue
            if cur_fig['kind']:
                fail(f"{loc}: one source per figure — this one already "
                     f"has its {cur_fig['kind']}")
            m = re.match(r'from midi "([^"]+)"'
                         r'(?:,\s*track "([^"]+)")?'
                         r',\s*bars (\d+)-(\d+)$', bar_words(s))
            if m:
                lo, hi = int(m.group(3)), int(m.group(4))
                if hi - lo + 1 != cur_fig['bars']:
                    fail(f"{loc}: the figure declares {cur_fig['bars']} "
                         f"bars but references {hi - lo + 1}")
                cur_fig.update(kind='midi', file=m.group(1),
                               track=m.group(2), lo=lo, hi=hi, loc=loc)
                continue
            m = re.match(r'from xml "([^"]+)",\s*part "([^"]+)"'
                         r',\s*bars (\d+)-(\d+)$', bar_words(s))
            if m:
                lo, hi = int(m.group(3)), int(m.group(4))
                if hi - lo + 1 != cur_fig['bars']:
                    fail(f"{loc}: the figure declares {cur_fig['bars']} "
                         f"bars but references {hi - lo + 1}")
                cur_fig.update(kind='xml', file=m.group(1),
                               part=m.group(2), lo=lo, hi=hi, loc=loc)
                continue
            m = re.match(r'notes:\s*(.+)$', s)
            if m:
                items, grids, ticks = parse_notes(m.group(1), loc)
                cur_fig.update(kind='inline', items=items, grids=grids,
                               ticks=ticks, loc=loc)
                continue
            fail(f"{loc}: cannot read figure source '{s}'")
        if cur is None:
            fail(f"{loc}: indented line outside any section: '{s}'")

        m = re.match(r'feel:\s*(.+)$', s)
        if m:
            cur['feel'] = m.group(1).strip()
            continue
        m = re.match(r'ending:\s*(.+)$', s)
        if m:
            cur['ending'] = (m.group(1).strip(), loc)
            continue
        m = re.match(r'chords:\s*(.+)$', s)
        if m:
            cur['content'] = parse_bars(m.group(1),
                                        f"section {cur['name']}")
            continue
        m = re.match(r'use chords ([\w ]+?)(?:\s+x(\d+))?$', s)
        if m:
            name = m.group(1).strip()
            if name not in parse_chart.defs_ref:
                pass
            cur['use'] = (name, int(m.group(2) or 1))
            continue
        m = re.match(r'ending (\d+),\s*(\d+) bars?:\s*chords:\s*(.+)$', s)
        if m:
            cur['endings'].append(
                {'num': int(m.group(1)), 'bars': int(m.group(2)),
                 'content': parse_bars(m.group(3),
                                       f"section {cur['name']} ending "
                                       f"{m.group(1)}")})
            continue
        m = re.match(r'build:\s*(.+)$', s)
        if m:
            for item in m.group(1).split(','):
                item = item.strip()
                mm = re.match(r'add ([\w ]+?) at (\d+)$', item)
                if not mm:
                    fail(f"{loc}: build items read 'add <who> at <bar>', "
                         f"not '{item}'")
                cur['events'].append((int(mm.group(2)), 'build',
                                      mm.group(1).strip()))
            continue
        m = re.match(r'at bar (\d+):\s*text "([^"]*)"$', s)
        if m:
            cur['events'].append((int(m.group(1)), 'text', m.group(2)))
            continue
        m = re.match(r'at bar (\d+):\s*tempo ([\d.]+)$', s)
        if m:
            cur['events'].append((int(m.group(1)), 'tempo', m.group(2)))
            continue
        m = re.match(r'at bar (\d+):\s*meter (\S+)$', s)
        if m:
            parse_meter(m.group(2))     # refuse nonsense at the line it sits on
            cur['events'].append((int(m.group(1)), 'meter', m.group(2)))
            continue
        m = re.match(r'at bar (\d+):\s*key (.+)$', s)
        if m:
            parse_key(m.group(2))       # refuse nonsense at the line it sits on
            cur['events'].append((int(m.group(1)), 'key',
                                  m.group(2).strip()))
            continue
        # the roadmap's fills and breaks (Matthew, 2026-09-29: "if you
        # say in the roadmap fill into whatever bar or beat, that should
        # happen ... or fill into a break")
        m = re.match(r'at bar (\d+)(?:,?\s*beat ([1-9](?:\.5)?))?:\s*'
                     r'(?:drums? )?fill$', s)
        if m:
            cur['events'].append((int(m.group(1)), 'fill',
                                  m.group(2) or ''))
            continue
        m = re.match(r'(?:drums? )?fill into bar (\d+)'
                     r'(?:,?\s*from beat ([1-9](?:\.5)?))?$', s)
        if m:
            n = int(m.group(1))
            if n < 2:
                fail(f"{loc}: 'fill into bar {n}' needs a bar before it "
                     "in this section — put 'fill into the next section' "
                     "on the section before, or 'at bar N: fill'")
            cur['events'].append((n - 1, 'fill', m.group(2) or ''))
            continue
        m = re.match(r'(?:drums? )?fill into (?:the )?next section$', s)
        if m:
            cur['events'].append((-1, 'fill', ''))     # its last bar
            continue
        m = re.match(r'at bar (\d+):\s*(?:a )?(?:stop|break)'
                     r'(?:,?\s*(\d+) bars?)?(,?\s*(?:drums? )?fill in'
                     r'(?:to it)?)?$', s)
        if m:
            n, k = int(m.group(1)), int(m.group(2) or 1)
            for b in range(n, n + k):
                cur['events'].append((b, 'break', 'first' if b == n
                                      else ''))
            if m.group(3):
                if n < 2:
                    fail(f"{loc}: a fill into a break on bar 1 needs a bar "
                         "before it in this section")
                cur['events'].append((n - 1, 'fill', ''))
            continue
        m = re.match(r'(?:drums? )?fill into (?:the )?(?:break|stop)$', s)
        if m:
            cur['events'].append((0, 'fill_break', ''))
            continue
        m = re.match(r'at bar (\d+):\s*fermata$', s)
        if m:
            cur['events'].append((int(m.group(1)), 'fermata', ''))
            continue
        m = re.match(r'at bar (\d+):\s*(segno|sign|coda|to coda|fine|'
                     r'd\.?\s?s\.?(?: al (?:coda|fine))?|'
                     r'd\.?\s?c\.?(?: al (?:coda|fine))?|'
                     r'dal segno(?: al (?:coda|fine))?|'
                     r'da capo(?: al (?:coda|fine))?)$', s, re.I)
        if m:
            cur['events'].append((int(m.group(1)), 'road',
                                  road_kind(m.group(2))))
            continue
        m = re.match(r'at bar (\d+):\s*cut(?: back)?(?: to)? here$', s)
        if m:
            # where a cut without a name lands ("cut back to here")
            cur['events'].append((int(m.group(1)), 'cutmark', ''))
            continue
        # the tempo words said bare, the way a bandleader writes them;
        # they print and perform exactly as text "..." does
        m = re.match(r'at bar (\d+):\s*((?:(?:molto|poco|poco a poco)\s+)?'
                     r'(?:rit\.?|ritard\.?|ritardando|rall\.?|rallentando|'
                     r'accel\.?|accelerando|slow down|speed up)|a tempo|'
                     r'tempo i|colla voce|fade out|fade)$', s, re.I)
        if m:
            cur['events'].append((int(m.group(1)), 'text', m.group(2)))
            continue
        if re.match(r'at bar \d+', s):
            fail(f"{loc}: cannot read '{s}'. After 'at bar N:' Copyist "
                 "takes text \"...\", tempo N, a tempo word (rit., "
                 "accel., a tempo), meter, key, fermata, fill, break, or "
                 "segno, coda, to coda, fine, d.s., d.c.")
        m = re.match(r'([\w ]+?):\s*(.+)$', s)
        if m:
            cur['directives'].append((m.group(1).strip(), m.group(2).strip(),
                                      loc))
            continue
        fail(f"{loc}: cannot read '{s}' in section {cur['name']}")

    for name, fig in chart['figures'].items():
        if not fig['kind']:
            fail(f"figure '{name}' has no source line")

    ci = chart['header'].get('countin', '0')
    if not str(ci).isdigit():
        fail(f"countin must be a number of bars, not '{ci}'")

    # resolve `use chords`
    for sec in chart['sections']:
        if 'use' in sec:
            name, times = sec.pop('use')
            if name not in chart['chords']:
                fail(f"section {sec['name']} uses chords '{name}', not defined")
            sec['content'] = chart['chords'][name] * times
        if sec['content'] is None:
            fail(f"section {sec['name']} has no chords")
        if sec['endings']:
            # the declared length is one pass: the body plus one ending.
            # the printed page carries the body and EVERY ending.
            es = sorted(sec['endings'], key=lambda e: e['num'])
            if not sec['repeat']:
                fail(f"section {sec['name']} has endings but no repeat — "
                     "say how many times it plays (repeat 2x)")
            if [e['num'] for e in es] != list(range(1, sec['repeat'] + 1)):
                fail(f"section {sec['name']} plays {sec['repeat']} times "
                     "but its ending numbers are "
                     + ", ".join(str(e['num']) for e in es)
                     + " — one ending per pass, numbered from 1")
            if len({e['bars'] for e in es}) != 1:
                fail(f"section {sec['name']}: endings must all be the "
                     "same length, so the declared bars mean one pass")
            for e in es:
                if len(e['content']) != e['bars']:
                    fail(f"section {sec['name']} ending {e['num']} "
                         f"declares {e['bars']} bars but its chords "
                         f"cover {len(e['content'])}")
            body = sec['bars'] - es[0]['bars']
            if len(sec['content']) != body:
                fail(f"section {sec['name']} declares {sec['bars']} bars "
                     f"(a {body}-bar body plus one {es[0]['bars']}-bar "
                     f"ending) but its chords cover {len(sec['content'])}")
            sec['body'] = body
            sec['endings'] = es
            for e in es:
                sec['content'] = sec['content'] + e['content']
            sec['bars'] = len(sec['content'])
        elif len(sec['content']) != sec['bars']:
            fail(f"section {sec['name']} declares {sec['bars']} bars but its "
                 f"chords cover {len(sec['content'])}")

    # ---- the meter map: the header meter at bar 1, changed by
    # `at bar N: meter` events, each holding until the next. Built here so
    # chord spreading, emission, the demo door and the listen math all
    # read one answer. Every timed event is also held to its section.
    # fills said relative to the form become bars: 'fill into the next
    # section' is this one's last bar; 'fill into the break' the bar
    # before its first break bar
    for sec in chart['sections']:
        evs = []
        for bar, kind, text in sec['events']:
            if kind == 'fill' and bar == -1:
                bar = sec['bars']
            if kind == 'fill_break':
                firsts = sorted(b for b, k, t in sec['events']
                                if k == 'break' and t == 'first')
                if not firsts or firsts[0] < 2:
                    fail(f"section {sec['name']}: 'fill into the break' "
                         "needs an 'at bar N: break' (N 2 or more) in "
                         "this section")
                bar, kind = firsts[0] - 1, 'fill'
            evs.append((bar, kind, text))
        sec['events'] = evs
    meters = [(1, parse_meter(chart['header'].get('meter', '4/4')))]
    start = 1
    for sec in chart['sections']:
        for bar, kind, text in sec['events']:
            if not 1 <= bar <= sec['bars']:
                fail(f"section {sec['name']}: 'at bar {bar}' is outside "
                     f"its {sec['bars']} bars")
            if kind == 'meter':
                absbar = start + bar - 1
                if any(b == absbar for b, _ in meters[1:]):
                    fail(f"section {sec['name']}: bar {bar} declares two "
                         "meters")
                meters.append((absbar, parse_meter(text)))
        start += sec['bars']
    meters.sort(key=lambda x: x[0])
    chart['meters'] = meters

    # the key map: the header's key, then every mid-chart change — a
    # working book modulates (the 8-Bit Big Band audit, 2026-09-22)
    base_key = parse_key(chart['header'].get('key', 'C'))
    keys = [(1, base_key)]
    start = 1
    for sec in chart['sections']:
        for bar, kind, text in sec['events']:
            if kind != 'key':
                continue
            absbar = start + bar - 1
            if absbar == 1:
                fail(f"section {sec['name']}: bar 1's key belongs in "
                     "the header")
            if any(b == absbar for b, _ in keys[1:]):
                fail(f"section {sec['name']}: bar {bar} declares two "
                     "keys")
            kf = parse_key(text)
            for b in chart['band']:
                h = HORNS.get(canonical_instrument(b['instrument']))
                wk = kf[0] + written_foff(h['foff'], kf[0]) if h else 0
                if h and not -7 <= wk <= 7:
                    fail(f"the key change to {text} lands "
                         f"{b['label']}'s written key at "
                         f"{wk} fifths — respell it")
            keys.append((absbar, kf))
        start += sec['bars']
    keys.sort(key=lambda x: x[0])
    chart['keys'] = keys

    # spread unplaced chords against each bar's own meter
    start = 1
    for sec in chart['sections']:
        content = []
        for off, bar in enumerate(sec['content']):
            beats = meter_at(meters, start + off)[0]
            n = len(bar)
            content.append([
                (b, c) if b is not None else
                (1.0 + i * (beats / n) if n > 1 else 1.0, c)
                for i, (b, c) in enumerate(bar)])
        sec['content'] = content
        start += sec['bars']
    # every bar's chord symbols, in printed bar numbers — the speller
    # reads them so a note spells the way its chord does
    chart['chord_bars'] = {}
    start = 1
    for sec in chart['sections']:
        for off, bar in enumerate(sec['content']):
            chart['chord_bars'][start + off] = [c for _, c in bar]
        start += sec['bars']
    # a bandleader who says "bass" on a swing chart means the upright;
    # on a funk or rock chart, the electric (Matthew, 2026-09-30: "you
    # like using the electric bass a lot in these demos")
    if chart.get('_bare_bass'):
        hf = chart['header'].get('feel', '')
        feels = [sec.get('feel') for sec in chart['sections']
                 if sec.get('feel')]
        if hf or not feels:
            which = bass_for_feel(hf)
        else:
            elec = sum(bass_for_feel(f) == 'electric bass' for f in feels)
            which = ('electric bass' if elec * 2 > len(feels)
                     else 'double bass')
        for b in chart['band']:
            if b['label'] in chart['_bare_bass'] and \
                    b['instrument'].lower() == 'bass':
                b['instrument'] = which
        chart['_bass_said'] = which
    return chart


parse_chart.defs_ref = {}


# ------------------------------------------------ spelling by the chord

def written_foff(foff, concert_fifths):
    """A transposing part's fifths offset in this key, respelled the way
    publishers respell: E major on alto sax is C# major (seven sharps),
    B major would be G# major (eight, not a key at all) — both print in
    flats instead, Db and Ab. Beyond six sharps or flats a written key
    moves twelve fifths, the same sounds on the other side of the
    circle. Concert-pitch parts keep the key the writer chose."""
    if not foff:
        return 0
    w = concert_fifths + foff
    if w > 6:
        return foff - 12
    if w < -6:
        return foff + 12
    return foff


# a chord tone's distance from its root on the line of fifths: the major
# third is four fifths up, the minor third three down, and so on — the
# form that turns "A7" into C# rather than Db without a lookup table
DEGREE_FIFTHS = {'3': 4, 'b3': -3, '5': 1, 'b5': -6, '#5': 8, '7': 5,
                 'b7': -2, 'bb7': -9, '6': 3, 'b6': -4, '9': 2, 'b9': -5,
                 '#9': 9, '11': -1, '#11': 6, '13': 3, 'b13': -4,
                 '4': -1, '2': 2}
_STEP_FIFTH = {s: i for i, s in enumerate("FCGDAEB")}


def chord_degrees(qual):
    """The chord tones a quality names, as degrees: 'm7b5' -> b3 b5 b7."""
    if qual == '5':
        return {'5'}
    if qual == 'alt':
        return {'3', 'b7', 'b9', '#9', '#11', 'b13'}
    minor = qual.startswith('m') and not qual.startswith('maj')
    if qual.startswith('dim'):
        third, fifth = 'b3', 'b5'
    elif qual.startswith('aug'):
        third, fifth = '3', '#5'
    else:
        third, fifth = ('b3' if minor else '3'), '5'
    if 'sus4' in qual or qual.endswith('sus'):
        third = '4'
    elif 'sus2' in qual:
        third = '2'
    if 'b5' in qual:
        fifth = 'b5'
    elif '#5' in qual:
        fifth = '#5'
    degs = {third, fifth}
    base = re.sub(r'[b#]\d+', '', qual)
    if base.startswith('dim7'):
        degs.add('bb7')
    elif 'maj' in base and re.search(r'7|9|13', base):
        degs.add('7')
    elif re.search(r'7|9|11|13', base) and not re.match(
            r'(m?6|m?69|m?add)', base):
        degs.add('b7')
    for acc, num in re.findall(r'([b#]?)(13|11|9|6)', qual):
        d = acc + num
        if d in DEGREE_FIFTHS:
            degs.add(d)
    return degs


def chord_spelling(syms, foff=0):
    """{pitch class: (step, alter)} for the chord tones of one bar's
    symbols, shifted foff fifths into a transposing part's frame. A pitch
    class two chords in the bar spell differently is left to the key."""
    from spelling import spell_fifth
    out, clash = {}, set()
    for sym in syms:
        # the parser leaves each chord as (step, alter, quality, bass);
        # a raw symbol is accepted too, for callers outside a chart
        try:
            got = split_chord(sym) if isinstance(sym, str) else sym
        except SystemExit:
            continue
        if not got or len(got) != 4:
            continue
        step, alter, qual, bass = got
        root = _STEP_FIFTH[step] + 7 * alter
        places = [root] + [root + DEGREE_FIFTHS[d]
                           for d in chord_degrees(qual)]
        if bass:
            m = re.fullmatch(r'([A-G])([b#]?)', bass)
            if m:
                places.append(_STEP_FIFTH[m.group(1)]
                              + 7 * {'b': -1, '#': 1, '': 0}[m.group(2)])
        for f in places:
            st, al, pc = spell_fifth(f + foff)
            if abs(al) > 2:
                continue
            if pc in out and out[pc] != (st, al):
                clash.add(pc)
            out[pc] = (st, al)
    for pc in clash:
        del out[pc]
    return out


def spelling_hints(chart, key, foff=0):
    """(minor_at, chords_at) for a part whose written key sits foff
    fifths from concert: what KeyedTable needs to spell like a copyist."""
    keys_ = chart.get('keys') or [(1, key)]
    bars = chart.get('chord_bars') or {}
    cache = {}

    def chords_at(b):
        if b not in cache:
            kf = key_at(keys_, b if b is not None else 1)[0]
            cache[b] = chord_spelling(bars.get(b, ()),
                                      written_foff(foff, kf))
        return cache[b]
    return (lambda b: key_at(keys_, b if b is not None else 1)[1]
            == 'minor', chords_at)


# --------------------------------------------------------- source score

def source_part_name(xml, pid):
    """A score part's name as a band label can find it: its part-name,
    else its abbreviation, else its instrument's name, else its id. A
    part named " " (Sibelius leaves some blank) must still be reachable,
    and two blank parts must not collapse into one."""
    import html as _html
    m = re.search(r'<score-part id="%s"[^>]*>(.*?)</score-part>'
                  % re.escape(pid), xml, re.S)
    body = m.group(1) if m else ''
    for rx in (r'<part-name[^>]*>([^<]*)</part-name>',
               r'<part-abbreviation[^>]*>([^<]*)</part-abbreviation>',
               r'<instrument-name>([^<]*)</instrument-name>'):
        n = re.search(rx, body)
        n = _html.unescape(n.group(1)) if n else ''
        n = re.sub(r'\s*\(\d+\)\s*$', '', n).strip()
        if re.search(r'\w', n):
            return n
    return pid


def load_source(path):
    # a Sibelius export writes `<chord />`; lifted bars must carry the
    # compact form every reader downstream expects
    xml = re.sub(r'\s+/>', '/>', open(path, encoding='utf-8').read())
    order = re.findall(r'<score-part id="([^"]+)"', xml)
    names = {pid: source_part_name(xml, pid) for pid in order}
    parts = {}
    for pid in order:
        body = re.search(r'<part id="%s">(.*?)</part>' % pid, xml, re.S).group(1)
        ms = {}
        for num, content in re.findall(
                r'<measure [^>]*?number="([^"]+)"[^>]*>(.*?)</measure>',
                body, re.S):
            ms[num] = content
        dv = re.search(r'<divisions>(\d+)</divisions>', body)
        staves = re.search(r'<staves>(\d+)</staves>', body)
        clef = re.search(r'<clef[^>]*>\s*<sign>(\w+)</sign>', body)
        fifths = re.search(r'<fifths>(-?\d+)</fifths>', body)
        parts[names[pid]] = {
            'measures': ms, 'div': int(dv.group(1)) if dv else 8,
            'staves': int(staves.group(1)) if staves else 1,
            'clef': clef.group(1) if clef else 'G',
            'fifths': int(fifths.group(1)) if fifths else 0}
    return parts


def match_part(label, source_names):
    """Band label -> unique source part name, by token prefix matching."""
    drop = {'in', 'bb', 'eb', 'f', 'c'}
    # words only: a score's "I (Trumpet)" must match the label
    # "i trumpet", so punctuation never counts as part of a word
    lt = re.findall(r'[\w#]+', label.lower())
    # "trumpet in bb" names the same part as "Trumpet in Bb": the
    # transposition words drop from both sides, never only one
    lt = [t for t in lt if t not in drop] or lt
    hits = []
    for name in source_names:
        nt = [t for t in re.findall(r'[\w#]+', name.lower())
              if t not in drop]
        if all(any(a.startswith(b) or b.startswith(a) for a in nt) for b in lt):
            hits.append(name)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        fail(f"band part '{label}' matches no part in the source score")
    fail(f"band part '{label}' is ambiguous in the source score: {hits}")


# ------------------------------------------------------------ emission

def strip_lifted(content, percussion=False):
    """Remove what the compiler owns from a lifted measure: rehearsal marks,
    words, metronome marks, harmony, print/layout. Keep notes, dynamics,
    wedges, attributes, barlines."""
    content = re.sub(r'<harmony[^>]*>.*?</harmony>\s*', '', content, flags=re.S)
    if percussion:
        # a key signature on a percussion staff renders every slash with a
        # courtesy natural in MuseScore — strip it, drums have no key
        content = re.sub(r'<key[^>]*>.*?</key>\s*', '', content, flags=re.S)
    content = re.sub(r'<print[^>]*/>\s*|<print[^>]*>.*?</print>\s*', '',
                     content, flags=re.S)

    def keep(m):
        block = m.group(0)
        # the road map is the engraving's, not ours: "To Coda", "D.S.
        # al Coda", "Fine" and the signs travel with the bars they sit
        # on, or the listen could never follow them
        if re.search(r'<segno|<coda|<sound [^>]*(dalsegno|dacapo|tocoda'
                     r'|fine|segno|coda)=', block) or re.search(
                r'<words[^>]*>\s*(D\.?\s?[SC]\.?|To Coda|Fine|Dal Segno'
                r'|Da Capo)', block, re.I):
            return block
        if re.search(r'<rehearsal|<words|<metronome', block):
            return ''
        return block
    return re.sub(r'<direction[^>]*>.*?</direction>\s*', keep, content,
                  flags=re.S)


# road maps (2026-09-27): his own "I Thought About You" arrangement
# walks segno at 9, To Coda at 36, D.S. al Coda at 58, coda at 59 —
# the "zero occurrences" of §5 held only for the first eleven scores
ROAD_WORDS = {'segno': None, 'coda': None, 'tocoda': 'To Coda',
              'fine': 'Fine', 'ds': 'D.S.', 'ds_coda': 'D.S. al Coda',
              'ds_fine': 'D.S. al Fine', 'dc': 'D.C.',
              'dc_coda': 'D.C. al Coda', 'dc_fine': 'D.C. al Fine'}


def road_kind(text):
    t = re.sub(r'\s+', ' ', text.lower().replace('.', '')).strip()
    t = t.replace('dal segno', 'ds').replace('da capo', 'dc')
    t = t.replace('d s', 'ds').replace('d c', 'dc')
    return {'segno': 'segno', 'sign': 'segno', 'coda': 'coda',
            'to coda': 'tocoda', 'fine': 'fine', 'ds': 'ds',
            'ds al coda': 'ds_coda', 'ds al fine': 'ds_fine', 'dc': 'dc',
            'dc al coda': 'dc_coda', 'dc al fine': 'dc_fine'}[t]


def check_road(chart):
    """A road map that goes nowhere is refused in a sentence: a D.S.
    needs its sign, "al Coda" needs a To Coda and a coda, "al Fine"
    needs a Fine."""
    have = {}
    start = 1
    for sec in chart['sections']:
        for bar, kind, text in sec['events']:
            if kind == 'road':
                have.setdefault(text, start + bar - 1)
        start += sec['bars']
    if not have:
        return
    jumps = [k for k in have if k.startswith(('ds', 'dc'))]
    if len(jumps) > 1:
        fail("a chart takes one D.S. or D.C.; this one has "
             + ", ".join(ROAD_WORDS[k] for k in jumps))
    for k in jumps:
        if k.startswith('ds') and 'segno' not in have:
            fail(f"{ROAD_WORDS[k]} at bar {have[k]} has no sign to go "
                 "back to: add 'at bar N: segno' where it returns")
        if k.endswith('coda') and not ('tocoda' in have
                                       and 'coda' in have):
            fail(f"{ROAD_WORDS[k]} needs 'to coda' (where it leaves) and "
                 "'coda' (where it lands)")
        if k.endswith('fine') and 'fine' not in have:
            fail(f"{ROAD_WORDS[k]} needs 'at bar N: fine' where it ends")
        if 'coda' in have and have['coda'] <= have[k]:
            fail(f"the coda at bar {have['coda']} must come after the "
                 f"{ROAD_WORDS[k]} at bar {have[k]}")


def say_road(listen_path):
    """The road map read back as the band will walk it, from the very
    document the listen plays: "bars 1-16, back to the sign: 5-12, then
    the coda: 17-24"."""
    import chartaudio
    xml = re.sub(r'\s+/>', '/>', open(listen_path, encoding='utf-8').read())
    road, ms = None, None
    for _pid, body in re.findall(r'<part id="([^"]+)">(.*?)</part>',
                                 xml, re.S):
        m_ = chartaudio._measures(body)
        mk = [chartaudio.roadmap_marks(m) for _n, m in m_]
        road = mk if road is None else [a | b for a, b in zip(road, mk)]
        ms = ms or m_
    if not ms or not any(k & {'ds', 'dc'} or any(
            x.startswith('cut:') for x in k) for k in road or []):
        return None
    walk = [n for n, _m in chartaudio.walk_cuts(
                chartaudio.expand_roadmap(ms, road), ms, road)
            if n.isdigit() and n != '0']
    runs = []
    for n in map(int, walk):
        if runs and runs[-1][1] + 1 == n:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    words = [f"{a}-{b}" if a != b else str(a) for a, b in runs]
    return ("the road map, as the band walks it (repeats included): "
            "bars " + ", then ".join(words))


def road_direction(kind):
    """A road-map mark as MusicXML: the sign or the words, plus the
    playback attribute any reader (ours included) follows."""
    if kind == 'segno':
        body, snd = '<segno/>', 'segno="segno"'
    elif kind == 'coda':
        body, snd = '<coda/>', 'coda="coda"'
    else:
        body = f'<words font-style="italic">{ROAD_WORDS[kind]}</words>'
        snd = {'tocoda': 'tocoda="coda"', 'fine': 'fine="yes"'}.get(
            kind, 'dacapo="yes"' if kind.startswith('dc')
            else 'dalsegno="segno"')
    return ('      <direction placement="above"><direction-type>'
            f'{body}</direction-type><sound {snd}/></direction>\n')


KS_DIR = os.path.expanduser("~/.config/copyist/keyswitches")


def parse_ks_line(s, loc):
    """'C0 legato' / 'C#-1 staccato' / '24 pizzicato' -> (midi, word).
    Note names are scientific (middle C is C4, MIDI 60); a library that
    counts middle C as C3 is one octave off, so the MIDI number is
    always accepted too — and the findings name both."""
    # a bracketed note after the name is for the reader of the map
    # ("[screenshot only]"), not part of the articulation
    s = re.sub(r'\s*\[[^\]]*\]\s*$', '', s)
    m = re.match(r'(\d{1,3})\s+(.+)$', s)
    if m and int(m.group(1)) < 128:
        return int(m.group(1)), m.group(2).strip()
    m = re.match(r'([A-Ga-g])([b#]?)(-?\d)\s+(.+)$', s)
    if not m:
        fail(f"{loc}: a keyswitch line is a key and its name, like "
             "'C0 legato' or '24 staccato', not '{s}'")
    pc = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9,
          'b': 11}[m.group(1).lower()] + {'b': -1, '#': 1, '': 0}[
              m.group(2)]
    return pc + (int(m.group(3)) + 1) * 12, m.group(4).strip()


def keyswitch_map(chart, name, loc='band'):
    """A part's keyswitch map: the chart's own block, else a saved
    library map in ~/.config/copyist/keyswitches/<name>.txt (same lines,
    written once for a patch and used by every chart)."""
    key = name.strip().lower()
    if key in chart.get('keyswitches', {}):
        return chart['keyswitches'][key]
    if os.path.isdir(KS_DIR):
        for fn in os.listdir(KS_DIR):
            if os.path.splitext(fn)[0].strip().lower() == key:
                out = {}
                for i, ln in enumerate(open(os.path.join(KS_DIR, fn),
                                            encoding='utf-8'), 1):
                    ln = ln.strip()
                    if ln and not ln.startswith('#'):
                        k, w = parse_ks_line(ln, f"{fn} line {i}")
                        out[k] = w
                return out
    fail(f"{loc}: no keyswitch map called \"{name}\": add a "
         f"'keyswitches \"{name}\":' block to the chart, or save one in "
         f"{KS_DIR}")


class DrumMap(dict):
    artic = {}


def bar_words(s):
    """A bar range as people write it -> the form the rules read:
    "bar 5" is "bars 5", and 1 to 4, 1 through 4, 1 thru 4, a typed
    en or em dash or spaced hyphen all mean 1-4."""
    bits = s.split('"')          # a quoted name is left exactly alone
    for i in range(0, len(bits), 2):
        t = re.sub(r'\bbar (\d)', r'bars \1', bits[i])
        bits[i] = re.sub(r'(?<=\d)\s*(?:\u2013|\u2014|-|\s(?:to|through'
                         r'|thru)\s)\s*(?=\d)', '-', t)
    return '"'.join(bits)


def drum_map_for(name, loc):
    if not name:
        return None
    import chartdrums
    key = instruments.DRUM_MAP_NAMES.get(name.strip().lower())
    saved = chartdrums.load_saved(name)
    if key or saved:
        # a built-in map, plus whatever the writer added to it (an AD2
        # kit's Flexi percussion, a cymbal that is really a china);
        # .artic carries the strokes they named - "snare ghost"
        m = DrumMap(instruments.DRUM_MAPS[key] if key else {})
        m.update(chartdrums.as_gm(saved))
        m.artic = chartdrums.artics(saved)
        return m
    fail(f"{loc}: no drum map called \"{name}\": Copyist knows "
         "Toontrack's (EZdrummer, Superior Drummer) and XLN's (Addictive "
         "Drums 2), and 'chart TUNE drums' names any other kit's notes "
         "once")


def lifted_rest(piece):
    """A bar lifted from an engraving that holds nothing but rests —
    no words, no dynamics, no chord, no signature change — can join a
    multirest like one of our own. Anything a player must see keeps the
    bar on its own."""
    if re.search(r'<direction|<harmony|<attributes|<barline|<print'
                 r'|<figured-bass', piece):
        return False
    notes = re.findall(r'<note[ >].*?</note>', piece, re.S)
    return bool(notes) and all('<rest' in n and '<cue' not in n
                               for n in notes)


TECHNIQUE_RE = re.compile(
    r"\s*(arco|pizz\.?|con sord|senza sord|sul |ord\.?\b|open\b|"
    r"[\w-]+ mute\b|mute\b)", re.I)


def direction(text, placement='above'):
    return (f'      <direction placement="{placement}">'
            f'<direction-type><words>{text}</words></direction-type>'
            f'</direction>\n')


def rehearsal(mark):
    return ('      <direction placement="above"><direction-type>'
            f'<rehearsal>{mark}</rehearsal></direction-type></direction>\n')


_NAT_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def transpose_chord(chord, t, foff=None):
    """The printed changes move with the horn: a Bb player's F7 is
    written G7. Letters move along the scale (so Bb reads as written C,
    never B-sharp) and the alter takes up the difference. Given the
    part's written fifths offset, the chord moves along the circle
    instead, so it follows a respelled key (Ab, not G#, for the alto
    in B major)."""
    if foff is not None and t % 12:
        def by_fifths(step, alter):
            f = 'FCGDAEB'.index(step) + 7 * alter + foff
            return 'FCGDAEB'[f % 7], f // 7
        step, alter, qual, bass = chord
        step, alter = by_fifths(step, alter)
        if bass:
            m = re.fullmatch(r'([A-G])([b#]?)', bass)
            bs, ba = by_fifths(m.group(1),
                               {'b': -1, '#': 1, '': 0}[m.group(2)])
            bass = bs + {-2: 'bb', -1: 'b', 0: '', 1: '#', 2: '##'}[ba]
        return (step, alter, qual, bass)
    if t % 12 == 0:
        return chord

    def move(step, alter):
        steps = round(t * 7 / 12)
        i = 'CDEFGAB'.index(step)
        new = 'CDEFGAB'[(i + steps) % 7]
        delta = (t % 12) - ((_NAT_PC[new] - _NAT_PC[step]) % 12)
        delta = (delta + 6) % 12 - 6
        return new, alter + delta

    step, alter, qual, bass = chord
    step, alter = move(step, alter)
    if bass:
        m = re.fullmatch(r'([A-G])([b#]?)', bass)
        bs, ba = move(m.group(1), {'b': -1, '#': 1, '': 0}[m.group(2)])
        bass = bs + {-2: 'bb', -1: 'b', 0: '', 1: '#', 2: '##'}[ba]
    return (step, alter, qual, bass)


def harmony_xml(chord, beat, pulse_div):
    step, alter, qual, bass = chord
    entry = CHORD_KINDS[qual]
    kind, ktext = entry[0], entry[1]
    degrees = entry[2] if len(entry) > 2 else []
    off = (beat - 1.0) * pulse_div
    if abs(off - round(off)) > 1e-6:
        fail(f"chord offset at beat {beat} is not integral at divisions {div}")
    out = ['      <harmony>',
           f'        <root><root-step>{step}</root-step>' +
           (f'<root-alter>{alter}</root-alter>' if alter else '') + '</root>',
           f'        <kind text="{ktext}">{kind}</kind>']
    if bass:
        bs = re.fullmatch(r'([A-G])([b#]?)', bass)
        ba = {'b': -1, '#': 1, '': 0}[bs.group(2)]
        out.append(f'        <bass><bass-step>{bs.group(1)}</bass-step>' +
                   (f'<bass-alter>{ba}</bass-alter>' if ba else '') + '</bass>')
    for dval, dalt, dtyp in degrees:
        out.append(f'        <degree><degree-value>{dval}</degree-value>'
                   f'<degree-alter>{dalt}</degree-alter>'
                   f'<degree-type>{dtyp}</degree-type></degree>')
    if round(off):
        out.append(f'        <offset>{int(round(off))}</offset>')
    out.append('      </harmony>')
    return "\n".join(out) + "\n"


SLASH_PITCH = {'G': ('B', 4), 'F': ('D', 3), 'C': ('C', 4),
               'percussion': ('B', 4)}

FLATS = 'BEADGCF'
SHARPS = 'FCGDAEB'


def key_alter(step, fifths):
    """The key signature's alteration for a step — so a slash note spelled
    on the middle line never earns an accidental (MuseScore renders the
    'unpitched' trick as a pitched natural, measured on the Bb chart)."""
    if fifths < 0:
        return -1 if step in FLATS[:-fifths] else 0
    if fifths > 0:
        return 1 if step in SHARPS[:fifths] else 0
    return 0


def slash_bar(div, clef, staves, fifths, meter=(4, 4)):
    num, den = meter
    pulse = div * 4 // den
    step, octv = SLASH_PITCH.get(clef, ('B', 4))
    alter = key_alter(step, fifths)
    if clef == 'percussion':
        pitch = ('        <unpitched><display-step>%s</display-step>'
                 '<display-octave>%d</display-octave></unpitched>'
                 % (step, octv))
    else:
        pitch = ('        <pitch><step>%s</step>%s<octave>%d</octave></pitch>'
                 % (step,
                    f'<alter>{alter}</alter>' if alter else '', octv))
    ptype = {1: 'whole', 2: 'half', 4: 'quarter', 8: 'eighth',
             16: '16th'}[den]
    out = []
    for _ in range(num):
        # dynamics="0": a slash is an instruction, not a pitch — playback
        # renderers must not sound the B the notehead happens to sit on
        out += ['      <note dynamics="0">',
                pitch,
                f'        <duration>{pulse}</duration>',
                '        <voice>1</voice>',
                f'        <type>{ptype}</type>',
                '        <stem>none</stem>',
                '        <notehead>slash</notehead>']
        if staves > 1:
            out.append('        <staff>1</staff>')
        out.append('      </note>')
    if staves > 1:
        bar = pulse * num
        out += [f'      <backup><duration>{bar}</duration></backup>',
                '      <note>',
                '        <rest measure="yes"/>',
                f'        <duration>{bar}</duration>',
                '        <voice>2</voice>',
                '        <staff>2</staff>',
                '      </note>']
    return "\n".join(out) + "\n"


def hits_bar(pattern, div, clef, staves, fifths, meter=(4, 4)):
    """Rhythmic kicks: slash noteheads WITH stems at the named beats,
    rests around them — 'hits on 1, 2+, 4' as the spec always promised.
    Each hit rings to the next hit or the bar line."""
    import convert as _c
    num, den = meter
    pulse = div * 4 // den
    step, octv = SLASH_PITCH.get(clef, ('B', 4))
    alter = key_alter(step, fifths)
    positions = sorted({int(round((b - 1) * pulse)) for b in pattern})
    out = []
    if positions and positions[0] > 0:
        for ln in _c.emit_rest(positions[0], div, 1, 1):
            out.append(ln)
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else pulse * num
        for plen, ptype, dots in _c.decompose(end - pos, div):
            if clef == 'percussion':
                pitch = ('        <unpitched><display-step>%s'
                         '</display-step><display-octave>%d'
                         '</display-octave></unpitched>' % (step, octv))
            else:
                pitch = ('        <pitch><step>%s</step>%s'
                         '<octave>%d</octave></pitch>'
                         % (step,
                            f'<alter>{alter}</alter>' if alter else '',
                            octv))
            out += ['      <note>', pitch,
                    f'        <duration>{plen}</duration>',
                    '        <voice>1</voice>',
                    f'        <type>{ptype}</type>']
            out += ['        <dot/>'] * dots
            out.append('        <notehead>slash</notehead>')
            if staves > 1:
                out.append('        <staff>1</staff>')
            out.append('      </note>')
    if staves > 1:
        bar = pulse * num
        out += [f'      <backup><duration>{bar}</duration></backup>',
                '      <note>',
                '        <rest measure="yes"/>',
                f'        <duration>{bar}</duration>',
                '        <voice>2</voice>',
                '        <staff>2</staff>',
                '      </note>']
    return "\n".join(out) + "\n"


def rest_bar(div, staves, meter=(4, 4)):
    bar = div * 4 * meter[0] // meter[1]
    out = []
    for staff in range(1, staves + 1):
        if staff == 2:
            out.append(f'      <backup><duration>{bar}</duration>'
                       '</backup>')
        out += ['      <note>',
                '        <rest measure="yes"/>',
                f'        <duration>{bar}</duration>',
                f'        <voice>{staff}</voice>']
        if staves > 1:
            out.append(f'        <staff>{staff}</staff>')
        out.append('      </note>')
    return "\n".join(out) + "\n"


# ------------------------------------------------------------ compile

def resolve_groups(band, custom=None):
    labels = [b['label'] for b in band]
    inst = {b['label']: canonical_instrument(b['instrument'])
            for b in band}
    g = {'all': labels[:],
         'saxes': [l for l in labels if 'sax' in inst[l]],
         'trumpets': [l for l in labels
                      if inst[l] in ('trumpet', 'cornet', 'flugelhorn')],
         'trombones': [l for l in labels if 'trombone' in inst[l]],
         'voices': [l for l in labels
                    if inst[l] in ('voice', 'soprano', 'mezzo',
                                   'alto voice', 'tenor voice',
                                   'baritone voice', 'bass voice')],
         'strings': [l for l in labels
                     if inst[l] in ('violin', 'viola', 'cello',
                                    'double bass', 'harp')],
         'rhythm': [l for l in labels if inst[l] in
                    ('guitar', 'piano', 'electric bass', 'double bass',
                     'five-string bass',
                     'drums', 'organ', 'vibraphone', 'banjo',
                     'accordion')]}
    g['horns'] = [l for l in labels
                  if l in g['saxes'] or l in g['trumpets'] or
                  l in g['trombones']]
    g['band'] = labels[:]
    for name, members in (custom or {}).items():
        for x in members:
            if x not in labels:
                fail(f"group {name} names '{x}', which is not in the band")
        g[name] = members
    return g


def compile_chart(chart_path, outdir):
    chart = parse_chart(chart_path)
    hdr = chart['header']
    meter = parse_meter(hdr.get('meter', '4/4'))
    src_path = hdr.get('source')
    if src_path and not os.path.isabs(src_path):
        src_path = os.path.join(os.path.dirname(os.path.abspath(chart_path)),
                                src_path)
    source = load_source(src_path) if src_path and os.path.exists(src_path) \
        else None
    if hdr.get('source') and source is None:
        fail(f"source score '{hdr['source']}' not found next to the chart")

    band = chart['band']
    groups = resolve_groups(band, chart.get('groups'))
    labels = [b['label'] for b in band]
    src_of = {}
    if source:
        for b in band:
            src_of[b['label']] = match_part(b['label'], source.keys())

    chord_parts = {l for l in labels
                   if l in groups['rhythm'] and
                   'drum' not in next(b for b in band
                                      if b['label'] == l)['instrument'].lower()}

    plans, total = build_plans(chart, band, groups, labels)
    check_road(chart)
    if source is None and any(
            plan['content'][l][0] == 'engraved'
            for plan in plans for l in labels):
        fail("'as engraved' is used but the chart has no source: line "
             "naming an engraving")

    # ---- the from-demo door
    findings = chartdemo.Findings()
    if chart.get('_bass_said'):
        up = chart['_bass_said'] == 'double bass'
        findings.add(f"band: 'bass' on a {'jazz' if up else 'backbeat'} "
                     f"chart is the {'upright' if up else 'electric'}; "
                     f"write 'bass = {'electric bass' if up else 'upright'}'"
                     " for the other")

    # meter changes worth saying out loud, in the writer's own bar numbers
    meters_map = chart['meters']
    spoken = int(hdr.get('countin', 0))
    tempo_bars = set()
    sstart = 1
    for sec in chart['sections']:
        for bar, kind, _ in sec['events']:
            if kind == 'tempo':
                tempo_bars.add(sstart + bar - 1)
        sstart += sec['bars']
    for b, m in meters_map[1:]:
        prev = meter_at(meters_map, b - 1) if b > 1 else None
        if m == prev:
            findings.add(f"bar {b + spoken} declares {m[0]}/{m[1]}, which "
                         "is already the meter — nothing changes")
            continue
        was_c = prev is not None and prev[1] == 8 and prev[0] % 3 == 0
        is_c = m[1] == 8 and m[0] % 3 == 0
        if prev is not None and was_c != is_c and b not in tempo_bars:
            findings.add(
                f"bar {b + spoken}: the meter changes {prev[0]}/{prev[1]} "
                f"to {m[0]}/{m[1]} with no new tempo — playback carries "
                "the quarter note across; add an 'at bar N: tempo' there "
                "if that is not the feel")

    resolved, horn_of, key = resolve_demo(chart, plans, band, labels,
                                          chart_path, findings, meter)
    demo_measures = {l: {} for l in labels}
    for l in labels:
        for item in resolved[l]:
            h = horn_of[l]
            tr, foff = h['transpose'], h['foff']
            # the key where this figure lands, not the header's: a tune
            # that modulates spells its later bars in their own key
            keys_ = chart.get('keys') or [(1, key)]
            fig_f = key_at(keys_, item['res']['at'])[0]
            minor_at, chords_at = spelling_hints(chart, key, foff)
            ms = chartdemo.render_range(item['res'],
                                        fig_f + written_foff(foff, fig_f),
                                        tr,
                                        item['fall'], findings,
                                        short=item['short'],
                                        every=item['every'],
                                        doit=item['doit'],
                                        scoops=item['scoops'],
                                        cue=item.get('cue', False),
                                        fifths_at=lambda b, k=keys_, f=foff:
                                        key_at(k, b)[0] + written_foff(
                                            f, key_at(k, b)[0]),
                                        minor_at=minor_at,
                                        chords_at=chords_at)
            for bar, xml in ms.items():
                if bar in demo_measures[l]:
                    fail(f"'{l}' has two demo figures landing on bar {bar}")
                demo_measures[l][bar] = xml
    # ---- figure lifts from MusicXML: written bars placed verbatim by
    # name. A lifted bar brings its source's divisions with it; the bar
    # after the figure restates the part's own — both of this pipeline's
    # readers track divisions per measure.
    div_marks = {l: {} for l in labels}
    lift_cache = {}
    for plan in plans:
        for l in labels:
            for ref in plan['lifts'][l]:
                f = ref['file'] if os.path.isabs(ref['file']) else \
                    os.path.join(os.path.dirname(
                        os.path.abspath(chart_path)), ref['file'])
                if f not in lift_cache:
                    if not os.path.exists(f):
                        fail(f"{ref['loc']}: figure source "
                             f"'{ref['file']}' not found next to the "
                             "chart")
                    lift_cache[f] = load_source(f)
                srcdoc = lift_cache[f]
                want = ref['part'].strip().lower()
                pname = next((k for k in srcdoc
                              if k.strip().lower() == want), None)
                if pname is None:
                    fail(f"{ref['loc']}: '{ref['part']}' is not a part "
                         f"of {os.path.basename(f)} — parts: "
                         + ", ".join(sorted(srcdoc)))
                sp = srcdoc[pname]
                perc = (horn_of.get(l) or {}).get('clef') == 'percussion'
                for i in range(ref['hi'] - ref['lo'] + 1):
                    srcbar = ref['lo'] + i
                    if str(srcbar) not in sp['measures']:
                        fail(f"{ref['loc']}: {os.path.basename(f)} part "
                             f"'{pname}' has no bar {srcbar}")
                    absbar = ref['at'] + i
                    if absbar in demo_measures[l]:
                        fail(f"'{l}' has two figures landing on bar "
                             f"{absbar}")
                    demo_measures[l][absbar] = strip_lifted(
                        sp['measures'][str(srcbar)], perc)
                    div_marks[l][absbar] = sp['div']
                div_marks[l].setdefault(
                    ref['at'] + ref['hi'] - ref['lo'] + 1, None)

    for name, fig in chart['figures'].items():
        if not fig['used']:
            findings.add(f"figure '{name}' is defined and never used")

    # ---- every part's fate per section (CHART-FORMAT.md 3.6): an
    # accidental twelve-bar rest is read back before it is printed
    for l in labels:
        fates, sounded = [], False
        for plan in plans:
            sec = plan['sec']
            kind, arg = plan['content'][l]
            if kind == 'default':
                kind = 'groove' if l in groups['rhythm'] else 'tacet'
            items = [i for i in resolved[l] if i['plan'] is plan]
            played = [i for i in items if not i.get('cue')]
            cued = [i for i in items if i.get('cue')]
            solo = any(isinstance(t[1], str)
                       and t[1].lower().startswith('solo')
                       for t in plan['texts'][l])
            if played:
                srcs = sorted({i['src_label'] + octave_words(
                                   i.get('octaves', 0)) + harmony_words(
                                   i.get('harm', 0))
                               for i in played if i.get('src_label')})
                ex = sorted({i['exploded'] for i in played
                             if i.get('exploded')})
                so = sorted({i['soli'] for i in played if i.get('soli')})
                if so:
                    what = ("soli under the " + " and ".join(so)
                            + ", voiced from the changes")
                elif ex:
                    what = "exploded from the " + " and ".join(ex)
                elif srcs:
                    what = "doubles the " + " and ".join(srcs)
                elif any(i['res'].get('detail') == 'rhythmic-slashes'
                         for i in played):
                    what = "your rhythm on slashes"
                else:
                    what = "your line"
            elif plan['lifts'][l]:
                what = "written figures"
            elif solo:
                what = "solo"
            elif plan.get('bg', {}).get(l):
                what = "backgrounds, made up in the listen"
            elif kind == 'engraved':
                what = "the engraving"
            elif kind == 'hits':
                what = "kicks"
            elif kind == 'groove':
                what = "slashes"
            else:
                what = "rest"
            enter = plan['enters'].get(l)
            if enter and what in ("kicks", "slashes"):
                what += f" from bar {enter}"
            elif enter and what == "rest":
                what = (f"rest — brought in at bar {enter}, but nothing "
                        "is written for it there")
            if what != "rest":
                sounded = True
            elif cued:
                what = "rest, with a cue to watch"
            fates.append(f"{sec['label'] or sec['name']}: {what}")
        findings.add(f"{l} — " + "; ".join(fates))
        if not sounded:
            findings.add(f"{l} NEVER PLAYS A BAR IN THIS CHART — "
                         "meant, or a missing line?")

    # ---- the range report: where each part peaks, in written pitch —
    # what an arranger checks before any page reaches a player
    shift = int(hdr.get('countin', 0))
    for l in labels:
        def bar_of_tick(start_bar, s):
            # the range report speaks bar numbers, and a bar is as
            # long as ITS meter says — a 12/8 chart once reported
            # peaks at bar 311 of 213 (Victory, 2026-09-22)
            b, t = start_bar, s
            while True:
                n_, d_ = meter_at(chart['meters'], b)
                bl = chartdemo.DIV * 4 * n_ // d_
                if t < bl:
                    return b
                t -= bl
                b += 1

        notes = [(p, bar_of_tick(item['res']['at'] + shift, s))
                 for item in resolved[l] if not item.get('cue')
                 and item['res'].get('detail') != 'rhythmic-slashes'
                 for s, e, ps in item['res']['timeline'] for p in ps]
        if not notes or l not in horn_of:
            continue
        h = horn_of[l]
        if h.get('clef') == 'percussion':
            findings.add(f"{l}: lifted from the demo as kit notation")
            continue
        tr, comf = h['transpose'], h['comf']
        hi = max(notes)
        lo = min(notes)
        keys_ = chart.get('keys') or [(1, key)]
        def wname(p, bar, _f=h['foff'], _k=keys_):
            # spelled in the key of ITS bar, as the page spells it
            kb = key_at(_k, bar - shift)
            wf = written_foff(_f, kb[0])
            table = chartdemo.spelling_table(
                kb[0] + wf, chartdemo.Findings(),
                minor=kb[1] == 'minor',
                chords=chord_spelling(
                    (chart.get('chord_bars') or {}).get(bar - shift, ()),
                    wf))
            s_, a_, o_ = chartdemo.convert.spell(p + tr, table)
            return f"{s_}{'b' if a_ == -1 else '#' if a_ == 1 else ''}{o_}"
        edge = ""
        if hi[0] > comf[1]:
            edge = (" — lead territory; know whose chops are on the "
                    "chair")
        elif hi[0] >= comf[1] - 2:
            edge = " — right at the top of the comfortable range"
        if lo[0] < comf[0]:
            edge += (" — and the low end sits in pedal territory"
                     if l == 'trombone' or 'trombone' in l
                     else " — and the low end is below the standard horn")
        findings.add(f"{l}: written peak {wname(*hi)} at bar {hi[1]}, "
                     f"lowest {wname(*lo)} at bar {lo[1]}{edge}")
    return _compile_rest(chart, band, groups, labels, plans, total,
                         source, src_of, chord_parts, hdr, chart_path, outdir,
                         demo_measures, horn_of, key, findings, meter,
                         div_marks)


def resolve_demo(chart, plans, band, labels, chart_path, findings,
                 meter=(4, 4)):
    """Resolve every from-demo overlay to a quantized timeline. Shared by
    the compiler and the read-aloud view — one resolver, two renderings."""
    hdr = chart['header']
    horn_of = {}
    demo_path = hdr.get('demo')
    if demo_path and not os.path.isabs(demo_path):
        demo_path = os.path.join(os.path.dirname(os.path.abspath(chart_path)),
                                 demo_path)
    chart_dir = os.path.dirname(os.path.abspath(chart_path))
    fifths, mode = parse_key(hdr['key']) if hdr.get('key') else (0, 'major')
    for b in band:
        inst = canonical_instrument(b['instrument'])
        if inst in HORNS:
            h = HORNS[inst]
            if b.get('tuning'):
                pitches = []
                for tok in b['tuning'].split():
                    m2 = re.fullmatch(r'([A-Ga-g])([b#]?)(-?\d)', tok)
                    if not m2:
                        fail(f"cannot read tuning note '{tok}' for "
                             f"'{b['label']}'")
                    base = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7,
                            'a': 9, 'b': 11}[m2.group(1).lower()]
                    alt = {'b': -1, '#': 1, '': 0}[m2.group(2)]
                    pitches.append(base + alt
                                   + (int(m2.group(3)) + 1) * 12)
                lo = min(pitches)
                lo_name = b['tuning'].split()[pitches.index(lo)]
                h = dict(h, fold=(lo, h['fold'][1]),
                         comf=(lo, h['comf'][1]))
                findings.add(f"{b['label']}: tuning honored — the floor "
                             f"is now {lo_name}")
            horn_of[b['label']] = h
    resolved = {l: [] for l in labels}
    for plan in plans:
        for l in labels:
            for ref in plan['overlays'][l]:
                b = next(x for x in band if x['label'] == l)
                if l not in horn_of:
                    fail(f"{ref['loc']}: '{l}' plays from the demo but its "
                         f"instrument '{b['instrument']}' is not in the "
                         "demo-part table")
                h = horn_of[l]
                tr, rng, foff = h['transpose'], h['fold'], h['foff']
                if ref.get('placed'):
                    findings.add(f"{l}: {ref['placed']}")
                if ref.get('inline'):
                    meters_map = chart.get('meters') or [(1, meter)]
                    fig_lo = max(1, ref['at'])
                    fig_hi = ref['at'] + (ref['hi'] - ref['lo'])
                    fig_meter = meter_at(meters_map, fig_lo)
                    for pb in range(fig_lo, fig_hi + 1):
                        if meter_at(meters_map, pb) != fig_meter:
                            fail(f"{ref['loc']}: '{l}' has a figure "
                                 "crossing the meter change at printed "
                                 f"bar {pb} — split it there")
                    res, rawmap = chartdemo.inline_res(
                        dict(ref, short=ref.get('short', False)),
                        fig_meter, int(hdr.get('countin', 0)),
                        fifths=key_at(chart.get('keys')
                                      or [(1, (fifths, mode))],
                                      fig_lo)[0])
                    if ref.get('legato'):
                        res['slurs'] = chartdemo._slur_runs(
                            res['timeline'], rawmap)
                    if ref.get('ghost'):
                        findings.add(f"{l}: an inline figure carries no "
                                     "velocities, so ghosts must be "
                                     "played in — none written")
                    chartdemo.attach_lyrics(
                        res, ref.get('lyrics') or ref.get('fig_lyrics'),
                        l, ref['loc'], findings)
                    resolved[l].append({'res': res, 'fall': ref['fall'],
                                        'short': ref.get('short', False),
                                        'every': ref.get('every'),
                                        'doit': ref.get('doit', False),
                                        'scoops': ref.get('scoops', []),
                                        'inline': True, 'plan': plan})
                    continue
                sel = ref['track'] or b['demo']
                if ref.get('file'):
                    f = ref['file'] if os.path.isabs(ref['file']) \
                        else os.path.join(chart_dir, ref['file'])
                    dm = chartdemo.load_demo(f)
                    track = ref['track']
                elif sel and sel.lower().endswith(('.mid', '.midi')):
                    dm = chartdemo.load_demo(sel if os.path.isabs(sel)
                                             else os.path.join(chart_dir, sel))
                    track = None
                else:
                    if not demo_path:
                        fail(f"{ref['loc']}: '{l}' uses from demo but the "
                             "chart has no demo: line")
                    dm = chartdemo.load_demo(demo_path)
                    track = sel
                meters_map = chart.get('meters') or [(1, meter)]
                fig_lo = max(1, ref['at'])
                fig_hi = ref['at'] + (ref['hi'] - ref['lo'])
                fig_meter = meter_at(meters_map, fig_lo)
                for pb in range(fig_lo, fig_hi + 1):
                    if meter_at(meters_map, pb) != fig_meter:
                        fail(f"{ref['loc']}: '{l}' has a demo figure "
                             f"crossing the meter change at printed bar "
                             f"{pb} — split the figure there")
                window = demo_window(dm, ref, fig_meter, meters_map,
                                     int(hdr.get('countin', 0)), l,
                                     findings)
                detail = ref.get('detail') or b.get('detail')
                if detail == 'full':
                    detail = None
                if detail in ('slashes', 'symbols'):
                    fail(f"{ref['loc']}: detail '{detail}' is what "
                         "'groove' and 'as demo' already print — use "
                         "those on the section line")
                if detail not in (None, 'simplified', 'rhythmic-slashes'):
                    fail(f"{ref['loc']}: detail levels here are full, "
                         f"simplified and rhythmic-slashes, not "
                         f"'{detail}'")
                if detail == 'rhythmic-slashes' and (ref.get('lyrics')
                                                     or ref.get('fig_lyrics')):
                    fail(f"{ref['loc']}: lyrics need pitches — a "
                         "slash rhythm carries none")
                res = chartdemo.resolve_range(
                    dm, track, ref['lo'], ref['hi'], ref['at'],
                    meter=fig_meter, window=window, detail=detail,
                    grand=h.get('grand', False),
                    octave_shift=b['demo_octave'],
                    sounding_range=rng, quant=ref.get('quant'),
                    poly=h['poly'],
                    legato=ref.get('legato', False),
                    ghost=ref.get('ghost', False),
                    trills=not ref.get('no_trills', False),
                    ks_map=(keyswitch_map(chart, b['keyswitches'],
                                          ref['loc'])
                            if b.get('keyswitches') else None),
                    drum_map=drum_map_for(b.get('drummap'), ref['loc']),
                    derive_dyns=hdr.get('dynamics', '') not in
                    ('by hand', 'manual'),
                    short=ref.get('short', False),
                    spoken_shift=int(hdr.get('countin', 0)),
                    part_label=l, findings=findings,
                    drums=h['clef'] == 'percussion')
                # a drum set (or the aux table, several instruments on
                # one chair) splits cymbals from drums; a conga, bongo or
                # bell player reads one voice, whatever the heads
                res['kit'] = canonical_instrument(b['instrument']) in (
                    'drums', 'percussion')
                chartdemo.attach_lyrics(
                    res, ref.get('lyrics') or ref.get('fig_lyrics'),
                    l, ref['loc'], findings)
                resolved[l].append({'res': res, 'fall': ref['fall'],
                                    'short': ref.get('short', False),
                                    'every': ref.get('every'),
                                    'doit': ref.get('doit', False),
                                    'scoops': ref.get('scoops', []),
                                    'plan': plan})
    # ---- explode: one part's chords dealt across a group's chairs
    for plan in plans:
        done_src = {}
        for target, (srcl, k, n, div_word, loc) in \
                plan.get('explode', {}).items():
            if srcl not in labels:
                fail(f"{loc}: '{srcl}' is not a band part to explode")
            items = done_src.setdefault(srcl, [
                i for i in resolved[srcl] if i['plan'] is plan])
            if not items:
                fail(f"{loc}: nothing to explode — '{srcl}' has no "
                     "played or figured line in this section")
            fold = (horn_of.get(target) or {}).get('fold')
            moved = []
            new = [dict(i, res=explode_res(i['res'], k, n, fold, moved),
                        cue=False, src_label=None, exploded=srcl)
                   for i in items]
            if target == srcl:
                resolved[srcl] = [i for i in resolved[srcl]
                                  if i['plan'] is not plan]
            resolved[target].extend(new)
            if moved:
                findings.add(f"{target}: exploded from {srcl}, "
                             f"{len(moved)} note(s) moved an octave into "
                             "range")
            if div_word:
                plan['texts'][target].append((1, 'div.'))
    # ---- soli: a written lead voiced down through the section from the
    # chord symbols (four-way close, drop 2 for four voices or more)
    for plan in plans:
        for target, (srcl, k, n, style, loc) in plan.get('soli',
                                                          {}).items():
            if srcl not in labels:
                fail(f"{loc}: '{srcl}' is not a band part to voice under")
            items = [i for i in resolved[srcl] if i['plan'] is plan]
            if not items:
                fail(f"{loc}: nothing to voice — '{srcl}' has no written "
                     "line in this section")
            # a soli voice lives in the chair's comfortable range, not
            # at the horn's limits (a bari at written F#6 on a shout)
            h_ = horn_of.get(target) or {}
            fold = h_.get('comf') or h_.get('fold')
            moved = []
            for i in items:
                r = soli_res(i['res'], k, n, style, plan, chart, fold,
                             moved)
                resolved[target].append(dict(i, res=r, cue=False,
                                             src_label=None, soli=srcl))
            if moved:
                findings.add(f"{target}: soli under the {srcl}, "
                             f"{len(moved)} note(s) moved an octave into "
                             "range")
    # ---- double and cue: another part's resolved line joins this one.
    # It re-renders with the TARGET's transposition and key, so a
    # doubled line is written for the player who now plays it; a cue
    # prints small and is never played.
    for plan in plans:
        for kind_map, is_cue in ((plan['doubles'], False),
                                 (plan['cues'], True)):
            for target, (srcl, shift, loc) in kind_map.items():
                word = "cue" if is_cue else "double"
                if srcl not in labels:
                    fail(f"{loc}: '{srcl}' is not a band part to {word}")
                items = [i for i in resolved[srcl] if i['plan'] is plan]
                if not items:
                    fail(f"{loc}: nothing to {word} — '{srcl}' has no "
                         "played or figured line in this section")
                first = min(i['res']['at'] for i in items)
                if is_cue:
                    plan['texts'][target].append(
                        (first - plan['start'] + 1, f"({srcl} cue)"))
                for i in items:
                    r = i['res']
                    if r.get('lyrics'):
                        # a double plays the line; only the voice sings
                        r = dict(r, lyrics=None, lyrics_text=None)
                    if shift:
                        r = shift_res(r, shift)
                    steps = 0 if is_cue else plan.get('harm', {}).get(
                        target, 0)
                    if steps:
                        # the arranger's "a third below": scale steps in
                        # the key in force where the line starts
                        r = harmonize_res(r, steps, key_at(
                            chart.get('keys') or [(1, (fifths, mode))],
                            r['at']))
                    resolved[target].append(dict(i, res=r, cue=is_cue,
                                                 src_label=srcl,
                                                 octaves=shift // 12,
                                                 harm=steps))

    return resolved, horn_of, (fifths, mode)


_OCT_WORDS = {'an': 1, 'one': 1, 'a': 1, 'two': 2, 'three': 3}


def octave_phrase(text):
    """'trumpet an octave down' -> ('trumpet', -12). The arranger's way
    of saying a double sits an octave off: 'an octave down/up/lower/
    higher/below/above', 'two octaves down', '8vb', '8va', '15ma', '15mb'.
    A bare part name comes back unshifted."""
    t = text.strip()
    m = re.match(r'(.+?)\s+(?:at\s+)?(8va|8vb|15ma|15mb|loco)$', t)
    if m:
        return m.group(1).strip(), {'8va': 12, '8vb': -12, '15ma': 24,
                                    '15mb': -24, 'loco': 0}[m.group(2)]
    m = re.match(r'(.+?)\s+(an|one|a|two|three|\d)\s+octaves?\s+'
                 r'(down|up|lower|higher|below|above)$', t)
    if m:
        n = _OCT_WORDS.get(m.group(2)) or int(m.group(2))
        sign = 1 if m.group(3) in ('up', 'higher', 'above') else -1
        return m.group(1).strip(), sign * 12 * n
    return t, 0


def explode_res(res, k, n, fold=None, moved=None):
    """Chair k of n's share of a resolved line's chords: the k-th note
    from the top; a chord shorter than the chairs doubles evenly when
    it divides, else repeats its lowest note (MuseScore's explode).
    Grand-staff voices merge first. A note under the chair's floor or
    over its ceiling moves by octaves into range."""
    onsets = {}
    lines = [res.get('timeline') or []]
    for st in res.get('staves') or ():
        lines += st['voices']
    for line in lines:
        for a, b, ps in line:
            e, got = onsets.get(a, (b, []))
            onsets[a] = (max(e, b), got + list(ps))
    tl = []
    for a in sorted(onsets):
        b, ps = onsets[a]
        ps = sorted(set(ps), reverse=True)
        if not ps:
            continue
        m = len(ps)
        if m >= n:
            p = ps[k]
        elif n % m == 0:
            p = ps[k // (n // m)]
        else:
            p = ps[k] if k < m else ps[-1]
        if fold:
            q = p
            while p < fold[0]:
                p += 12
            while p > fold[1]:
                p -= 12
            if p != q and moved is not None:
                moved.append(a)
        tl.append((a, b, [p]))
    # one voice now: a note ringing past the next onset stops there
    for i in range(len(tl) - 1):
        a, b, ps = tl[i]
        if b > tl[i + 1][0]:
            tl[i] = (a, tl[i + 1][0], ps)
    return dict(res, timeline=tl, staves=None, trills={}, trems={},
                ks={}, lyrics=None, lyrics_text=None)


_STEPS = {'second': 1, 'third': 2, 'fourth': 3, 'fifth': 4, 'sixth': 5,
          'seventh': 6, 'ninth': 8, 'tenth': 9, '2nd': 1, '3rd': 2,
          '4th': 3, '5th': 4, '6th': 5, '7th': 6, '9th': 8, '10th': 9}
_STEP_NAMES = {v: k for k, v in _STEPS.items() if not k[0].isdigit()}


def harmony_phrase(text):
    """'flugel a third below' -> ('flugel', -2): a double harmonized a
    diatonic interval away, counted in scale steps (a third is two).
    'in thirds below', 'a 6th above', 'a sixth under' read the same.
    Anything else comes back as (text, 0)."""
    t = text.strip()
    m = re.match(r'(.+?)\s+(?:a |an |in )?(' + '|'.join(_STEPS) +
                 r')s?\s+(below|above|down|up|under|over|lower|higher)$', t)
    if not m:
        return t, 0
    sign = 1 if m.group(3) in ('above', 'up', 'over', 'higher') else -1
    return m.group(1).strip(), sign * _STEPS[m.group(2)]


def harmony_words(steps):
    """' a third below' — said after a part name, the way it was asked."""
    if not steps:
        return ''
    return (f" a {_STEP_NAMES.get(abs(steps), str(abs(steps) + 1))} "
            f"{'above' if steps > 0 else 'below'}")


def harmonize_res(res, steps, key):
    """A resolved line moved by scale steps in key (fifths, mode): each
    note lands on the scale tone that many steps away. A chromatic note
    (a leading tone, a blue note) harmonizes from the scale tone it
    bends, so the harmony line itself stays in the key."""
    tonic = (key[0] * 7) % 12              # the relative major's tonic
    scale = sorted((tonic + x) % 12 for x in (0, 2, 4, 5, 7, 9, 11))

    def move(p):
        q = p if p % 12 in scale else (p - 1 if (p - 1) % 12 in scale
                                       else p + 1)
        octv, deg = divmod(q, 12)
        idx = octv * 7 + scale.index(deg) + steps
        o, d = divmod(idx, 7)
        return o * 12 + scale[d]
    return map_res(res, move)


def soli_res(res, k, n, style, plan, chart, fold=None, moved=None):
    """Voice k of n under a lead line (voice 0 is the lead itself): at
    each note, the chord sounding there as four notes; a chord tone in
    the lead is voiced close below it, a passing tone in parallel scale
    thirds; drop 2 (the second voice down an octave) for four voices or
    more unless 'close' was asked. A note past the chair's range moves
    an octave in."""
    import chartgroove as G
    meters = chart.get('meters') or [(1, (4, 4))]
    DIVQ = 24

    def chord_at(tick):
        absbar = res['at']
        t = tick
        while True:
            num, den = meter_at(meters, absbar)
            bt = DIVQ * 4 * num // den
            if t < bt:
                break
            t -= bt
            absbar += 1
        off = absbar - plan['start']
        beat = t / DIVQ + 1
        rows = plan['sec']['content']
        c = None
        for o in range(0, min(off, len(rows) - 1) + 1):
            for b_, cc in rows[o]:
                if cc is not None and (o < off or b_ <= beat + 1e-6):
                    c = cc
        return c

    def four(c, lead=None):
        root = G._root_pc(c)
        iv = [i for i in G._tones(c) if i < 12]
        if len(iv) < 4:
            iv.append(9 if 4 in iv else 10)
        if 11 in iv and 4 in iv and (lead is None
                                     or (lead - root) % 12 != 11):
            # a major chord voices as a sixth unless the melody is on the
            # major seventh: the 7 under the root is the rub arrangers
            # write around
            iv = [9 if i == 11 else i for i in iv]
        return [(root + i) % 12 for i in iv[:4]]

    style = style or ('drop2' if n >= 4 else 'close')
    tl = []
    for a, b, ps in res.get('timeline') or []:
        if not ps:
            continue
        m = max(ps)
        c = chord_at(a)
        voices = [m]
        if c is not None and m % 12 in four(c, m):
            pcs = four(c, m)
            cur = m
            while len(voices) < n:
                cur -= 1
                if cur % 12 in pcs:
                    voices.append(cur)
        else:
            sc = sorted({(G._root_pc(c) + i) % 12 for i in G._scale(c)}) \
                if c is not None else None
            cur = m
            while len(voices) < n:
                steps = 0
                while steps < 2:
                    cur -= 1
                    if sc is None or cur % 12 in sc:
                        steps += 1
                voices.append(cur)
        if style == 'drop2' and n >= 4:
            voices[1] -= 12
        voices.sort(reverse=True)
        p = voices[k] if k < len(voices) else voices[-1]
        if n >= 5 and k == n - 1 and c is not None and fold:
            # five voices or more: the bottom chair plays the root in its
            # own register, the big band's floor under the section
            p = G._near(G._root_pc(c), (fold[0] + fold[1]) // 2 - 5)
        if fold:
            q = p
            while p < fold[0]:
                p += 12
            while p > fold[1]:
                p -= 12
            if p != q and moved is not None:
                moved.append(a)
        tl.append((a, b, [p]))
    return dict(res, timeline=tl, staves=None, trills={}, trems={}, ks={},
                lyrics=None, lyrics_text=None)


def octave_words(n):
    """' an octave down', ' two octaves up', or '' — said after a part
    name, the way the double was asked for."""
    if not n:
        return ''
    count = {1: 'an octave', 2: 'two octaves', 3: 'three octaves'}.get(
        abs(n), f'{abs(n)} octaves')
    return f" {count} {'up' if n > 0 else 'down'}"


def shift_res(res, semis):
    """A resolved line moved by whole octaves: every pitch, plus the
    maps keyed on pitch (trills with their targets, tremolos,
    keyswitch marks) and any grand-staff voices. Rhythm, marks and
    words are untouched."""
    return map_res(res, lambda p: p + semis)


def map_res(res, f):
    """A resolved line with every pitch passed through f, the maps keyed
    on pitch and any grand-staff voices included."""
    def tl(line):
        return [(a, b, [f(p) for p in ps]) for a, b, ps in line]
    out = dict(res, timeline=tl(res.get('timeline') or []))
    if res.get('trills'):
        out['trills'] = {(q, f(p)): (f(aux),) + tuple(rest)
                         for (q, p), (aux, *rest) in res['trills'].items()}
    for k in ('trems', 'ks'):
        if res.get(k):
            out[k] = {(q, f(p)): v for (q, p), v in res[k].items()}
    if res.get('staves'):
        out['staves'] = [dict(st, voices=[tl(v) for v in st['voices']])
                         for st in res['staves']]
    return out


def demo_window(dm, ref, fig_meter, meters, shift, label, findings):
    """Where demo bars lo..hi live, in demo ticks — or None to let the
    single-meter arithmetic stand. The file's own time signatures are
    ground truth when present; otherwise the chart's meter map, translated
    by the count-in (the shared-grid assumption)."""
    lo, hi, loc = ref['lo'], ref['hi'], ref['loc']
    if dm.timesigs:
        for b in range(lo, hi + 1):
            dmet = dm.meter_of(b)
            if dmet != fig_meter:
                if len(meters) > 1:
                    fail(f"{loc}: demo bar {b} is in {dmet[0]}/{dmet[1]} "
                         f"but the figure lands in "
                         f"{fig_meter[0]}/{fig_meter[1]} — the demo and "
                         "the page must agree where a figure lands")
                findings.add(f"{label}: the demo is stamped "
                             f"{dmet[0]}/{dmet[1]} but the chart is in "
                             f"{fig_meter[0]}/{fig_meter[1]} — trusting "
                             "the chart; re-export the demo if this "
                             "sounds wrong")
                return None
        return (dm.bar_tick(lo), dm.bar_tick(hi + 1))
    if len(meters) == 1:
        return None
    # no time signatures in the file, but the chart mixes meters: locate
    # demo bars by the chart's own map, shifted by the count-in
    for b in range(lo, hi + 1):
        n, d = meter_at(meters, max(1, b - shift))
        if (n, d) != fig_meter:
            fail(f"{loc}: demo bar {b} sits in {n}/{d} on the shared "
                 f"grid but the figure lands in "
                 f"{fig_meter[0]}/{fig_meter[1]} — move the figure, or "
                 "re-export the demo with its meter map")

    def blen(b):
        n, d = meter_at(meters, max(1, b - shift))
        return dm.division * 4 * n // d
    lo_t = sum(blen(b) for b in range(1, lo))
    return (lo_t, lo_t + sum(blen(b) for b in range(lo, hi + 1)))


def build_plans(chart, band, groups, labels):
    """Resolve every part x section into a content plan. Shared by the
    compiler and the read-aloud part view, so the prose and the page can
    never disagree."""
    plans = []           # per section: {'start': bar, ...}
    start = 1
    for sec in chart['sections']:
        plan = {'sec': sec, 'start': start,
                'content': {l: ('default', None) for l in labels},
                'texts': {l: [] for l in labels},
                'dyns': {l: [] for l in labels},
                'wedges': {l: [] for l in labels},
                'overlays': {l: [] for l in labels},
                'lifts': {l: [] for l in labels},
                'enters': {},
                'doubles': {}, 'cues': {}, 'bg': {}, 'explode': {}}
        for target, instr, loc in sec['directives']:
            tgts = groups.get(target) or ([target] if target in labels else None)
            if tgts is None:
                fail(f"{loc}: '{target}' is not a band part or group")
            anns, engraved, groove_words = [], None, None
            solo_slashes = False
            bg_style = None
            explode_src = None
            soli_src = None
            demo_refs, fall, quant, short = [], False, None, False
            legato, ghost = False, False
            no_trills = False
            fig_lifts, lyrics_text = [], None
            doubles, cues, detail_word = None, None, None
            harm = 0
            every_artic, dyn_marks, scoops, doit = None, [], [], False
            wedge_marks = []
            hits_map = {}
            # split on commas OUTSIDE quotes — groove "shuffle, ride
            # heavy" is one piece, and the old error blamed the writer
            raw_pieces = [normalize_piece(p.strip())
                          for p in re.split(
                              r',(?=(?:[^"]*"[^"]*")*[^"]*$)', instr)]
            # 'hits on 1, 2+, 4' — the beat list is itself commas, so
            # bare beat tokens re-attach to a preceding hits piece
            pieces_merged = []
            for p in raw_pieces:
                if (pieces_merged
                        and pieces_merged[-1].startswith('hits')
                        and re.fullmatch(r'[\d.+]+|and-of-\d+', p)):
                    pieces_merged[-1] += ' ' + p
                else:
                    pieces_merged.append(p)
            for piece in pieces_merged:
                m = re.match(r'figure ([\w ]+?)(?:\s+at bar (\d+))?$',
                             piece)
                if m and m.group(1).strip() in chart['figures']:
                    fig = chart['figures'][m.group(1).strip()]
                    fig['used'] = True
                    at = start + int(m.group(2) or 1) - 1
                    if fig['kind'] == 'midi':
                        demo_refs.append({'track': fig['track'],
                                          'file': fig['file'],
                                          'lo': fig['lo'], 'hi': fig['hi'],
                                          'fig_lyrics': fig.get('lyrics'),
                                          'at': at, 'loc': loc})
                    elif fig['kind'] == 'inline':
                        demo_refs.append({'track': None, 'file': None,
                                          'inline': fig['items'],
                                          'grids': fig['grids'],
                                          'ticks': fig['ticks'],
                                          'fig_lyrics': fig.get('lyrics'),
                                          'lo': 1, 'hi': fig['bars'],
                                          'at': at, 'loc': loc})
                    else:
                        fig_lifts.append({'file': fig['file'],
                                          'part': fig['part'],
                                          'lo': fig['lo'], 'hi': fig['hi'],
                                          'at': at, 'loc': loc})
                    continue
                if m and piece.startswith('figure '):
                    fail(f"{loc}: figure '{m.group(1).strip()}' is not "
                         "defined")
                m = re.match(r'as engraved bars (\d+)(?:-(\d+))?'
                             r'(?:\s+at bars (\d+))?$', bar_words(piece))
                if m:
                    engraved = (int(m.group(1)),
                                int(m.group(2) or m.group(1)),
                                int(m.group(3) or 1))
                    continue
                m = re.match(r'from demo(?:\s+"([^"]+)")?'
                             r'\s+bars (\d+)(?:-(\d+))?'
                             r'(?:\s+at bars (\d+))?$', bar_words(piece))
                if m:
                    lo = int(m.group(2))
                    hi = int(m.group(3) or lo)
                    if hi < lo:
                        fail(f"{loc}: demo bars {lo}-{hi} run backwards")
                    # default placement: the demo and the chart share one
                    # grid, shifted by the demo's count-in bars, so demo
                    # bar N lands on printed bar N - countin unless an
                    # explicit `at bar` moves it
                    shift = int(chart['header'].get('countin', 0))
                    at = (start + int(m.group(4)) - 1) if m.group(4) \
                        else lo - shift
                    end = start + sec['bars'] - 1
                    if not m.group(4) and (at > end
                                           or at + hi - lo < start):
                        # written inside this section, so it's this
                        # section's line — never another section's
                        placed = (
                            f"{loc}: demo bars {lo}-{hi} would land on "
                            f"bars {at}-{at + hi - lo}, outside "
                            f"{sec['name']}; placed at its top (bar "
                            f"{start}) — say 'at bar N' to move it")
                        at = start
                    else:
                        placed = None
                    demo_refs.append({'track': m.group(1), 'lo': lo,
                                      'hi': hi, 'at': at, 'loc': loc,
                                      'placed': placed})
                    continue
                m = re.match(r'hits(?: bar (\d+))? on (.+)$', piece)
                if m:
                    beats = [parse_beat(t) for t in m.group(2).split()]
                    hits_map[int(m.group(1)) if m.group(1) else None] = \
                        beats
                    continue
                # "mute harmon", "harmon mute at bar 3", "open at bar 7":
                # either word order, anywhere in the section
                m = re.match(r'(?:mute (\w+)|(\w+) mute)'
                             r'(?:\s*-\s*([\w ]+?))?'
                             r'(?:\s+(?:at|from)\s+bar\s+(\d+))?$', piece)
                if m and (m.group(1) or m.group(2)) not in ('no',):
                    kind = m.group(1) or m.group(2)
                    extra = f' - {m.group(3)}' if m.group(3) else ''
                    anns.append((int(m.group(4) or 1),
                                 f'{kind} mute{extra}'))
                    continue
                m = re.match(r'(?:open|remove mute|mute off)'
                             r'\s+(?:at|from)\s+bar\s+(\d+)$', piece)
                if m:
                    anns.append((int(m.group(1)), 'open'))
                    continue
                # the bow: "arco at bar 9", "pizz at bar 17" — printed
                # the way string parts print them, and the listen
                # changes to the bowed or plucked take right there
                m = re.match(r'(arco|bowed|with the bow|takes the bow|'
                             r'pizz\.?|pizzicato|plucked|fingered)'
                             r'(?:\s+(?:at|from)\s+bar\s+(\d+))?$', piece)
                if m:
                    # "fingered" is the bass player's word for plucked
                    word = 'pizz.' if m.group(1).startswith(
                        ('pizz', 'pluck', 'finger')) else 'arco'
                    anns.append((int(m.group(2) or 1), word))
                    continue
                if piece == 'open':
                    anns.append((1, 'open'))
                    continue
                if piece == 'fall':
                    fall = True
                    continue
                if piece in ('eighths', 'straight eighths'):
                    quant = 'eighths'
                    continue
                if piece in ('straight', 'straight time'):
                    # onsets on the eighth grid, durations as played —
                    # how a shuffle or swing line is notated
                    quant = 'grid8'
                    continue
                if piece == 'quarters':
                    quant = 'quarters'
                    continue
                if piece == 'triplets':
                    quant = 'triplets'
                    continue
                if piece == 'eighth triplets':
                    quant = 'triplet8'
                    continue
                if piece == 'sixteenth triplets':
                    quant = 'triplet16'
                    continue
                if piece in ('sixteenths', 'straight sixteenths'):
                    quant = 'sixteenths'
                    continue
                if piece == 'short':
                    short = True
                    continue
                if piece in ('legato', 'slurred'):
                    legato = True
                    continue
                if piece in ('ghosts', 'ghost notes', 'ghosted'):
                    ghost = True
                    continue
                if piece in ('no trills', 'trills as played',
                             'no trill'):
                    # the writer's word: fast alternations here are
                    # written-out notes, not trills
                    no_trills = True
                    continue
                if piece in ('marcato', 'short and fat'):
                    every_artic = 'strong-accent'
                    continue
                if piece == 'staccato':
                    every_artic = 'staccato'
                    continue
                if piece == 'tenuto':
                    every_artic = 'tenuto'
                    continue
                if piece == 'accent':
                    every_artic = 'accent'
                    continue
                m = re.match(r'(cresc|dim)(?:\s+at bar (\d+))?$', piece)
                if m:
                    anns.append((int(m.group(2) or 1), m.group(1) + '.'))
                    continue
                m = re.match(r'(scoop|plop) (first|last)$', piece)
                if m:
                    scoops.append((m.group(1), m.group(2)))
                    continue
                m = re.match(r'(scoop|plop) bar (\d+) beat ([\d.]+)$', piece)
                if m:
                    scoops.append((m.group(1),
                                   (int(m.group(2)), float(m.group(3)))))
                    continue
                if piece == 'doit':
                    doit = True
                    continue
                m = re.match(r'dyn (?:(subito)\s+)?'
                             r'(pp|p|mp|mf|f|ff|sfz|fp)'
                             r'(?:\s+at bar (\d+))?'
                             r'(?:\s+beat (\S+))?$', piece)
                if m:
                    if m.group(4):
                        try:
                            beat = float(m.group(4))
                        except ValueError:
                            beat = parse_beat(m.group(4))
                    else:
                        beat = 1.0
                    dyn_marks.append((int(m.group(3) or 1), beat,
                                      m.group(2), bool(m.group(1))))
                    continue
                m = re.match(r'groove(?:\s+"([^"]*)")?$', piece)
                if m:
                    groove_words = m.group(1) or ''
                    continue
                m = re.match(r'lyrics "([^"]*)"$', piece)
                if m:
                    lyrics_text = m.group(1)
                    continue
                m = re.match(r'text "([^"]*)"(?:\s+at bar (\d+))?$', piece)
                if m:
                    anns.append((int(m.group(2) or 1), m.group(1)))
                    continue
                if piece == 'as demo':
                    groove_words = 'as demo'
                    continue
                if piece in ('simplified', 'rhythmic slashes',
                             'rhythmic-slashes', 'full'):
                    detail_word = piece.replace(' ', '-')
                    continue
                m = re.match(r'double ([\w ]+)$', piece)
                if m:
                    src, harm = harmony_phrase(m.group(1).strip())
                    doubles = (src, 0) if harm else \
                        octave_phrase(m.group(1).strip())
                    continue
                m = re.match(r'(?:soli|harmoni[sz]e)\s+(?:on\s+|under\s+)?'
                             r'(?:the\s+)?([\w ]+?)(?:,?\s+(close|drop 2|'
                             r'drop two))?$', piece)
                if m:
                    # the arranger's soli: one written lead, each chair a
                    # voice under it from the chord symbols
                    soli_src = (m.group(1).strip(),
                                'close' if m.group(2) == 'close' else
                                'drop2' if m.group(2) else None)
                    continue
                m = re.match(r'(?:explode|divisi|div\.?)\s+(?:from\s+)?'
                             r'(?:the\s+)?([\w ]+)$', piece)
                if m:
                    # MuseScore's and Sibelius's explode: one part's
                    # chords dealt out across the target's chairs
                    explode_src = (m.group(1).strip(), piece.startswith(
                        ('divisi', 'div')))
                    continue
                m = re.match(r'cue ([\w ]+)$', piece)
                if m:
                    cues = octave_phrase(m.group(1).strip())
                    continue
                m = re.match(r'on pass (\d+):\s*(.+)$', piece)
                if m:
                    if not sec['repeat']:
                        fail(f"{loc}: 'on pass' only means something in "
                             "a repeated section")
                    if int(m.group(1)) > max(sec['repeat'], 1):
                        fail(f"{loc}: 'on pass {m.group(1)}' in a section "
                             f"played {sec['repeat']} times")
                    tag = f"({m.group(1)}x only)"
                    inner = normalize_piece(m.group(2).strip())
                    mm = re.match(r'text "([^"]*)"(?:\s+at bar (\d+))?$',
                                  inner)
                    if mm:
                        anns.append((int(mm.group(2) or 1),
                                     f'{mm.group(1)} {tag}'))
                        continue
                    mm = re.match(r'mute (\w+)$', inner)
                    if mm:
                        anns.append((1, f'{mm.group(1)} mute {tag}'))
                        continue
                    if inner == 'open':
                        anns.append((1, f'open {tag}'))
                        continue
                    fail(f"{loc}: on pass carries words and mutes for "
                         "now — per-pass notes print once with a "
                         f"'{tag}' text")
                if piece == 'tacet':
                    engraved = 'tacet'
                    continue
                if piece in ('solo', 'solo open'):
                    anns.append((1, 'solos (open)' if 'open' in piece
                                 or sec['open'] else 'Solo'))
                    solo_slashes = True
                    continue
                m = re.fullmatch(r'backgrounds?(?:\s+(riffs?|pads?|'
                                 r'ad lib))?', piece)
                if m:
                    # backgrounds with no notes are made up on the spot,
                    # the way a jazz horn section does behind a solo
                    anns.append((1, 'backgrounds'))
                    bg_style = 'riff' if (m.group(1) or '').startswith(
                        'riff') else 'pads'
                    continue
                if piece == 'on cue':
                    if anns and anns[-1][1] == 'backgrounds':
                        anns[-1] = (anns[-1][0], 'backgrounds on cue')
                        bg_style = (bg_style or 'pads') + ' cue'
                    else:
                        anns.append((1, 'on cue'))
                    continue
                m = re.match(r'(cresc(?:endo)?|dim(?:inuendo)?|'
                             r'decresc(?:endo)?)\s+(?:from\s+)?'
                             r'bars?\s+(\d+)\s*(?:-|to)\s*'
                             r'(?:bar\s+)?(\d+)$', piece)
                if m:
                    # the hairpin the working books write on every page
                    wa, wb = int(m.group(2)), int(m.group(3))
                    if not 1 <= wa <= wb <= sec['bars']:
                        fail(f"{loc}: the hairpin runs bars {wa}-{wb} "
                             f"and {sec['name']} has {sec['bars']}")
                    wedge_marks.append(
                        ('crescendo' if piece.startswith('c')
                         else 'diminuendo', wa, wb))
                    continue
                if piece.startswith('notes:'):
                    # a writer's first instinct; the commas already split it
                    fail(f"{loc}: notes: goes in a figure, not on a part's "
                         f"line. Write 'figure NAME, N bars:' with "
                         f"'notes: ...' under it, then '{target}: figure "
                         f"NAME' here")
                fail(f"{loc}: instruction '{piece}' is not built yet")
            if soli_src:
                inst_of = {x['label']: canonical_instrument(
                    x['instrument']) for x in band}
                chairs = sorted(tgts, key=lambda c: -(
                    HORNS.get(inst_of.get(c), {}).get('comf',
                                                       (0, 0))[1]))
                lead_in = soli_src[0] in chairs
                others = [c for c in chairs if c != soli_src[0]]
                n_voices = len(others) + 1
                for k, c in enumerate(others, 1):
                    plan.setdefault('soli', {})[c] = (
                        soli_src[0], k, n_voices, soli_src[1], loc)
                if not lead_in and not others:
                    fail(f"{loc}: soli needs chairs to voice")
            if explode_src:
                # top voice to the highest-reaching chair, the next
                # down, and so on (MuseScore: a short chord doubles
                # evenly, or repeats its lowest note)
                inst_of = {x['label']: canonical_instrument(
                    x['instrument']) for x in band}
                chairs = sorted(tgts, key=lambda c: -(
                    HORNS.get(inst_of.get(c), {}).get('comf',
                                                       (0, 0))[1]))
                for k, c in enumerate(chairs):
                    plan['explode'][c] = (explode_src[0], k, len(chairs),
                                          explode_src[1], loc)
            for l in tgts:
                if doubles:
                    plan['doubles'][l] = doubles + (loc,)
                    plan.setdefault('harm', {})[l] = harm
                if cues:
                    plan['cues'][l] = cues + (loc,)
                if engraved == 'tacet':
                    plan['content'][l] = ('tacet', None)
                elif engraved:
                    plan['content'][l] = ('engraved', engraved)
                elif hits_map:
                    plan['content'][l] = ('hits',
                                          (hits_map, groove_words or ''))
                elif groove_words is not None:
                    plan['content'][l] = ('groove', groove_words)
                elif solo_slashes and plan['content'][l][0] == 'default':
                    # a soloist reads slashes under the changes, never
                    # empty bars — rests with chords over them look like
                    # unfinished engraving (Matthew's ruling, 2026-09-21)
                    plan['content'][l] = ('groove', '')
                if bg_style and not demo_refs and not fig_lifts \
                        and plan['content'][l][0] == 'default':
                    # made-up backgrounds read as slashes under the
                    # changes; written ones stay exactly as written
                    plan['content'][l] = ('groove', '')
                    plan['bg'][l] = bg_style
                for ref in demo_refs:
                    plan['overlays'][l].append(dict(ref, fall=fall,
                                                    quant=quant,
                                                    short=short,
                                                    legato=legato,
                                                    ghost=ghost,
                                                    no_trills=no_trills,
                                                    lyrics=lyrics_text,
                                                    detail=detail_word,
                                                    every=every_artic,
                                                    doit=doit,
                                                    scoops=scoops))
                plan['lifts'][l].extend(fig_lifts)
                plan['texts'][l].extend(anns)
                plan['dyns'][l].extend(dyn_marks)
                plan['wedges'][l].extend(wedge_marks)
        for bar, kind, text in sec['events']:
            if kind in ('meter', 'key', 'fermata'):
                continue    # signatures and holds are signs on the
                            # page, never words — emission handles them
            if kind == 'break':
                if text == 'first':
                    n = sum(1 for b, k, _t in sec['events']
                            if k == 'break' and b >= bar and
                            all((bb, 'break') in [(x, y) for x, y, _z in
                                                  sec['events']]
                                for bb in range(bar, b + 1)))
                    word = 'Break' + (f' ({n} bars)' if n > 1 else '')
                    for l in labels:
                        plan['texts'][l].append((bar, word))
                continue
            if kind == 'fill':
                word = 'Fill' + (f' from beat {text}' if text else '')
                for bb in band:
                    if canonical_instrument(bb['instrument']) == 'drums':
                        plan['texts'][bb['label']].append((bar, word))
                continue
            if kind == 'build' and text not in groups \
                    and text not in labels:
                fail(f"section {sec['name']}: build adds '{text}', which "
                     "is not a band part or group")
            for l in labels:
                if kind == 'tempo':
                    plan['texts'][l].append((bar, ('tempo', text)))
                elif kind == 'road':
                    plan['texts'][l].append((bar, ('road', text)))
                elif kind == 'build':
                    plan['texts'][l].append((bar, f"+{text}"))
                else:
                    plan['texts'][l].append((bar, text))
            if kind == 'build' and bar > 1:
                # "+bass at 5" means the bass is not playing before 5:
                # its slashes (and the listen's realized bass) start
                # there. Played or written material the writer placed
                # earlier still wins its bars — that is a stronger word.
                for t in groups.get(text) or [text]:
                    plan['enters'][t] = min(plan['enters'].get(t, bar),
                                            bar)
        plans.append(plan)
        start += sec['bars']
    return plans, start - 1


TRANSPOSE_XML = {
    2:   ('-1', '-2', None),     # Bb instruments
    7:   ('-4', '-7', None),     # F horn
    9:   ('-5', '-9', None),     # Eb alto
    12:  ('0', '0', '-1'),       # octave instruments (guitar, basses,
                                 # tenor voice)
    14:  ('-1', '-2', '-1'),     # Bb tenor, octave down
    21:  ('-5', '-9', '-1'),     # Eb baritone, octave down
    5:   ('-3', '-5', None),     # alto flute in G
    -3:  ('2', '3', None),       # Eb clarinet
    3:   ('-2', '-3', None),     # A clarinet
    -12: ('0', '0', '1'),        # piccolo, xylophone, celesta
    -24: ('0', '0', '2'),        # glockenspiel
}

CLEF_XML = {'G': '<sign>G</sign><line>2</line>',
            'F': '<sign>F</sign><line>4</line>',
            'C': '<sign>C</sign><line>3</line>',
            'percussion': '<sign>percussion</sign><line>2</line>'}

SOUND_DYN = {'pp': 40, 'p': 54, 'mp': 71, 'mf': 89, 'f': 106, 'ff': 123,
             'sfz': 112, 'fp': 98}


# What the listen may make up, each the writer's to turn off (chart
# settings, listen_*): set by the front door before a build.
TAKE = ''          # the listen's take; '' = the tune's own, fixed
LISTEN_OPTS = {'grooves': True, 'solos': True, 'backgrounds': True,
               'endings': True, 'mutes': True, 'brushes': True,
               'builds': True, 'feather': True}


_STEPS_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def bar_notes(xml, div, transpose=0):
    """One measure's pitched notes as [(start, end, midi)] in quarters
    from the bar's start, concert pitch (the written pitch less the
    part's transposition)."""
    out, pos, last = [], 0, 0
    for el in re.finditer(r'<(note|backup|forward|attributes)\b.*?</\1>',
                          xml, re.S):
        e, k = el.group(0), el.group(1)
        if k == 'attributes':
            d = re.search(r'<divisions>(\d+)', e)
            if d:
                div = int(d.group(1))
            continue
        du = re.search(r'<duration>(\d+)', e)
        dur = int(du.group(1)) if du else 0
        if k == 'backup':
            pos -= dur
            continue
        if k == 'forward':
            pos += dur
            continue
        if '<grace' in e:
            continue
        chorded = '<chord/>' in e
        st = last if chorded else pos
        m = re.search(r'<step>(\w)</step>(?:\s*<alter>(-?\d+)</alter>)?'
                      r'\s*<octave>(-?\d+)</octave>', e)
        if m:
            p = (12 * (int(m.group(3)) + 1) + _STEPS_PC[m.group(1)]
                 + int(m.group(2) or 0) - transpose)
            out.append((st / div, (st + dur) / div, p))
        if not chorded:
            last = pos
            pos += dur
    return out


def vamp_passes(sec):
    """How many times round an open section goes in the listen: about
    eight bars of it, two to four passes — and a take is a take: the
    cue comes a time sooner or later in the moment (Matthew,
    2026-09-30: "live in the moment")."""
    base = max(2, min(4, round(8 / max(sec['bars'], 1))))
    d = chartgroove._Dice(sec['name'], 'passes')
    r = d()
    return max(2, min(5, base + (-1 if r < 0.25 else 1 if r > 0.75
                                  else 0)))


# what each chair plays to cue the band out of a till-cue section
CUE_SOUND = {'drums': 'a fill into the next section',
             'comp': 'a run up the next chord',
             'bass': 'a walk up into the next root',
             'horn': 'a pickup into the downbeat',
             'voice': 'a sung pickup into the downbeat'}
_CUE_WORDS = {'drummer': 'drums', 'drum': 'drums', 'kit': 'drums',
              'singer': 'voice', 'vocalist': 'voice', 'vocals': 'voice',
              'vocal': 'voice', 'voice': 'voice'}
_LEADER = ('bandleader', 'band leader', 'leader', 'conductor', 'me',
           'director', 'md')


def road_cues(plans, band, labels, findings):
    """Who cues each till-cue section, and where each cut goes. A cue
    names a band part, an instrument, 'the drummer', 'the singer', or
    the bandleader (a nod, no sound). A cut names a section by its name
    or label, or lands on the nearest 'cut to here' mark that way."""
    def inst(l):
        return canonical_instrument(next(
            b for b in band if b['label'] == l)['instrument'])
    for i, pl in enumerate(plans):
        sec = pl['sec']
        who = (sec.get('cue_from') or '').lower()
        sec['_cuer'], sec['_cue_role'] = None, None
        if who and who not in _LEADER:
            want = _CUE_WORDS.get(who, who)
            hit = next((l for l in labels if l.lower() == who), None)
            if hit is None and want == 'drums':
                hit = next((l for l in labels if inst(l) == 'drums'), None)
            if hit is None and want == 'voice':
                hit = next((l for l in labels if 'voice' in (
                    (SOUNDS.get(inst(l)) or ('', ''))[1])), None)
            if hit is None:
                hit = next((l for l in labels
                            if inst(l) == canonical_instrument(who)), None)
            if hit is None:
                fail(f"section {sec['name']}: '{sec['cue_from']}' cues it, "
                     "but nobody in the band is called that — name a "
                     "part, 'the drummer', 'the singer' or the bandleader")
            sec['_cuer'] = hit
            sid = (SOUNDS.get(inst(hit)) or ('', ''))[1]
            h = HORNS.get(inst(hit)) or {}
            role = chartgroove.role_of(sid, h.get('clef', 'G'))
            sec['_cue_role'] = 'voice' if 'voice' in sid else (
                role if role in ('drums', 'comp', 'bass') else 'horn')
        elif sec.get('open') and not who:
            # nobody named: in the moment the drummer usually sets it up
            drum = next((l for l in labels if inst(l) == 'drums'), None)
            if drum and chartgroove._Dice(sec['name'], 'who cues')() < 0.6:
                sec['_cuer_quiet'] = drum
                sec['_cue_role'] = 'drums'
        sec['_cut'] = None
        if not sec.get('cut'):
            continue
        tgt = sec.get('cut_to')
        if tgt:
            j = next((k for k, q in enumerate(plans)
                      if q['sec']['name'].lower() == tgt.lower()
                      or (q['sec']['label'] or '').lower() == tgt.lower()),
                     None)
            if j is None:
                fail(f"section {sec['name']}: cut to '{tgt}', and no "
                     "section is called that")
            land = plans[j]['start']
            word = plans[j]['sec']['label'] or plans[j]['sec']['name']
        else:
            marks = [(q['start'] + b - 1) for q in plans
                     for b, k, _t in q['sec']['events'] if k == 'cutmark']
            here = pl['start']
            got = [m for m in marks if (m < here if sec['cut_back']
                                        else m > here + sec['bars'] - 1)]
            if not got:
                fail(f"section {sec['name']}: 'cut"
                     f"{' back' if sec['cut_back'] else ''}' with no "
                     "section named, and no 'at bar N: cut"
                     f"{' back' if sec['cut_back'] else ''} to here' "
                     "mark that way")
            land = max(got) if sec['cut_back'] else min(got)
            word = f"bar {land}"
        back = land < pl['start']
        sec['_cut'] = (land, word, back)
        said = (('On cue, ' if sec.get('open') else '')
                + ('back to ' if back else 'to ')
                + ('the coda' if word.lower() == 'coda' else word))
        said = said[0].upper() + said[1:]
        for l in labels:
            pl['texts'][l].append((sec['bars'], said))
        if findings is not None:
            findings.add(f"road map: after {sec['label'] or sec['name']}"
                         + (" (on the cue)" if sec.get('open') else "")
                         + f", the band cuts {'back ' if back else ''}to "
                         f"{word}" + (" once, then carries on" if back
                                      else ""))


def _inject_fermata(piece):
    """A fermata on this bar's last note or rest — the phrase-end
    hold every ballad page carries (Aria of the Soul, at every
    cadence)."""
    i = piece.rfind('</note>')
    if i < 0:
        return piece
    return piece[:i] + '<notations><fermata/></notations>' + piece[i:]


def _compile_rest(chart, band, groups, labels, plans, total,
                  source, src_of, chord_parts, hdr, chart_path, outdir,
                  demo_measures=None, horn_of=None, key=(0, 'major'),
                  findings=None, meter=(4, 4), div_marks=None):
    demo_measures = demo_measures or {l: {} for l in labels}
    div_marks = div_marks or {}
    # ---- the ending: words and a fermata on the pages, the whole
    # performance in the listen (chartending)
    import chartending
    # the take: a band never plays the same take twice. The CLI sets a
    # fresh one every build unless the writer keeps one (listen_take)
    chartgroove.SALT = hdr.get('title', '') + (f"#take{TAKE}" if TAKE
                                               else '')
    road_cues(plans, band, labels, findings)
    for pl in plans:
        if pl['sec'].get('open') and not pl['sec']['repeat']:
            said = 'vamp till cue' if pl['sec'].get('vamp') \
                else 'open, till cue'
            cuer = pl['sec'].get('_cuer')
            for l in labels:
                word = said + (' (you cue)' if l == cuer else
                               f' ({cuer} cues)' if cuer else '')
                if not any(t == (1, word) for t in pl['texts'][l]):
                    pl['texts'][l].append((1, word))
            if findings is not None:
                name = pl['sec']['label'] or pl['sec']['name']
                how = CUE_SOUND.get(pl['sec'].get('_cue_role'),
                                    'the band just goes on')
                if cuer:
                    cuer = ('drummer' if pl['sec']['_cue_role'] == 'drums'
                            else 'singer' if pl['sec']['_cue_role']
                            == 'voice' else cuer)
                findings.add(f"listen: {name} is open — this take it goes "
                             f"round {vamp_passes(pl['sec'])} times, till "
                             "the cue on the gig; "
                             + (f"the {cuer} cues it on the last time "
                                f"round ({how})" if cuer else
                                "nobody is named to cue it, so "
                                + ("the drummer sets it up"
                                   if pl['sec'].get('_cue_role') == 'drums'
                                   else "the band just goes on")))
    if TAKE and findings is not None:
        findings.add(f"listen: take {TAKE} — everything the band made up "
                     "is played fresh this build. To hear this take again, "
                     f"chart set listen_take={TAKE}; 'same' keeps one take "
                     "for every build")
    # a road map walks repeats itself: those stay repeats in the listen
    has_road = any(k == 'road' for pl in plans
                   for _b, k, _t in pl['sec']['events'])
    chartgroove.OPTS.update(builds=LISTEN_OPTS['builds'],
                            brushes=LISTEN_OPTS['brushes'],
                            feather=LISTEN_OPTS.get('feather', True))
    off_now = [k for k, v in LISTEN_OPTS.items() if not v]
    if off_now and findings is not None:
        findings.add("listen: turned off in settings, so the band leaves "
                     "them out — " + ", ".join(off_now))
    for i, pl in enumerate(plans):
        # where each section sits in the tune: the band builds across it
        pl['sec']['_arc'] = i / max(len(plans) - 1, 1)
    def written_ending(pl):
        """How the written parts end the tune: 'long' when one holds
        its last note half a bar or more, 'short' when they all end on
        short notes, None when nothing written plays the last bar."""
        last = pl['start'] + pl['sec']['bars'] - 1
        shape = None
        for l in labels:
            xml = demo_measures.get(l, {}).get(last)
            kind_, arg_ = pl['content'][l]
            if xml is None and kind_ == 'engraved' and source:
                lo_, hi_, at_ = arg_
                src = lo_ + (last - (pl['start'] + at_ - 1))
                if lo_ <= src <= hi_:
                    xml = source[src_of[l]]['measures'].get(str(src))
            if not xml or '<note' not in xml:
                continue
            dv = re.search(r'<divisions>(\d+)</divisions>', xml)
            durs = [int(x) for x in re.findall(
                r'<note(?:(?!</note>).)*?<pitch>(?:(?!</note>).)*?'
                r'<duration>(\d+)</duration>', xml, re.S)]
            if not durs:
                continue
            div_ = int(dv.group(1)) if dv else chartdemo.DIV
            n_, d_ = meter_at(chart.get('meters') or [(1, meter)], last)
            bar_len = div_ * 4 * n_ // d_
            if max(durs) * 2 >= bar_len or '<tie type="start"' in xml:
                return 'long'
            shape = 'short'
        return shape

    keys_l = next((b['label'] for b in band if canonical_instrument(
        b['instrument']) in ('piano', 'organ', 'keyboard', 'rhodes')),
        None)
    drums_l = next((b['label'] for b in band if canonical_instrument(
        b['instrument']) == 'drums'), None)
    for i, pl in enumerate(plans):
        got = pl['sec'].get('ending')
        auto = False
        if not got and i == len(plans) - 1 and LISTEN_OPTS['endings']:
            # the roadmap says nothing: the band decides in the moment,
            # from the feel, its own call in every tune — the listen
            # only; the pages keep what the roadmap wrote
            got, auto = ("band's choice", f"section {pl['sec']['name']}"), \
                True
        if not got:
            continue
        etext, eloc = got
        if i != len(plans) - 1:
            fail(f"{eloc}: an ending goes on the last section — "
                 f"'{pl['sec']['name']}' is not the last")
        try:
            steps = chartending.parse(etext, labels, groups)
        except chartending.EndingError as e:
            fail(f"{eloc}: {e}")
        if [k for k, _ in steps] == ['asis']:
            continue                    # the notes stop where they stop
        song = (hdr.get('title', ''), pl['sec']['name'])
        if any(k == 'choice' for k, _ in steps):
            chosen = chartending.band_choice(
                pl['sec']['feel'] or hdr.get('feel') or '', song,
                keys_l is not None, bool(groups.get('horns')),
                written_ending(pl), has_drums=drums_l is not None)
            pl['_written_end'] = written_ending(pl)
            j = next(n for n, (k, _) in enumerate(steps) if k == 'choice')
            have = {k for k, _ in steps}
            # what the roadmap already says stands; the band fills in
            # the rest, never contradicting it
            if have & {'stop', 'hit', 'button'}:
                chosen = [c for c in chosen
                          if c[0] not in ('stop', 'hit', 'button')]
            chosen = [c for c in chosen if c[0] not in have]
            steps = steps[:j] + chosen + steps[j + 1:]
        sh = chartending.shape(steps, labels, groups)
        if sh.get('dictate'):
            if drums_l is None:
                fail(f"{eloc}: a drummer-dictated ending needs a drum "
                     "chair in the band")
            who_d, text_d = sh['dictate']
            if text_d:
                sh['dictate_chords'] = [bar[0][1] for bar in
                                        parse_bars(text_d, eloc)
                                        if bar and bar[0][1]]
            else:
                # the band's call: bVI13(#11), V13(b9), IV13(#11),
                # V7(#9,b13) home to the last chord — the Last Surprise
                # shape, in this tune's key
                last_c = next((c for bar in reversed(pl['sec']['content'])
                               for _b, c in reversed(bar) if c), None)
                tpc = chartgroove._root_pc(last_c) if last_c else 0
                nm = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A',
                      'Bb', 'B']
                sh['dictate_chords'] = [bar[0][1] for bar in parse_bars(
                    f"{nm[(tpc + 8) % 12]}13#11, {nm[(tpc + 7) % 12]}13b9, "
                    f"{nm[(tpc + 5) % 12]}13#11, {nm[(tpc + 7) % 12]}7#9b13",
                    eloc)]
        # who voices a band chord, top down: the melodic chairs by the
        # top of their range
        sh['voices'] = sorted(
            [(l, (horn_of.get(l) or {}).get('comf', (55, 79))[0],
              (horn_of.get(l) or {}).get('comf', (55, 79))[1])
             for l in labels if l not in groups.get('rhythm', ())
             and horn_of.get(l) and horn_of[l].get('clef') != 'percussion'],
            key=lambda x: -x[2])
        sh['inst'] = {b['label']: canonical_instrument(b['instrument'])
                      for b in band}
        # who soloed: they're the ones who blow over a held last chord
        sh['soloists'] = sorted({l for p_ in plans for l in labels
                                 if any(isinstance(t[1], str) and
                                        t[1].lower().startswith('solo')
                                        for t in p_['texts'].get(l, ()))})
        if sh.get('cadenza') == 'lead':
            # 'cadenza' with nobody named: the top voice on the stand
            sh['cadenza'] = sh['voices'][0][0] if sh['voices'] else None
        sh['keys'] = keys_l
        sh['auto'] = auto
        sh['song'] = song
        pl['ending'] = sh
        nb = pl['sec']['bars']
        said = chartending.words(steps)
        if auto:
            if sh['rit']:
                pl.setdefault('listen_words', []).append(
                    (max(1, nb - 1), 'rit.'))
            if findings is not None:
                why = {'long': ", holding with the written parts' "
                              "long last note",
                       'short': ", stopping with the written parts' short "
                                "last notes"}.get(pl.get('_written_end'), '')
                findings.add("listen: the roadmap names no ending, so the "
                             f"band chose one: {said}{why}. Write 'ending:' "
                             "on the last section to decide it yourself")
            continue
        players = [l for l in labels
                   if pl['content'][l][0] not in ('tacet', 'default')
                   or pl['overlays'].get(l)
                   or (pl['content'][l][0] == 'default'
                       and l in groups['rhythm'])]
        players += [l for l in sh['noodle'] + sh['fill'] + sh['gliss']
                    + ([sh['cadenza']] if sh.get('cadenza') else [])
                    if l and l not in players]
        if sh.get('dictate'):
            players = list(labels)          # everyone is in the show
        for l in set(players) | {labels[0]}:
            if said:
                pl['texts'][l].append((nb, said))
            if sh['rit']:
                pl['texts'][l].append((max(1, nb - 1), 'rit.'))
            if sh['fade']:
                pl['texts'][l].append((max(1, nb - 3), 'fade out'))
        if sh['held'] and not any(b == nb and k == 'fermata'
                                  for b, k, _ in pl['sec']['events']):
            pl['sec']['events'].append((nb, 'fermata', ''))
        if findings is not None:
            findings.add("ending: " + (said or etext) + " — the listen "
                         "plays it; the pages say it over the last bar")
    horn_of = horn_of or {}
    realized_bars = {}          # label -> listening bars the band realized
    meters = chart.get('meters') or [(1, meter)]
    keys_map = chart.get('keys') or [(1, (0, 'major'))]
    m_num, m_den = meter_at(meters, 1)

    # ---- where each section sits in the source. The page may print
    # slashes where the source writes the player's real notes: the
    # listen plays what is written, and realizes from the chords only
    # where the source has nothing (Matthew, 2026-09-28: "keep the
    # slashes, I'm just saying extra notes was being played"). A
    # section is placed by any part lifted whole from the source; one
    # with none (an open solo) by the sections either side, only when
    # the gap is exactly its length.
    sec_src = [None] * len(plans)
    for i, pl in enumerate(plans):
        for kind_, arg_ in pl['content'].values():
            if kind_ == 'engraved' and isinstance(arg_, tuple) and \
                    arg_[2] == 1 and arg_[1] - arg_[0] + 1 == \
                    pl['sec']['bars']:
                sec_src[i] = arg_[0]
                break
    i = 0
    while i < len(plans):
        if sec_src[i] is not None:
            i += 1
            continue
        j = i
        while j < len(plans) and sec_src[j] is None:
            j += 1
        if i > 0 and j < len(plans):
            at = sec_src[i - 1] + plans[i - 1]['sec']['bars']
            if at + sum(plans[k]['sec']['bars'] for k in range(i, j)) \
                    == sec_src[j]:
                for k in range(i, j):
                    sec_src[k] = at
                    at += plans[k]['sec']['bars']
        i = j
    played_written = {}

    def written_notes(sp_, lo, hi):
        """Does the source give this player real notes in these bars
        — not rests, not slashes?"""
        for n in range(lo, hi + 1):
            m = sp_['measures'].get(str(n), '')
            for note in re.findall(r'<note\b.*?</note>', m, re.S):
                if '<rest' not in note and \
                        not re.search(r'<notehead[^>]*>slash', note):
                    return True
        return False

    # ---- backgrounds made up on the spot, in the listen
    def bg_bar(clef, staves, fifths, sec, off, absbar, bmeter, div, horn,
               label, state, governing, plan):
        """The horns on backgrounds voice the chords together, top horn
        on top: held pads, or a riff every horn plays; 'on cue' waits
        for the second half (Matthew, 2026-09-29: backgrounds can
        happen on the spot, like in jazz, or be written)."""
        style = plan['bg'][label]
        if 'cue' in style and off < sec['bars'] // 2:
            return None
        busy = sec.get('_busy')
        if busy is not None and busy > 0.55:
            return None      # the soloist is talking: the horns wait
        if any(k == 'break' and b == off + 1 for b, k, _t in sec['events']):
            return None      # a break: everyone out but the soloist
        who = [x['label'] for x in band if plan['bg'].get(x['label'])]
        who.sort(key=lambda l: -(horn_of.get(l) or {}).get(
            'comf', (0, 70))[1])
        k = who.index(label)
        bar = chartgroove.Bar(div, bmeter, fifths, staves,
                              shift=horn['transpose'] if horn else 0)
        chords = chartgroove._chords_in(sec, off, governing)
        lo, hi = horn['comf'] if horn else (55, 79)
        chartgroove.backgrounds(bar, state, chords, k, len(who), lo, hi,
                                'riff' if style.startswith('riff')
                                else 'pads', off, sec['name'])
        return bar.xml()

    # ---- where the band is inside a soloist's turn, for dynamics
    def soloists(plan):
        """Who solos in this section, in the order the chart calls them
        (a band leader's 'tenor, then trumpet'); anyone soloing without
        a line of their own follows in band order."""
        who = [x['label'] for x in band if any(
            isinstance(t[1], str) and t[1].lower().startswith('solo')
            for t in plan['texts'].get(x['label'], ()))]
        order = []
        for tgt, ins, _l in plan['sec'].get('directives', ()):
            if ins.strip().lower().startswith('solo'):
                for l in groups.get(tgt) or [tgt]:
                    if l in who and l not in order:
                        order.append(l)
        return order + [l for l in who if l not in order]

    def solo_turn(sec, off, cur_pass, passes, plan):
        """(bar in the current soloist's turn, turn length) or None
        when nobody solos here."""
        who = soloists(plan)
        if not who or not LISTEN_OPTS['solos']:
            return None
        walk = sec['bars'] * passes
        each = max(walk // len(who), 1)
        at = cur_pass * sec['bars'] + off
        k = min(at // each, len(who) - 1)
        length = walk - k * each if k == len(who) - 1 else each
        return (at - k * each, length, k)

    def solo_busy(sec, plan, passes, bar_beats):
        """How busy the soloist is in this bar, 0 (resting) to 1 (a
        solid line of eighths), so the band can leave room or answer."""
        turn = sec.get('_turn')
        if not turn:
            return None
        who = soloists(plan)
        walk = sec['bars'] * passes
        story = solo_story(who[turn[2]], sec, who, walk, bar_beats)
        t0, t1 = turn[0] * bar_beats, (turn[0] + 1) * bar_beats
        n = sum(1 for at, *_r in story if t0 <= at < t1)
        return min(n / (2.0 * bar_beats), 1.0)

    def solo_answer(sec, plan, passes, bar_beats):
        """The soloist's last phrase, when they breathe in this bar:
        its rhythm as beats in the bar (up to four notes), so the piano
        or the drummer can pick it up and answer (Matthew, 2026-09-30:
        "if someone plays something during their solo, anyone should be
        able to pick that phrase up in some kind of way and react")."""
        turn = sec.get('_turn')
        if not turn or turn[0] == 0:
            return None
        who = soloists(plan)
        walk = sec['bars'] * passes
        story = solo_story(who[turn[2]], sec, who, walk, bar_beats)
        t0 = turn[0] * bar_beats
        now = [n for n in story if t0 <= n[0] < t0 + bar_beats]
        prev = [n for n in story if t0 - bar_beats <= n[0] < t0]
        if len(now) > 2 or len(prev) < 2:
            return None             # still talking, or nothing to answer
        tail = prev[-4:]
        return [round(n[0] - (t0 - bar_beats), 3) for n in tail]

    # ---- a mute nobody wrote: the brass's own call on made-up parts
    def band_mute(label, sec, kind):
        """'harmon mute', 'cup mute', 'plunger mute' or None: what a
        brass player reaches for on a solo or backgrounds when the chart
        leaves it to them (Matthew, 2026-09-29: "same goes for mutes ...
        from the roadmap or on the spot"). A mute the chart names always
        wins; the choice comes from the tune, the same every build."""
        if not LISTEN_OPTS['mutes']:
            return None
        inst = canonical_instrument(next(
            x['instrument'] for x in band if x['label'] == label))
        if inst not in ('trumpet', 'c trumpet', 'cornet', 'trombone',
                        'bass trombone'):
            return None
        for pl in plans:
            if pl['sec'] is sec and any(
                    isinstance(t[1], str) and re.search(
                        r'mute|con sord|open', t[1], re.I)
                    for t in pl['texts'].get(label, ())):
                return None
        feel = (sec['feel'] or hdr.get('feel') or '').lower()
        style, traits = chartgroove.style_of(feel)
        if style in ('funk', 'latin', 'samba', 'straight', 'motown',
                     'hiphop', 'reggae', 'secondline'):
            return None
        soft = 'ballad' in traits or 'ballad' in feel
        bluesy = style == 'shuffle' or 'blues' in feel
        # a section's backgrounds all go into the same mute together
        d = chartgroove._Dice(hdr.get('title', ''), sec['name'], kind,
                              label if kind == 'solo' else 'section')
        r = d()
        if kind == 'bg':
            return 'cup mute' if soft and r < 0.55 else None
        if 'trombone' in inst:
            if bluesy and r < 0.35:
                return 'plunger mute'
            return 'cup mute' if soft and r < 0.3 else None
        if soft:
            return 'harmon mute' if r < 0.45 else \
                'cup mute' if r < 0.6 else None
        return 'harmon mute' if r < 0.18 else None

    # ---- each soloist's whole solo, planned once, heard by the next
    stories = {}
    personas = {}

    def solo_story(label, sec, who, walk, bar_beats):
        """A soloist's planned solo over its share of the section. The
        soloist after it hears how it ended: a line spilling over the
        barline, or the last phrase to answer."""
        k = who.index(label)
        key = (sec['name'], label, walk)
        if key in stories:
            return stories[key]
        each = max(walk // max(len(who), 1), 1)
        lo_bar = k * each
        hi_bar = walk if k == len(who) - 1 else lo_bar + each
        b = next(x for x in band if x['label'] == label)
        inst = canonical_instrument(b['instrument'])
        h = HORNS.get(inst) or {}
        snd = SOUNDS.get(inst)
        sid = snd[1] if snd else ''
        role = chartgroove.role_of(sid, h.get('clef', 'G'))
        if role == 'bass':
            lo, hi = 36, 62
        elif role == 'comp':
            lo, hi = (55, 79) if 'guitar' in sid else (62, 86)
        elif h:
            lo, hi = h['comf']
            lo = max(lo, h['fold'][0])
        else:
            lo, hi = 55, 79
        per_bar, carry = [], None
        for w in range(0, walk):
            o = w % sec['bars']
            got = [(bb, c) for bb, c in sec['content'][o] if c is not None]
            if (not got or got[0][0] > 1.0) and carry is not None:
                got = [(1.0, carry)] + got
            if got:
                carry = got[-1][1]
            per_bar.append(got)

        def chord_fn(t, base=lo_bar):
            i = min(max(int(t // bar_beats) + base, 0), len(per_bar) - 1)
            beat_in = t - (i - base) * bar_beats + 1
            if not per_bar[i]:
                return carry
            c = per_bar[i][0][1]
            for bb, cc in per_bar[i]:
                if bb <= beat_in + 1e-6:
                    c = cc
            return c
        if 'voice' in sid:
            voice = 'voice'
        elif role == 'bass':
            voice = 'bass'
        elif role == 'comp':
            # a vibes or marimba player blows single lines with two
            # mallets, never a pianist's run with a left hand under it
            voice = 'guitar' if 'guitar' in sid else 'mallets' if \
                sid.startswith('pitched-percussion') else 'keys'
        else:
            voice = 'horn'
        echo, after = None, 0.0
        if k > 0:
            prev = solo_story(who[k - 1], sec, who, walk, bar_beats)
            prev_total = each * bar_beats
            over = [n for n in prev if n[0] >= prev_total - 1e-6]
            if over:
                after = max(n[0] + n[1] for n in over) - prev_total + 0.5
            echo = chartgroove.last_phrase(prev, prev_total)
        feel = sec['feel'] or hdr.get('feel') or ''
        # each soloist is their own player; the next one contrasts the
        # one before
        seed = (hdr.get('title', ''), label, sec['name'], lo_bar)
        pd = chartgroove._Dice(seed, 'persona')
        persona = chartgroove.PERSONAS[int(pd() * 4) % 4]
        if k > 0 and persona == personas.get((sec['name'], who[k - 1])):
            persona = chartgroove.PERSONAS[
                (chartgroove.PERSONAS.index(persona) + 1) % 4]
        personas[(sec['name'], label)] = persona
        # the roadmap's breaks inside this soloist's turn: the band stops,
        # the soloist carries it alone
        brk_bars = {b for b, kk, _t in sec['events'] if kk == 'break'}
        breaks = []
        for w in range(lo_bar, hi_bar):
            if (w % sec['bars']) + 1 in brk_bars:
                q0 = (w - lo_bar) * bar_beats
                if breaks and abs(breaks[-1][1] - q0) < 1e-6:
                    breaks[-1] = (breaks[-1][0], q0 + bar_beats)
                else:
                    breaks.append((q0, q0 + bar_beats))
        plan_ = chartgroove.plan_solo(
            chord_fn, hi_bar - lo_bar, bar_beats, lo, hi, feel,
            seed, voice, echo=echo, start_after=after,
            next_soloist=k < len(who) - 1, persona=persona,
            breaks=breaks)
        stories[key] = plan_
        return plan_

    # ---- a soloist's bar in the listen
    def solo_bar(sound_id, clef, staves, fifths, sec, off, absbar, bmeter,
                 div, horn, label, state, governing, plan, cur_pass=0,
                 passes=1):
        """The page says solo and nothing was played in: the soloist
        plays over the changes, in the listen only (Matthew,
        2026-09-29). A drummer takes a drum solo; a pianist keeps
        left-hand shells under the line."""
        chartgroove.LEAD_NOW = None       # the soloist IS the lead
        role = chartgroove.role_of(sound_id, clef)
        bar = chartgroove.Bar(div, bmeter, fifths, staves,
                              shift=horn['transpose'] if horn else 0)
        feel = sec['feel'] or hdr.get('feel') or ''
        # soloists named together take turns, in the chart's order, the
        # section split between them (a real band never blows at once)
        who = soloists(plan)
        k = who.index(label) if label in who else 0
        walk = sec['bars'] * passes         # a vamp's bars, every pass
        at = cur_pass * sec['bars'] + off
        absbar = absbar + 1000 * cur_pass   # a new pass, new notes
        each = max(walk // max(len(who), 1), 1)
        lo_bar = k * each
        hi_bar = walk if k == len(who) - 1 else lo_bar + each
        spill = at >= hi_bar and at < hi_bar + 2 and role not in (
            'drums', 'perc')
        if not lo_bar <= at < hi_bar and not spill:
            return None
        pos, total = at - lo_bar, hi_bar - lo_bar
        if role == 'drums':
            chartgroove.drum_solo(bar, absbar, pos, total, label)
            return bar.xml()
        if role == 'perc':
            return chartgroove.realize('groove', '', sound_id, clef,
                                       staves, fifths, sec, off, absbar,
                                       bmeter, div, feel, state,
                                       governing)
        chords = chartgroove._chords_in(sec, off, governing)
        nxt = None
        if off + 1 < sec['bars']:
            nxt = next((c for _b, c in sec['content'][off + 1]
                        if c is not None), None)
        if role == 'bass':
            lo, hi = 36, 62
        elif role == 'comp':
            lo, hi = (55, 79) if 'guitar' in sound_id else (62, 86)
        elif horn:
            lo, hi = horn['comf']
            lo = max(lo, horn['fold'][0])
        else:
            lo, hi = 55, 79
        # the whole solo is planned before its first note, so it can
        # tell a story over the changes it will actually meet, and it
        # hears the soloist before it
        bar_beats = bmeter[0]
        story = solo_story(label, sec, who, walk, bar_beats)
        chartgroove.play_planned(bar, story, pos, bar_beats)
        if role == 'comp' and sound_id.startswith('keyboard'):
            # a pianist or organist keeps shells under the line; vibes,
            # marimba and guitar play the line alone (Matthew,
            # 2026-09-30: "vibes play lines, not chords")
            chartgroove.comp_shells(bar, state, chords, absbar, nxt)
        return bar.xml()

    def ensemble_hits(entries, bmeter):
        """The section's written hits in a bar: onsets where two or more
        horns or voices strike together, with the longest note there and
        the air before the next hit."""
        by = {}
        for l_, s_, e_, _m in entries:
            if l_ in groups['rhythm']:
                continue
            k_ = round(s_ * 12) / 12
            got = by.setdefault(k_, [set(), 0.0, 0])
            got[0].add(l_)
            got[1] = max(got[1], e_ - s_)
            got[2] = max(got[2], _m)
        ons = sorted(k for k, v in by.items() if len(v[0]) >= 2)
        if not ons:
            return None
        end = bmeter[0] * 4 / bmeter[1]
        out = []
        for i_, k in enumerate(ons):
            nxt = ons[i_ + 1] if i_ + 1 < len(ons) else end
            out.append((k, by[k][1], max(nxt - (k + by[k][1]), 0.0),
                        by[k][2]))
        return out

    def next_chord(pi_):
        """The first chord of whatever the band plays next: the cut's
        landing, else the next section."""
        sec_ = plans[pi_]['sec']
        nxt = None
        if sec_.get('_cut'):
            nxt = next((q for q in plans
                        if q['start'] == sec_['_cut'][0]), None)
        elif pi_ + 1 < len(plans):
            nxt = plans[pi_ + 1]
        if nxt is None:
            return None
        for row in nxt['sec']['content']:
            for _b, c in row:
                if c is not None:
                    return c
        return None

    def cue_range(label):
        b_ = next(x for x in band if x['label'] == label)
        h_ = HORNS.get(canonical_instrument(b_['instrument'])) or {}
        if h_.get('comf'):
            return max(h_['comf'][0], h_['fold'][0]), h_['comf'][1]
        return 55, 79

    # ---- the lead, heard by the band: a first pass collects it. The
    # first keyboard comping is the one the other chord players (a
    # guitar beside a piano) voice around, as they would on the stand.
    LEAD = {'collect': None, 'map': None, 'compers': set(),
            'hears_comp': set()}

    # ---- who comps: one chord player at a time unless the chart says
    sid_of = {}
    for bb in band:
        _s = SOUNDS.get(canonical_instrument(bb['instrument']))
        sid_of[bb['label']] = _s[1] if _s else ''
    strolled = {}
    _chordy = [l for l in groups['rhythm']
               if sid_of.get(l, '').startswith(('keyboard', 'pluck.guitar',
                                                  'pitched-percussion'))]
    _keys = [l for l in _chordy if sid_of[l].startswith('keyboard')]
    if _keys:
        LEAD['compers'] = {_keys[0]}
        LEAD['hears_comp'] = set(_chordy) - {_keys[0]}

    def strolls(label, plan):
        """A mallet player the chart didn't give anything to, in a
        section where a keyboard or guitar is comping too."""
        if not sid_of.get(label, '').startswith('pitched-percussion'):
            return False
        for other in groups['rhythm']:
            if other == label or not sid_of.get(other, '').startswith(
                    ('keyboard', 'pluck.guitar')):
                continue
            k_ = plan['content'][other][0]
            if k_ in ('default', 'groove'):
                return True
        return False

    # ---- emit one part's measures
    def part_measures(label, with_directions, with_harmony, listen=False,
                      part_mode=False):
        b = next(x for x in band if x['label'] == label)
        default_groove = label in groups['rhythm']
        sp = source[src_of[label]] if source else None
        horn = horn_of.get(label)
        div = sp['div'] if sp else chartdemo.DIV
        grand = bool(horn and horn.get('grand')) and sp is None
        staves = sp['staves'] if sp else (2 if grand else 1)
        clef = sp['clef'] if sp else (horn['clef'] if horn else 'G')
        fifths = sp['fifths'] if sp else (
            key[0] + written_foff(horn['foff'], key[0]) if horn
            else key[0])
        governing = [None]      # printed-chord state, carried across bars
        out = []
        # the listening document's rhythm section: what this chair
        # plays when the page says slashes (Matthew's ruling, 2026-09-20)
        _snd = SOUNDS.get(canonical_instrument(b['instrument']))
        sound_id = _snd[1] if _snd else ''
        my_role = chartgroove.role_of(sound_id, clef)
        groove_state = {}
        active_chord = [None]   # harmony carried bar to bar, all parts

        def attributes():
            tr = ''
            if horn and horn['transpose'] in TRANSPOSE_XML:
                d, c, o = TRANSPOSE_XML[horn['transpose']]
                # a respelled written key (Ab for G#) sits one letter
                # further from concert: the diatonic step follows it
                moved = written_foff(horn['foff'], key[0]) - horn['foff']
                if moved and not sp:
                    d = str(int(d) + (-1 if moved < 0 else 1))
                tr = (f'<transpose><diatonic>{d}</diatonic>'
                      f'<chromatic>{c}</chromatic>'
                      + (f'<octave-change>{o}</octave-change>' if o else '')
                      + '</transpose>')
            keyxml = ('' if clef == 'percussion' else
                      f'        <key><fifths>{fifths}</fifths>'
                      f'<mode>{key[1]}</mode></key>\n')
            if grand:
                # a keyboard-family part prints on the grand staff
                clefxml = ('        <staves>2</staves>\n'
                           f'        <clef number="1">{CLEF_XML["G"]}'
                           '</clef>\n'
                           f'        <clef number="2">{CLEF_XML["F"]}'
                           '</clef>\n')
            else:
                clefxml = (f'        <clef>'
                           f'{CLEF_XML[clef if clef in CLEF_XML else "G"]}'
                           '</clef>\n')
            return ('      <attributes>\n'
                    f'        <divisions>{div}</divisions>\n'
                    + keyxml +
                    f'        <time><beats>{m_num}</beats>'
                    f'<beat-type>{m_den}</beat-type></time>\n'
                    + clefxml
                    + ('' if clef == 'percussion' else
                       (f'        {tr}\n' if tr else ''))
                    + '      </attributes>\n')

        pk = chart['pickup']
        if pk:
            content = ''
            # the source's pickup bar: numbered 0 by most programs, but
            # some number it 1 and call it implicit — then it is simply
            # the first bar
            pk_num = '0' if sp and '0' in sp['measures'] else (
                next(iter(sp['measures']), None) if sp else None)
            if pk['engraved'] and sp and pk_num is not None:
                content = strip_lifted(sp['measures'][pk_num],
                                       clef == 'percussion')
            if with_directions:
                if hdr.get('feel'):
                    content = direction(hdr['feel'].capitalize()) + content
                for t in pk['texts']:
                    content = direction(t, 'below') + content
            out.append((f'    <measure implicit="yes" number="0">\n{content}'
                        '    </measure>\n', False, False))

        need_attrs = source is None
        was_groove = False
        was_swing = (False, False)
        was_feelk = None                # laid back / loose / on top
        cur_div = div
        resume_div = None
        fine_div = None
        marks = div_marks.get(label, {})
        for pi_, plan in enumerate(plans):
            sec = plan['sec']
            kind, arg = plan['content'][label]
            if kind == 'default':
                kind = 'groove' if default_groove else 'tacet'
                arg = '' if kind == 'groove' else None
                if listen and kind == 'groove' and strolls(label, plan):
                    # two chord players comping at once muddy the
                    # changes: unasked, the vibes stroll while the
                    # piano or guitar comps (Matthew, 2026-09-30)
                    kind, arg = 'tacet', None
                    strolled.setdefault(label, []).append(
                        sec['label'] or sec['name'])
            lo_ = sec_src[pi_]
            if listen and kind == 'groove' and sp and lo_ is not None \
                    and written_notes(sp, lo_, lo_ + sec['bars'] - 1):
                kind, arg = 'engraved', (lo_, lo_ + sec['bars'] - 1, 1)
                played_written.setdefault(label, []).append(sec['name'])
            # an open section vamps: the page shows it once between
            # repeat signs, the listen writes it out a few times round
            # so a soloist over it keeps going instead of looping
            passes = vamp_passes(sec) if listen and sec.get('open') and \
                not sec['repeat'] else 1
            # a repeated solo section is written out in the listen, so
            # the solo tells one story across every chorus instead of
            # the same chorus three times
            solo_rep = listen and sec['repeat'] and not \
                sec.get('endings') and any(
                    isinstance(t[1], str) and t[1].lower().startswith(
                        'solo') for ll in labels
                    for t in plan['texts'].get(ll, ()))
            # any repeated section the band makes up is written out too,
            # so a head played twice isn't comped twice the same way
            band_rep = listen and sec['repeat'] and not \
                sec.get('endings') and not has_road and not any(
                    plan['content'][ll][0] == 'engraved'
                    for ll in labels) and any(
                    plan['content'][ll][0] in ('groove', 'hits')
                    or (plan['content'][ll][0] == 'default'
                        and ll in groups['rhythm'])
                    for ll in labels)
            solo_rep = solo_rep or band_rep
            if solo_rep:
                passes = max(sec['repeat'], 1)
            for off, cur_pass in [(o, k) for k in range(passes)
                                  for o in range(sec['bars'])]:
                absbar = plan['start'] + off
                bmeter = meter_at(meters, absbar)
                pieces = []
                bar_div0 = cur_div
                if listen and off == sec['bars'] - 1 and \
                        cur_pass == passes - 1 and sec.get('open') and \
                        not sec['repeat'] and sec.get('_cue_role') == \
                        'drums' and label in (sec.get('_cuer'),
                                              sec.get('_cuer_quiet')):
                    groove_state['cue_fill'] = True
                # what the lead plays in this bar, heard by whoever is
                # making something up under it (not by the lead itself)
                # the bass walks through its approach notes and the
                # drums have no pitch: only chord players and horns
                # making something up voice around the lead
                chartgroove.LEAD_NOW = [
                    (s_, e_, m_) for l_, s_, e_, m_ in LEAD['map'].get(
                        str(absbar if not cur_pass
                            else f'{absbar}x{cur_pass}'), ())
                    if l_ != label and (l_ not in LEAD['compers']
                                        or label in LEAD['hears_comp'])
                ] if listen and LEAD['map'] and my_role not in (
                    'bass', 'drums', 'perc') else None
                chartgroove.ENSEMBLE_NOW = ensemble_hits(
                    LEAD['map'].get(str(absbar if not cur_pass
                                        else f'{absbar}x{cur_pass}'), ()),
                    bmeter) if listen and LEAD['map'] and \
                    my_role == 'drums' else None
                resumed = None
                if resume_div is not None:
                    # the bar after a realized one goes back to the
                    # part's own divisions
                    if resume_div != cur_div:
                        resumed = ('      <attributes><divisions>'
                                   f'{resume_div}</divisions>'
                                   '</attributes>\n')
                        pieces.append(resumed)
                        fine_div = cur_div
                        cur_div = resume_div
                    resume_div = None
                if absbar in marks:
                    want_div = marks[absbar] or div
                    if want_div != cur_div:
                        pieces.append('      <attributes><divisions>'
                                      f'{want_div}</divisions>'
                                      '</attributes>\n')
                        cur_div = want_div
                if need_attrs:
                    pieces.append(attributes())
                    need_attrs = False
                elif absbar > 1 and bmeter != meter_at(meters, absbar - 1):
                    # the meter changes here: every part restates the time
                    # signature, and a bar that shows one is never allowed
                    # to hide inside a multirest
                    pieces.append('      <attributes><time>'
                                  f'<beats>{bmeter[0]}</beats>'
                                  f'<beat-type>{bmeter[1]}</beat-type>'
                                  '</time></attributes>\n')
                if not need_attrs and absbar > 1 and clef != 'percussion' \
                        and key_at(keys_map, absbar) != \
                        key_at(keys_map, absbar - 1):
                    # the key changes here: every pitched part restates
                    # its own written signature — concert fifths plus
                    # the horn's offset, the same sum as bar one
                    kf, kmode = key_at(keys_map, absbar)
                    pieces.append('      <attributes><key>'
                                  f'<fifths>{kf + (written_foff(horn["foff"], kf) if horn else 0)}'
                                  '</fifths>'
                                  f'<mode>{kmode}</mode></key>'
                                  '</attributes>\n')
                # slashes are instructions, not pitches: mute the part's
                # playback through a groove region, restore after (the
                # dynamics="0" note attribute alone is ignored by
                # MuseScore's importer — measured, not assumed)
                if off == 0 and kind == 'groove' and not was_groove:
                    # not in the listening document: its groove bars are
                    # real rests already, and a part playing demo bars in
                    # a groove section must not have its notes muted —
                    # chartaudio honors dynamics, unlike MuseScore
                    if not listen:
                        pieces.append('      <direction>'
                                      '<sound dynamics="0"/></direction>\n')
                    was_groove = True
                elif off == 0 and kind != 'groove' and was_groove:
                    if not listen:
                        pieces.append('      <direction>'
                                      '<sound dynamics="80"/></direction>\n')
                    was_groove = False
                if listen and off == 0:
                    feel_now = (sec['feel'] or hdr.get('feel')
                                or '').lower()
                    # swing playback, measured 2026-09-20: MuseScore's
                    # MusicXML importer computes its swing ratio as
                    # second/first x 100 (backwards from the spec), so
                    # 3:2 here lands its offbeats at 0.658 — triplet
                    # feel. Only the listening document carries this;
                    # the page says "Swing" in words, and no other
                    # importer ever sees the inverted encoding.
                    # a swing feel by any name — "two feel", "ballad",
                    # "double time" — swings; "straight" said outright wins
                    style_now, traits_now = chartgroove.style_of(feel_now)
                    swung_funk = style_now == 'funk' and \
                        'swung' in traits_now
                    want = (not (bmeter[1] == 8 and bmeter[0] % 3 == 0)
                            and (swung_funk
                                 or ((any(w in feel_now
                                          for w in ('swing', 'shuffle'))
                                      and style_now not in ('straight',
                                                            'funk'))
                                     or style_now in ('swing', 'shuffle')
                                     or (style_now in ('waltz', 'hiphop')
                                         and 'swung' in traits_now))))
                    # "Swing 16ths" swings the half-beat — the 8-Bit
                    # book's groove — and a flip between units re-emits.
                    # Swung funk swings its sixteenths, which in half
                    # time ARE the written eighths
                    unit16 = want and ('16' in feel_now
                                       or 'sixteen' in feel_now
                                       or ((swung_funk
                                            or style_now == 'hiphop')
                                           and 'half' not in traits_now
                                           and not re.search(
                                               r'\b8ths?\b|eighth',
                                               feel_now)))
                    # the swing ratio real trios use at this tempo (the
                    # Jazz Trio Database): wider slow, flatter fast —
                    # a flat triplet at every tempo was stiff at medium
                    # and bouncy up-tempo. The pages never see it.
                    try:
                        bpm_now = float(hdr.get('tempo', 140))
                    except (TypeError, ValueError):
                        bpm_now = 140.0
                    if unit16:
                        bpm_now *= 2          # sixteenths swing like fast
                    swing_first = int(round(
                        100 * chartgroove.swing_ratio(bpm_now)))
                    if style_now == 'shuffle':
                        swing_first = 200     # a shuffle is triplets
                    if (want, unit16) != was_swing:
                        # spec-correct MusicXML (first:second = 2:1 is
                        # triplet swing): only chartaudio plays this
                        # document now, and it reads the spec. The
                        # hidden words keep the direction valid.
                        pieces.append(
                            '      <direction><direction-type>'
                            '<words print-object="no">'
                            + ('Swing' if want else 'Straight')
                            + '</words></direction-type><sound><swing>'
                            + (f'<first>{swing_first}</first>'
                               '<second>100</second>'
                               '<swing-type>'
                               + ('16th' if unit16 else 'eighth')
                               + '</swing-type>'
                               if want else '<straight/>')
                            + '</swing></sound></direction>\n')
                        was_swing = (want, unit16)
                    # where the band sits against the time: the section's
                    # own feel words, or back to tight when it says none
                    import chartaudio as _ca
                    fk = _ca.feel_word(feel_now)
                    for _t in plan['texts'].get(label, ()):
                        if _t[0] == 1 and isinstance(_t[1], str):
                            fk = _ca.feel_word(_t[1]) or fk
                    if fk != was_feelk and (fk or was_feelk):
                        word = {'back': 'laid back', 'loose': 'loose',
                                'push': 'on top', 'tight': 'tight'}.get(
                            fk, 'tight')
                        pieces.append(
                            '      <direction><direction-type>'
                            f'<words print-object="no">{word}</words>'
                            '</direction-type></direction>\n')
                        was_feelk = fk
                if with_directions and absbar == 1 and not chart['pickup']:
                    if hdr.get('feel'):
                        pieces.append(direction(hdr['feel'].capitalize()))
                    if hdr.get('tempo') and not re.fullmatch(
                            r'[\d.]+', str(hdr['tempo'])):
                        # tempo words are performance language, printed
                        # verbatim (Lush Life says "Slow, freely")
                        pieces.append(direction(hdr['tempo']))
                    elif hdr.get('tempo'):
                        # a compound meter's tempo is a dotted-quarter
                        # figure — that is how a 6/8 player reads it
                        compound = m_den == 8 and m_num % 3 == 0
                        dot = '<beat-unit-dot/>' if compound else ''
                        sound = (float(hdr['tempo']) * 1.5 if compound
                                 else float(hdr['tempo']))
                        pieces.append(
                            '      <direction placement="above">'
                            '<direction-type><metronome>'
                            f'<beat-unit>quarter</beat-unit>{dot}'
                            f'<per-minute>{hdr["tempo"]}</per-minute>'
                            '</metronome></direction-type>'
                            f'<sound tempo="{sound:g}"/>'
                            '</direction>\n')
                if with_directions and off == 0:
                    mark = sec['name']
                    if re.fullmatch(r'[A-Z]\d*|\d+', mark):
                        pieces.append(rehearsal(mark))
                    else:
                        # word marks box too, shouted the way a book
                        # prints INTRO — 'intro' was silently losing
                        # its box (found on Victory, 2026-09-22)
                        pieces.append(rehearsal(mark.upper()))
                    if sec['label']:
                        pieces.append(direction(sec['label']))
                    if sec['feel']:
                        pieces.append(direction(sec['feel']))
                    if kind == 'groove' and arg:
                        pieces.append(direction(arg))
                    if kind == 'hits' and arg[1]:
                        pieces.append(direction(arg[1]))
                # the section's own words ride the top staff only; a
                # player's technique (arco, pizz., a mute) belongs to that
                # player in the score and the listen alike — the bass's
                # arco was reaching neither (Bow Ballad, 2026-09-28)
                if listen and with_directions:
                    # the band's own calls (a rit. nobody wrote) reach
                    # the listen, never the page
                    for tbar, text in plan.get('listen_words', ()):
                        if tbar == off + 1:
                            pieces.append(direction(text))
                for tbar, text in sorted(plan['texts'][label],
                                         key=lambda t: t[0]):
                    if tbar != off + 1:
                        continue
                    if not (with_directions
                            or (isinstance(text, str)
                                and TECHNIQUE_RE.match(text))):
                        continue
                    if isinstance(text, tuple) and text[0] == 'road':
                        pieces.append(road_direction(text[1]))
                        continue
                    if isinstance(text, tuple) and text[0] == 'tempo':
                        # in a compound bar the mark is a dotted
                        # quarter, and it sounds half again as fast —
                        # the same convention the header tempo keeps
                        bcompound = (bmeter[1] == 8
                                     and bmeter[0] % 3 == 0)
                        bdot = '<beat-unit-dot/>' if bcompound else ''
                        bsound = (float(text[1]) * 1.5 if bcompound
                                  else float(text[1]))
                        pieces.append(
                            '      <direction placement="above">'
                            '<direction-type><metronome>'
                            f'<beat-unit>quarter</beat-unit>{bdot}'
                            f'<per-minute>{text[1]}</per-minute>'
                            '</metronome></direction-type>'
                            f'<sound tempo="{bsound:g}"/>'
                            '</direction>\n')
                    else:
                        pieces.append(direction(text, 'above'))
                for wtype, wa, wb in plan.get('wedges', {}).get(label, ()):
                    if wa == off + 1:
                        pieces.append(
                            '      <direction placement="below">'
                            '<direction-type><wedge type="'
                            + wtype + '"/></direction-type>'
                            '</direction>\n')
                for dbar, dbeat, mark, sub in plan.get('dyns',
                                                       {}).get(label, ()):
                    if dbar == off + 1:
                        doff = int(round((dbeat - 1.0) * div))
                        if sub:
                            pieces.append(
                                '      <direction placement="below">'
                                '<direction-type><words>subito</words>'
                                '</direction-type>'
                                + (f'<offset>{doff}</offset>'
                                   if doff else '')
                                + '</direction>\n')
                        pieces.append(
                            '      <direction placement="below">'
                            '<direction-type><dynamics>'
                            f'<{mark}/></dynamics></direction-type>'
                            + (f'<offset>{doff}</offset>' if doff else '')
                            + f'<sound dynamics="{SOUND_DYN[mark]}"/>'
                            '</direction>\n')
                waiting = (kind in ('groove', 'hits')
                           and off + 1 < plan['enters'].get(label, 0)
                           and absbar not in demo_measures[label])
                soloing = any(isinstance(t[1], str)
                              and t[1].lower().startswith('solo')
                              for t in plan['texts'][label])
                silent = (kind == 'tacet' and not soloing
                          and absbar not in demo_measures[label])
                if waiting or silent:
                    # a player waiting to come in, or sitting a section
                    # out, reads one multirest, not changes over empty
                    # bars — and where they play again the chord is
                    # restated
                    governing[0] = None
                elif with_harmony and clef != 'percussion' and (
                        label in chord_parts
                        or plan.get('bg', {}).get(label) or any(
                            isinstance(t[1], str) and
                            t[1].lower().startswith('solo') for t in
                            plan['texts'][label])):
                    for beat, chord in sec['content'][off]:
                        if chord is None:
                            continue
                        if chord != governing[0] or off == 0:
                            pc = chord
                            if horn and not listen:
                                pc = transpose_chord(
                                    pc, horn['transpose'],
                                    written_foff(
                                        horn['foff'],
                                        key_at(keys_map, absbar)[0]))
                            pieces.append(harmony_xml(
                                pc, beat, div * 4 // bmeter[1]))
                        governing[0] = chord
                if absbar in demo_measures[label]:
                    pieces.append(demo_measures[label][absbar])
                elif waiting:
                    pieces.append(rest_bar(div, staves, bmeter))
                elif kind == 'engraved':
                    lo, hi, at = arg
                    idx = absbar - (plan['start'] + at - 1)
                    srcbar = lo + idx
                    if 0 <= idx <= hi - lo:
                        if str(srcbar) not in sp['measures']:
                            fail(f"{label}: source has no bar {srcbar}")
                        pieces.append(strip_lifted(sp['measures'][str(srcbar)],
                                                   clef == 'percussion'))
                    else:
                        pieces.append(rest_bar(div, staves, bmeter))
                elif kind == 'hits':
                    hmap, _gw = arg
                    pattern = hmap.get(off + 1, hmap.get(None))
                    if listen:
                        # a groove needs sixteenths and triplets:
                        # 24 a quarter at least, whatever the lifted
                        # score's own divisions (2 in Matt's Blues put
                        # the funk bass's pickups on the next note)
                        gdiv = cur_div if cur_div % 24 == 0 else 24
                        if resumed in pieces and fine_div == gdiv:
                            # still realizing: no back-and-forth
                            pieces.remove(resumed)
                            resume_div = cur_div
                            cur_div = gdiv
                        elif gdiv != cur_div:
                            pieces.append('      <attributes><divisions>'
                                          f'{gdiv}</divisions>'
                                          '</attributes>\n')
                            resume_div = cur_div
                            cur_div = gdiv
                        made = None if not LISTEN_OPTS['grooves'] else \
                            chartgroove.realize(
                            'hits', arg, sound_id, clef, staves,
                            fifths, sec, off, absbar + 1000 * cur_pass, bmeter, gdiv,
                            sec['feel'] or hdr.get('feel') or '',
                            groove_state, active_chord[0],
                            written_shift=horn['transpose']
                            if horn else 0)
                        pieces.append(made or rest_bar(cur_div, staves,
                                                       bmeter))
                        if made:
                            realized_bars[label] = \
                                realized_bars.get(label, 0) + 1
                    elif pattern:
                        pieces.append(hits_bar(pattern, div, clef,
                                               staves, fifths, bmeter))
                    else:
                        pieces.append(slash_bar(div, clef, staves,
                                                fifths, bmeter))
                elif kind == 'groove':
                    # MuseScore's importer plays slash noteheads no matter
                    # what (dynamics="0", cue, sound directions and
                    # unpitched all measured audible), so the listening
                    # variant used to render groove regions as real
                    # rests. Now it renders what the slashes MEAN: the
                    # realized rhythm section, listening document only.
                    if listen:
                        # a groove needs sixteenths and triplets:
                        # 24 a quarter at least, whatever the lifted
                        # score's own divisions (2 in Matt's Blues put
                        # the funk bass's pickups on the next note)
                        gdiv = cur_div if cur_div % 24 == 0 else 24
                        if resumed in pieces and fine_div == gdiv:
                            # still realizing: no back-and-forth
                            pieces.remove(resumed)
                            resume_div = cur_div
                            cur_div = gdiv
                        elif gdiv != cur_div:
                            pieces.append('      <attributes><divisions>'
                                          f'{gdiv}</divisions>'
                                          '</attributes>\n')
                            resume_div = cur_div
                            cur_div = gdiv
                        sec['_turn'] = solo_turn(sec, off, cur_pass,
                                                 passes, plan)
                        sec['_busy'] = solo_busy(sec, plan, passes,
                                                 bmeter[0])
                        sec['_answer'] = solo_answer(sec, plan, passes,
                                                     bmeter[0])
                        if soloing and not LISTEN_OPTS['solos'] or \
                                plan.get('bg', {}).get(label) and \
                                not soloing and \
                                not LISTEN_OPTS['backgrounds'] or \
                                not soloing and \
                                not plan.get('bg', {}).get(label) and \
                                not LISTEN_OPTS['grooves']:
                            made = None     # the writer turned it off
                        elif plan.get('bg', {}).get(label) and \
                                not soloing:
                            made = bg_bar(clef, staves, fifths, sec, off,
                                          absbar, bmeter, gdiv, horn,
                                          label, groove_state,
                                          active_chord[0], plan)
                        elif soloing:
                            made = solo_bar(
                                sound_id, clef, staves, fifths, sec,
                                off, absbar, bmeter, gdiv, horn, label,
                                groove_state, active_chord[0], plan,
                                cur_pass, passes)
                        else:
                            made = chartgroove.realize(
                                'groove', arg, sound_id, clef, staves,
                                fifths, sec, off, absbar + 1000 * cur_pass, bmeter, gdiv,
                                sec['feel'] or hdr.get('feel') or '',
                                groove_state, active_chord[0],
                                written_shift=horn['transpose']
                                if horn else 0)
                        bgs = plan.get('bg', {}).get(label)
                        if (soloing or bgs) and off == 0 and \
                                cur_pass == 0:
                            mw = band_mute(label, sec,
                                           'bg' if bgs and not soloing
                                           else 'solo')
                            groove_state['muted'] = mw
                            if mw:
                                pieces.append(direction(mw))
                            if soloing and chartgroove.role_of(
                                    sound_id, clef) in ('comp', 'bass'):
                                pieces.append(direction('solo'))
                                groove_state['leading'] = True
                        impl = groove_state.get('impl')
                        if impl and impl != groove_state.get('impl_said'):
                            # the listen hears what's in the drummer's
                            # hands: brushes pick up the brush kit
                            pieces.append(direction(impl))
                            groove_state['impl_said'] = impl
                        pieces.append(made or rest_bar(cur_div, staves,
                                                       bmeter))
                        if groove_state.get('leading') and \
                                off == sec['bars'] - 1 and \
                                cur_pass == passes - 1:
                            pieces.append(direction('comp'))
                            groove_state['leading'] = False
                        if groove_state.get('muted') and \
                                off == sec['bars'] - 1 and \
                                cur_pass == passes - 1:
                            # the mute comes out for whatever is next
                            pieces.append(direction('open'))
                            groove_state['muted'] = None
                        if made:
                            realized_bars[label] = \
                                realized_bars.get(label, 0) + 1
                    else:
                        pieces.append(slash_bar(div, clef, staves,
                                                fifths, bmeter))
                else:
                    pieces.append(rest_bar(div, staves, bmeter))
                for _cb, _cc in sec['content'][off]:
                    if _cc is not None:
                        active_chord[0] = _cc

                barline = ''
                open_bl = ''
                ends = sec.get('endings') or []
                vamp_page = sec.get('open') and not sec['repeat'] \
                    and not listen
                if ((sec['repeat'] and not solo_rep) or vamp_page) \
                        and off == 0 and cur_pass == 0:
                    open_bl = ('      <barline location="left">'
                               '<bar-style>heavy-light</bar-style>'
                               '<repeat direction="forward"/></barline>\n')
                if ends:
                    # volta brackets: each ending but the last closes
                    # with a backward repeat; the last discontinues and
                    # carries the section's closing bar
                    body = sec['body']
                    elen = ends[0]['bars']
                    k = (off - body) // elen + 1 if off >= body else 0
                    if k >= 1 and (off - body) % elen == 0:
                        open_bl += ('      <barline location="left">'
                                    f'<ending number="{k}" type="start"/>'
                                    '</barline>\n')
                    if k >= 1 and (off - body) % elen == elen - 1:
                        if k < len(ends):
                            barline = ('      <barline location="right">'
                                       f'<ending number="{k}" '
                                       'type="stop"/>'
                                       '<repeat direction="backward"/>'
                                       '</barline>\n')
                        else:
                            style = ('light-heavy' if plan is plans[-1]
                                     else 'light-light')
                            barline = ('      <barline location="right">'
                                       f'<bar-style>{style}</bar-style>'
                                       f'<ending number="{k}" '
                                       'type="discontinue"/></barline>\n')
                elif sec['repeat'] and not solo_rep and \
                        off == sec['bars'] - 1:
                    barline = ('      <barline location="right">'
                               '<bar-style>light-heavy</bar-style>'
                               f'<repeat direction="backward" '
                               f'times="{sec["repeat"]}"/></barline>\n')
                elif vamp_page and off == sec['bars'] - 1:
                    # an open vamp: round again until the cue
                    barline = ('      <barline location="right">'
                               '<bar-style>light-heavy</bar-style>'
                               '<repeat direction="backward"/>'
                               '</barline>\n')
                elif off == sec['bars'] - 1 and cur_pass < passes - 1:
                    barline = ''                # the vamp goes round
                elif off == sec['bars'] - 1:
                    # every section closes with a double bar; the last
                    # section closes the chart with a final bar
                    style = ('light-heavy' if plan is plans[-1]
                             else 'light-light')
                    barline = ('      <barline location="right">'
                               f'<bar-style>{style}</bar-style>'
                               '</barline>\n')
                # a right-hand barline may close a multirest; a repeat
                # start may not hide inside one
                if any(b == off + 1 and k == 'fermata'
                       for b, k, _ in sec['events']):
                    for pi in range(len(pieces) - 1, -1, -1):
                        if '</note>' in pieces[pi]:
                            pieces[pi] = _inject_fermata(pieces[pi])
                            break
                for wtype, wa, wb in plan.get('wedges', {}).get(label, ()):
                    if wb == off + 1:
                        pieces.append(
                            '      <direction placement="below">'
                            '<direction-type><wedge type="stop"/>'
                            '</direction-type></direction>\n')
                pure_rest = (len(pieces) == 1 and not open_bl
                             and '<repeat' not in barline
                             and (pieces[0] == rest_bar(div, staves,
                                                        bmeter)
                                  or lifted_rest(pieces[0])))
                head_ok = (not pure_rest and not open_bl
                           and '<repeat' not in barline
                           and any(p == rest_bar(div, staves, bmeter)
                                   or lifted_rest(p) for p in pieces)
                           and all(p == rest_bar(div, staves, bmeter)
                                   or lifted_rest(p)
                                   or p.lstrip().startswith(
                                       ('<direction', '<attributes'))
                                   for p in pieces))
                last_time = (listen and off == sec['bars'] - 1
                             and cur_pass == passes - 1)
                if last_time and sec.get('_cut'):
                    # where the band cuts to: the listen walks it
                    pieces.append('      <direction><direction-type>'
                                  '<words print-object="no">copyist cut '
                                  f'{sec["_cut"][0]}</words>'
                                  '</direction-type></direction>\n')
                if last_time and sec.get('open') and not sec['repeat'] \
                        and label == sec.get('_cuer') \
                        and sec.get('_cue_role') != 'drums':
                    cue = chartgroove.cue_bar(
                        sec['_cue_role'], cur_div, bmeter, fifths, staves,
                        horn['transpose'] if horn else 0,
                        active_chord[0], next_chord(pi_),
                        *(cue_range(label)), (hdr.get('title', ''),
                                              label, absbar))
                    at_ = max((k_ for k_, p_ in enumerate(pieces)
                               if '<note' in p_), default=None)
                    if cue and at_ is not None:
                        pieces[at_] = cue
                    elif cue:
                        pieces.append(cue)
                mnum = absbar if not cur_pass else f'{absbar}x{cur_pass}'
                if listen and LEAD['collect'] is not None and (
                        absbar in demo_measures[label]
                        or kind == 'engraved' or soloing
                        or label in LEAD['compers']):
                    # the lead in this bar: a written line, a lifted
                    # part, the soloist — what the others listen to
                    LEAD['collect'].setdefault(str(mnum), []).extend(
                        (label,) + n for n in bar_notes(
                            "".join(pieces), bar_div0,
                            horn['transpose'] if horn else 0))
                out.append((f'    <measure number="{mnum}">\n' + open_bl +
                            "".join(pieces) + barline + '    </measure>\n',
                            pure_rest, head_ok))

        # ---- the ending, in the listen: the last bar held, whatever
        # plays over it, and the hit on the cue
        endsh = plans[-1].get('ending') if plans else None
        if listen and endsh and out:
            last_pl = plans[-1]
            last_abs = last_pl['start'] + last_pl['sec']['bars'] - 1
            kind_l = last_pl['content'][label][0]
            realized = (kind_l in ('groove', 'hits')
                        or (kind_l == 'default' and default_groove)) \
                and last_abs not in demo_measures[label] \
                and not last_pl['overlays'].get(label) \
                and last_pl['sec']['name'] not in played_written.get(
                    label, ())
            xml0 = out[-1][0]
            # the band's own call never rewrites a written ending: only
            # the chairs that were making it up end it their way
            got = None if (endsh.get('auto') and not realized) else \
                chartending.listen_bars(
                    xml0, chartgroove.role_of(sound_id, clef), sound_id,
                    active_chord[0], meter_at(meters, last_abs),
                    horn['transpose'] if horn else 0, fifths, staves,
                    endsh, label, not realized, label,
                    song=endsh.get('song', ''))
            if got:
                body, extras = got
                bl = re.search(r'<barline location="right">.*?</barline>\n?',
                               xml0, re.S)
                bl = bl.group(0) if bl else ''
                if body is not None:
                    head = re.match(r'\s*<measure number="[^"]+">\n',
                                    xml0)
                    keep = re.findall(r'      <direction.*?</direction>\n',
                                      xml0, re.S)
                    out[-1] = (head.group(0) + ''.join(keep) + body
                               + ('' if extras else bl)
                               + '    </measure>\n', False, False)
                elif extras and bl:
                    out[-1] = (out[-1][0].replace(bl, ''), False, False)
                for k, ex in enumerate(extras, 1):
                    # the ending's own bars are not the chart's bars:
                    # named so the listen never counts them as printed
                    out.append((f'    <measure number="{last_abs}e{k}">\n'
                                + ex + (bl if k == len(extras) else '')
                                + '    </measure>\n', False, False))

        # ---- multirests, parts only: a stretch of waiting prints as one
        # bar carrying its count. Runs break naturally at anything a
        # player must see — marks, texts, dynamics, double bars — because
        # those bars are not pure rests.
        if part_mode:
            i = 0
            while i < len(out):
                if out[i][1] or out[i][2]:
                    # a run may START on a rest bar that carries only
                    # directions — the mark and the words ride above
                    # the count, the way a working book groups an
                    # intro as 4 — but only PURE bars extend it
                    j = i
                    while (j + 1 < len(out) and out[j + 1][1]
                           and '<barline' not in out[j][0]):
                        j += 1
                    n = j - i + 1
                    if n >= 2:
                        content = out[i][0]
                        # before the bar's first note, whatever its
                        # attributes (a lifted <note default-x=...>)
                        content = re.sub(
                            r'(\s*)<note[ >]',
                            lambda m_: (m_.group(1)
                                        + '<attributes><measure-style>'
                                        f'<multiple-rest>{n}'
                                        '</multiple-rest></measure-style>'
                                        '</attributes>' + m_.group(0)),
                            content, count=1)
                        out[i] = (content, True, False)
                    i = j + 1
                else:
                    i += 1
        return "".join(t[0] for t in out)

    # ---- whole documents
    def document(part_labels, directions_on, harmony_on, listen=False,
                 part_mode=False):
        L = [XMLHEAD, '<score-partwise version="3.1">\n',
             '  <work>'
             + ('<work-number>%s</work-number>' % hdr['number']
                if hdr.get('number') else '')
             + '<work-title>%s</work-title></work>\n' %
             hdr.get('title', 'Untitled'),
             '  <identification>']
        if hdr.get('composer'):
            L.append('<creator type="composer">%s</creator>' % hdr['composer'])
        if hdr.get('arranger'):
            L.append('<creator type="arranger">%s</creator>' % hdr['arranger'])
        if hdr.get('lyricist'):
            L.append('<creator type="lyricist">%s</creator>'
                     % hdr['lyricist'])
        if hdr.get('rev'):
            L.append('<creator type="revision">%s</creator>'
                     % hdr['rev'])
        if hdr.get('from'):
            L.append('<source>%s</source>' % hdr['from'])
        L.append('<encoding><software>Copyist chartc</software></encoding>'
                 '</identification>\n')
        L.append('  <part-list>\n')
        for i, l in enumerate(part_labels, 1):
            name = src_of.get(l, l)
            inst = canonical_instrument(next(
                x for x in band if x['label'] == l)['instrument'])
            sound = SOUNDS.get(inst)
            L.append(f'    <score-part id="P{i}">'
                     f'<part-name>{name}</part-name>')
            if sound:
                iname, sid, prog = sound
                # channel 10 is percussion's — every unpitched
                # instrument takes it, no one else touches it
                perc = HORNS.get(inst, {}).get('clef') == 'percussion'
                chan = 10 if perc else (i if i < 10 else i + 1)
                L.append(f'<score-instrument id="P{i}-I1">'
                         f'<instrument-name>{iname}</instrument-name>'
                         f'<instrument-sound>{sid}</instrument-sound>'
                         f'</score-instrument>'
                         f'<midi-instrument id="P{i}-I1">'
                         f'<midi-channel>{chan}</midi-channel>'
                         f'<midi-program>{prog}</midi-program>'
                         f'</midi-instrument>')
            L.append('</score-part>\n')
        L.append('  </part-list>\n')
        for i, l in enumerate(part_labels, 1):
            L.append(f'  <part id="P{i}">\n')
            L.append(part_measures(l, directions_on(l), harmony_on(l),
                                   listen, part_mode))
            L.append('  </part>\n')
        L.append('</score-partwise>\n')
        return "".join(L)

    os.makedirs(outdir, exist_ok=True)
    # a title can hold a slash ("Take A Brake / What's Going On"); a
    # file name cannot
    title = re.sub(r'\s*[/\\:]\s*', ' - ', hdr.get('title', 'chart'))
    score_path = os.path.join(outdir, f'{title} — score.musicxml')
    with open(score_path, 'w', encoding='utf-8') as f:
        f.write(document(labels,
                         directions_on=lambda l: l == labels[0],
                         harmony_on=lambda l: l in chord_parts))
    written = [score_path]
    listen_path = os.path.join(outdir, f'{title} — for listening.musicxml')
    # two passes: the first only learns what the lead plays in every
    # bar; the second is the band, each chair hearing it
    import copy as _copy
    kept = _copy.deepcopy((realized_bars, played_written, strolled))
    LEAD['collect'] = {}
    document(labels, directions_on=lambda l: l == labels[0],
             harmony_on=lambda l: l in chord_parts, listen=True)
    LEAD['map'], LEAD['collect'] = LEAD['collect'], None
    for live, was in zip((realized_bars, played_written, strolled), kept):
        live.clear()
        live.update(was)
    with open(listen_path, 'w', encoding='utf-8') as f:
        f.write(document(labels,
                         directions_on=lambda l: l == labels[0],
                         harmony_on=lambda l: l in chord_parts,
                         listen=True))
    chartgroove.LEAD_NOW = None
    chartgroove.ENSEMBLE_NOW = None
    written.append(listen_path)
    # written in the chart or lifted from a score, a road map is read
    # back in bar numbers
    road_said = say_road(listen_path)
    if road_said:
        findings.add(road_said)
    for l, secs in strolled.items():
        findings.add(f"listen: {l} leaves the comping to the piano or "
                     "guitar in " + ", ".join(dict.fromkeys(secs))
                     + ", so two chord players never fight over the "
                     "changes; anything written for it still plays. "
                     f"Write '{l}: groove' to have both comp")
    if realized_bars:
        findings.add("listen: made up from the chord symbols (the "
                     "rhythm section, solos and backgrounds) — "
                     + ", ".join(f"{src_of.get(l, l)} ({n} bars)"
                                 for l, n in realized_bars.items())
                     + " — the pages keep their slashes")
    if played_written:
        findings.add("listen: under the slashes, the source's own notes "
                     "play — "
                     + "; ".join(f"{src_of.get(l, l)} in "
                                 + ", ".join(dict.fromkeys(names))
                                 for l, names in played_written.items())
                     + " — only sections the source leaves empty are made "
                     "up from the chords")
    for l in labels:
        p = os.path.join(outdir, f'{title} — {src_of.get(l, l)}.musicxml')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(document([l], directions_on=lambda _: True,
                             harmony_on=lambda _: True, part_mode=True))
        written.append(p)
    if findings:
        seen = []
        for line in findings.lines:
            if line not in seen:
                print("finding:", line)
                seen.append(line)
        # findings also land in a file: console scroll is not a record
        with open(os.path.join(outdir, f'{title} — findings.txt'), 'w',
                  encoding='utf-8') as f:
            f.write("\n".join(seen) + "\n" if seen else
                    "No findings — nothing was reduced, guessed, "
                    "or moved.\n")
    print(f"chartc: wrote {len(written)} files, {total} bars, "
          f"{len(chart['sections'])} sections.")
    return written


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('chart')
    ap.add_argument('-o', '--outdir', default='chart-build')
    a = ap.parse_args()
    compile_chart(a.chart, a.outdir)
