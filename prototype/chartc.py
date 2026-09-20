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
endings, `hits`, `double`, `cue`, `build:`, `on pass`, meters other
than 4/4.

Usage: chartc.py <file.chart> [-o outdir]
"""
import os
import re
import sys
import argparse

import chartdemo

BEATS = 4          # 4/4 only in this increment

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
def _inst(transpose, fold, clef, foff, comf, poly=False):
    return {'transpose': transpose, 'fold': fold, 'clef': clef,
            'foff': foff, 'comf': comf, 'poly': poly}


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
    'electric bass':     _inst(12, (23, 60),  'F', 0, (28, 55)),
    'piano':             _inst(0,  (21, 108), 'G', 0, (21, 108), poly=True),
    'vibraphone':        _inst(0,  (53, 89),  'G', 0, (53, 89), poly=True),
    'organ':             _inst(0,  (24, 96),  'G', 0, (24, 96), poly=True),
    # orchestral doubles and colors
    'english horn':      _inst(7,  (52, 81),  'G', 1, (52, 79)),
    'alto flute':        _inst(5,  (55, 91),  'G', 1, (55, 88)),
    'eb clarinet':       _inst(-3, (55, 96),  'G', -1, (55, 91)),
    'cornet':            _inst(2,  (54, 94),  'G', 2, (54, 82)),
    'euphonium':         _inst(0,  (34, 70),  'F', 0, (40, 67)),
    'harp':              _inst(0,  (24, 103), 'G', 0, (24, 103), poly=True),
    'celesta':           _inst(-12, (60, 108), 'G', 0, (60, 108), poly=True),
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
    # key, grooves, kicks and words — notation from a played demo is
    # future work for the whole unpitched family
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
    'piano':          ('Piano', 'keyboard.piano', 1),
    'vibraphone':     ('Vibraphone', 'pitched-percussion.vibraphone', 12),
    'organ':          ('Organ', 'keyboard.organ', 17),
    'english horn':   ('English Horn', 'wind.reed.english-horn', 70),
    'alto flute':     ('Alto Flute', 'wind.flutes.flute.alto', 74),
    'eb clarinet':    ('Eb Clarinet', 'wind.reed.clarinet.eflat', 72),
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
    'horn in f': 'french horn',
    'bone': 'trombone', 't-bone': 'trombone',
    'flugel': 'flugelhorn', 'picc': 'piccolo',
    'upright bass': 'double bass', 'string bass': 'double bass',
    'acoustic bass': 'double bass', 'contrabass': 'double bass',
    'bass': 'electric bass', 'bass guitar': 'electric bass',
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
    """'Eb minor' -> (fifths, mode)."""
    m = re.fullmatch(r'([A-Ga-g][b#]?)\s*(major|minor)?', text.strip())
    if not m:
        fail(f"cannot read key '{text}'")
    root = m.group(1).lower()
    mode = m.group(2) or 'major'
    if root not in KEY_FIFTHS:
        fail(f"cannot read key root '{m.group(1)}'")
    fifths = KEY_FIFTHS[root] + (-3 if mode == 'minor' else 0)
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
}

# jazz shorthand for qualities: the dash minor, min spellings, bare sus
QUAL_SYNONYMS = {'-': 'm', '-7': 'm7', '-9': 'm9', '-11': 'm11',
                 '-6': 'm6', 'min': 'm', 'min7': 'm7', 'min9': 'm9',
                 'sus': 'sus4', 'ma7': 'maj7', 'M7': 'maj7',
                 'm(maj7)': 'mmaj7', 'aug7': '7#5', '7alt': 'alt'}

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
    if qual not in CHORD_KINDS:
        fail(f"chord quality '{qual}' (in '{sym}') is not in the supported list")
    alter = {'b': -1, '#': 1, '': 0}[acc]
    return (step, alter, qual, bass)


def parse_bars(text, where):
    # a parenthesized group repeats whole: ( F7, Bb7 ) x4 is eight bars
    text = re.sub(r'\(\s*([^()]*?)\s*\)\s*x(\d+)',
                  lambda m: ", ".join([m.group(1)] * int(m.group(2))),
                  text)
    if '(' in text or ')' in text:
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
        n = len(bar)
        for i, item in enumerate(bar):
            if item[0] is None:
                item[0] = 1.0 + i * (BEATS / n) if n > 1 else 1.0
        for _ in range(reps):
            bars.append([(b, split_chord(s)) for b, s in bar])
    return bars


def parse_chart(path):
    chart = {'header': {}, 'band': [], 'chords': {}, 'sections': [],
             'pickup': None}
    cur = None          # current section
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
            m = re.match(r'chords ([\w ]+?):\s*(.+)$', s)
            if m:
                chart['chords'][m.group(1).strip()] = parse_bars(
                    m.group(2), f"chords {m.group(1)}")
                continue
            m = re.match(r'figure ', s)
            if m:
                fail(f"{loc}: named figures are not built yet — "
                     "use 'as engraved' or wait for the next increment")
            m = re.match(r'pickup (\d+) beats((?:,\s*as engraved)?)'
                         r'(?::\s*(.*))?$', s)
            if m:
                texts = re.findall(r'text "([^"]*)"', m.group(3) or '')
                chart['pickup'] = {'beats': int(m.group(1)),
                                   'engraved': bool(m.group(2)),
                                   'texts': texts}
                continue
            m = re.match(r'section ([\w ]+?)'
                         r'(?:,\s*(\d+) bars)?'
                         r'(?:,\s*label "([^"]*)")?'
                         r'(?:,\s*repeat (\d+)x)?'
                         r'(,\s*open)?\s*$', s)
            if m:
                if m.group(2) is None:
                    fail(f"{loc}: section {m.group(1)} must declare its length")
                cur = {'name': m.group(1).strip(), 'bars': int(m.group(2)),
                       'label': m.group(3), 'repeat': int(m.group(4) or 0),
                       'open': bool(m.group(5)), 'content': None,
                       'feel': None, 'directives': [], 'events': []}
                chart['sections'].append(cur)
                continue
            m = re.match(r'(\w+):\s*(.+)$', s)
            if m and m.group(1) in ('title', 'composer', 'arranger', 'key',
                                    'meter', 'tempo', 'feel', 'source',
                                    'demo', 'countin', 'dynamics'):
                chart['header'][m.group(1)] = m.group(2).strip().strip('"')
                continue
            fail(f"{loc}: cannot read '{s}'")

        # indented lines
        if mode == 'band':
            m = re.match(r'([\w ]+?)(?:\s*=\s*([\w ]+?))?'
                         r'(?:,\s*detail (\w[\w-]*))?'
                         r'(?:,\s*tuning ([\w ]+))?'
                         r'(?:,\s*demo "([^"]+)"(?:\s+octave (-?\d+))?)?\s*$',
                         s)
            if not m:
                fail(f"{loc}: cannot read band line '{s}'")
            chart['band'].append({'label': m.group(1).strip(),
                                  'instrument': (m.group(2) or m.group(1)).strip(),
                                  'detail': m.group(3),
                                  'tuning': m.group(4),
                                  'demo': m.group(5),
                                  'demo_octave': int(m.group(6) or 0)})
            continue
        if mode == 'output':
            continue        # defaults only in this increment
        if cur is None:
            fail(f"{loc}: indented line outside any section: '{s}'")

        m = re.match(r'feel:\s*(.+)$', s)
        if m:
            cur['feel'] = m.group(1).strip()
            continue
        m = re.match(r'chords:\s*(.+)$', s)
        if m:
            cur['content'] = parse_bars(m.group(1), f"section {cur['name']}")
            continue
        m = re.match(r'use chords ([\w ]+?)(?:\s+x(\d+))?$', s)
        if m:
            name = m.group(1).strip()
            if name not in parse_chart.defs_ref:
                pass
            cur['use'] = (name, int(m.group(2) or 1))
            continue
        m = re.match(r'at bar (\d+):\s*text "([^"]*)"$', s)
        if m:
            cur['events'].append((int(m.group(1)), 'text', m.group(2)))
            continue
        m = re.match(r'([\w ]+?):\s*(.+)$', s)
        if m:
            cur['directives'].append((m.group(1).strip(), m.group(2).strip(),
                                      loc))
            continue
        fail(f"{loc}: cannot read '{s}' in section {cur['name']}")

    # resolve `use chords`
    for sec in chart['sections']:
        if 'use' in sec:
            name, times = sec.pop('use')
            if name not in chart['chords']:
                fail(f"section {sec['name']} uses chords '{name}', not defined")
            sec['content'] = chart['chords'][name] * times
        if sec['content'] is None:
            fail(f"section {sec['name']} has no chords")
        if len(sec['content']) != sec['bars']:
            fail(f"section {sec['name']} declares {sec['bars']} bars but its "
                 f"chords cover {len(sec['content'])}")
    return chart


parse_chart.defs_ref = {}


# --------------------------------------------------------- source score

def load_source(path):
    xml = open(path, encoding='utf-8').read()
    order = re.findall(r'<score-part id="([^"]+)">', xml)
    names = dict(re.findall(
        r'<score-part id="([^"]+)">.*?<part-name[^>]*>([^<]*)</part-name>',
        xml, re.S))
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
        parts[names[pid].strip()] = {
            'measures': ms, 'div': int(dv.group(1)) if dv else 8,
            'staves': int(staves.group(1)) if staves else 1,
            'clef': clef.group(1) if clef else 'G',
            'fifths': int(fifths.group(1)) if fifths else 0}
    return parts


def match_part(label, source_names):
    """Band label -> unique source part name, by token prefix matching."""
    drop = {'in', 'bb', 'eb', 'f', 'c'}
    lt = [t for t in label.lower().split()]
    hits = []
    for name in source_names:
        nt = [t for t in name.lower().split() if t not in drop]
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
        if re.search(r'<rehearsal|<words|<metronome', block):
            return ''
        return block
    return re.sub(r'<direction[^>]*>.*?</direction>\s*', keep, content,
                  flags=re.S)


def direction(text, placement='above'):
    return (f'      <direction placement="{placement}">'
            f'<direction-type><words>{text}</words></direction-type>'
            f'</direction>\n')


def rehearsal(mark):
    return ('      <direction placement="above"><direction-type>'
            f'<rehearsal>{mark}</rehearsal></direction-type></direction>\n')


def harmony_xml(chord, beat, div):
    step, alter, qual, bass = chord
    entry = CHORD_KINDS[qual]
    kind, ktext = entry[0], entry[1]
    degrees = entry[2] if len(entry) > 2 else []
    off = (beat - 1.0) * div
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


def slash_bar(div, clef, staves, fifths):
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
    out = []
    for _ in range(BEATS):
        # dynamics="0": a slash is an instruction, not a pitch — playback
        # renderers must not sound the B the notehead happens to sit on
        out += ['      <note dynamics="0">',
                pitch,
                f'        <duration>{div}</duration>',
                '        <voice>1</voice>',
                '        <type>quarter</type>',
                '        <stem>none</stem>',
                '        <notehead>slash</notehead>']
        if staves > 1:
            out.append('        <staff>1</staff>')
        out.append('      </note>')
    if staves > 1:
        out += [f'      <backup><duration>{div * BEATS}</duration></backup>',
                '      <note>',
                '        <rest measure="yes"/>',
                f'        <duration>{div * BEATS}</duration>',
                '        <voice>2</voice>',
                '        <staff>2</staff>',
                '      </note>']
    return "\n".join(out) + "\n"


def hits_bar(pattern, div, clef, staves, fifths):
    """Rhythmic kicks: slash noteheads WITH stems at the named beats,
    rests around them — 'hits on 1, 2+, 4' as the spec always promised.
    Each hit rings to the next hit or the bar line."""
    import convert as _c
    step, octv = SLASH_PITCH.get(clef, ('B', 4))
    alter = key_alter(step, fifths)
    positions = sorted({int(round((b - 1) * div)) for b in pattern})
    out = []
    if positions and positions[0] > 0:
        for ln in _c.emit_rest(positions[0], div, 1, 1):
            out.append(ln)
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else div * BEATS
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
            out.append('      </note>')
    return "\n".join(out) + "\n"


def rest_bar(div, staves):
    out = []
    for staff in range(1, staves + 1):
        if staff == 2:
            out.append(f'      <backup><duration>{div * BEATS}</duration>'
                       '</backup>')
        out += ['      <note>',
                '        <rest measure="yes"/>',
                f'        <duration>{div * BEATS}</duration>',
                f'        <voice>{staff}</voice>']
        if staves > 1:
            out.append(f'        <staff>{staff}</staff>')
        out.append('      </note>')
    return "\n".join(out) + "\n"


# ------------------------------------------------------------ compile

def resolve_groups(band):
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
                     'drums', 'organ', 'vibraphone', 'banjo',
                     'accordion')]}
    g['horns'] = [l for l in labels
                  if l in g['saxes'] or l in g['trumpets'] or
                  l in g['trombones']]
    g['band'] = labels[:]
    return g


def compile_chart(chart_path, outdir):
    chart = parse_chart(chart_path)
    hdr = chart['header']
    if hdr.get('meter', '4/4') != '4/4':
        fail("only 4/4 charts compile in this increment")
    src_path = hdr.get('source')
    if src_path and not os.path.isabs(src_path):
        src_path = os.path.join(os.path.dirname(os.path.abspath(chart_path)),
                                src_path)
    source = load_source(src_path) if src_path and os.path.exists(src_path) \
        else None
    if hdr.get('source') and source is None:
        fail(f"source score '{hdr['source']}' not found next to the chart")

    band = chart['band']
    groups = resolve_groups(band)
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
    if source is None and any(
            plan['content'][l][0] == 'engraved'
            for plan in plans for l in labels):
        fail("'as engraved' is used but the chart has no source: line "
             "naming an engraving")

    # ---- the from-demo door
    findings = chartdemo.Findings()
    resolved, horn_of, key = resolve_demo(chart, plans, band, labels,
                                          chart_path, findings)
    demo_measures = {l: {} for l in labels}
    for l in labels:
        for item in resolved[l]:
            h = horn_of[l]
            tr, foff = h['transpose'], h['foff']
            ms = chartdemo.render_range(item['res'], key[0] + foff, tr,
                                        item['fall'], findings,
                                        short=item['short'],
                                        every=item['every'],
                                        doit=item['doit'],
                                        scoops=item['scoops'])
            for bar, xml in ms.items():
                if bar in demo_measures[l]:
                    fail(f"'{l}' has two demo figures landing on bar {bar}")
                demo_measures[l][bar] = xml
    # ---- the range report: where each part peaks, in written pitch —
    # what an arranger checks before any page reaches a player
    shift = int(hdr.get('countin', 0))
    for l in labels:
        notes = [(p, item['res']['at'] + s // chartdemo.BAR + shift)
                 for item in resolved[l]
                 for s, e, ps in item['res']['timeline'] for p in ps]
        if not notes or l not in horn_of:
            continue
        h = horn_of[l]
        tr, comf = h['transpose'], h['comf']
        hi = max(notes)
        lo = min(notes)
        table = chartdemo.spelling_table(key[0] + h['foff'],
                                         chartdemo.Findings())
        def wname(p):
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
        findings.add(f"{l}: written peak {wname(hi[0])} at bar {hi[1]}, "
                     f"lowest {wname(lo[0])} at bar {lo[1]}{edge}")
    return _compile_rest(chart, band, groups, labels, plans, total,
                         source, src_of, chord_parts, hdr, chart_path, outdir,
                         demo_measures, horn_of, key, findings)


def resolve_demo(chart, plans, band, labels, chart_path, findings):
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
            horn_of[b['label']] = HORNS[inst]
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
                sel = ref['track'] or b['demo']
                if sel and sel.lower().endswith(('.mid', '.midi')):
                    dm = chartdemo.load_demo(sel if os.path.isabs(sel)
                                             else os.path.join(chart_dir, sel))
                    track = None
                else:
                    if not demo_path:
                        fail(f"{ref['loc']}: '{l}' uses from demo but the "
                             "chart has no demo: line")
                    dm = chartdemo.load_demo(demo_path)
                    track = sel
                res = chartdemo.resolve_range(
                    dm, track, ref['lo'], ref['hi'], ref['at'],
                    octave_shift=b['demo_octave'],
                    sounding_range=rng, quant=ref.get('quant'),
                    poly=h['poly'],
                    derive_dyns=hdr.get('dynamics', '') not in
                    ('by hand', 'manual'),
                    short=ref.get('short', False),
                    spoken_shift=int(hdr.get('countin', 0)),
                    part_label=l, findings=findings)
                resolved[l].append({'res': res, 'fall': ref['fall'],
                                    'short': ref.get('short', False),
                                    'every': ref.get('every'),
                                    'doit': ref.get('doit', False),
                                    'scoops': ref.get('scoops', []),
                                    'plan': plan})
    return resolved, horn_of, (fifths, mode)


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
                'overlays': {l: [] for l in labels}}
        for target, instr, loc in sec['directives']:
            tgts = groups.get(target) or ([target] if target in labels else None)
            if tgts is None:
                fail(f"{loc}: '{target}' is not a band part or group")
            anns, engraved, groove_words = [], None, None
            demo_refs, fall, quant, short = [], False, None, False
            every_artic, dyn_marks, scoops, doit = None, [], [], False
            hits_map = {}
            raw_pieces = [normalize_piece(p.strip())
                          for p in instr.split(',')]
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
                m = re.match(r'as engraved bars (\d+)-(\d+)'
                             r'(?:\s+at bar (\d+))?$', piece)
                if m:
                    engraved = (int(m.group(1)), int(m.group(2)),
                                int(m.group(3) or 1))
                    continue
                m = re.match(r'from demo(?:\s+"([^"]+)")?'
                             r'\s+bars (\d+)(?:-(\d+))?'
                             r'(?:\s+at bar (\d+))?$', piece)
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
                    demo_refs.append({'track': m.group(1), 'lo': lo,
                                      'hi': hi, 'at': at, 'loc': loc})
                    continue
                m = re.match(r'hits(?: bar (\d+))? on (.+)$', piece)
                if m:
                    beats = [parse_beat(t) for t in m.group(2).split()]
                    hits_map[int(m.group(1)) if m.group(1) else None] = \
                        beats
                    continue
                m = re.match(r'mute (\w+)$', piece)
                if m:
                    anns.append((1, f'{m.group(1)} mute'))
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
                m = re.match(r'dyn (pp|p|mp|mf|f|ff|sfz|fp)'
                             r'(?:\s+at bar (\d+))?'
                             r'(?:\s+beat (\S+))?$', piece)
                if m:
                    if m.group(3):
                        try:
                            beat = float(m.group(3))
                        except ValueError:
                            beat = parse_beat(m.group(3))
                    else:
                        beat = 1.0
                    dyn_marks.append((int(m.group(2) or 1), beat,
                                      m.group(1)))
                    continue
                m = re.match(r'groove(?:\s+"([^"]*)")?$', piece)
                if m:
                    groove_words = m.group(1) or ''
                    continue
                m = re.match(r'text "([^"]*)"(?:\s+at bar (\d+))?$', piece)
                if m:
                    anns.append((int(m.group(2) or 1), m.group(1)))
                    continue
                if piece == 'tacet':
                    engraved = 'tacet'
                    continue
                if piece in ('solo', 'solo open'):
                    anns.append((1, 'solos (open)' if 'open' in piece
                                 or sec['open'] else 'Solo'))
                    continue
                if piece == 'backgrounds':
                    anns.append((1, 'backgrounds'))
                    continue
                if piece == 'on cue':
                    if anns and anns[-1][1] == 'backgrounds':
                        anns[-1] = (anns[-1][0], 'backgrounds on cue')
                    else:
                        anns.append((1, 'on cue'))
                    continue
                fail(f"{loc}: instruction '{piece}' is not built yet")
            for l in tgts:
                if engraved == 'tacet':
                    plan['content'][l] = ('tacet', None)
                elif engraved:
                    plan['content'][l] = ('engraved', engraved)
                elif hits_map:
                    plan['content'][l] = ('hits',
                                          (hits_map, groove_words or ''))
                elif groove_words is not None:
                    plan['content'][l] = ('groove', groove_words)
                for ref in demo_refs:
                    plan['overlays'][l].append(dict(ref, fall=fall,
                                                    quant=quant,
                                                    short=short,
                                                    every=every_artic,
                                                    doit=doit,
                                                    scoops=scoops))
                plan['texts'][l].extend(anns)
                plan['dyns'][l].extend(dyn_marks)
        for bar, kind, text in sec['events']:
            for l in labels:
                plan['texts'][l].append((bar, text))
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
    -12: ('0', '0', '1'),        # piccolo, xylophone, celesta
    -24: ('0', '0', '2'),        # glockenspiel
}

CLEF_XML = {'G': '<sign>G</sign><line>2</line>',
            'F': '<sign>F</sign><line>4</line>',
            'C': '<sign>C</sign><line>3</line>',
            'percussion': '<sign>percussion</sign><line>2</line>'}

SOUND_DYN = {'pp': 40, 'p': 54, 'mp': 71, 'mf': 89, 'f': 106, 'ff': 123,
             'sfz': 112, 'fp': 98}


def _compile_rest(chart, band, groups, labels, plans, total,
                  source, src_of, chord_parts, hdr, chart_path, outdir,
                  demo_measures=None, horn_of=None, key=(0, 'major'),
                  findings=None):
    demo_measures = demo_measures or {l: {} for l in labels}
    horn_of = horn_of or {}

    # ---- emit one part's measures
    def part_measures(label, with_directions, with_harmony, listen=False,
                      part_mode=False):
        b = next(x for x in band if x['label'] == label)
        default_groove = label in groups['rhythm']
        sp = source[src_of[label]] if source else None
        horn = horn_of.get(label)
        div = sp['div'] if sp else chartdemo.DIV
        staves = sp['staves'] if sp else 1
        clef = sp['clef'] if sp else (horn['clef'] if horn else 'G')
        fifths = sp['fifths'] if sp else (key[0] + horn['foff'] if horn
                                          else key[0])
        governing = [None]      # printed-chord state, carried across bars
        out = []

        def attributes():
            tr = ''
            if horn and horn['transpose'] in TRANSPOSE_XML:
                d, c, o = TRANSPOSE_XML[horn['transpose']]
                tr = (f'<transpose><diatonic>{d}</diatonic>'
                      f'<chromatic>{c}</chromatic>'
                      + (f'<octave-change>{o}</octave-change>' if o else '')
                      + '</transpose>')
            keyxml = ('' if clef == 'percussion' else
                      f'        <key><fifths>{fifths}</fifths>'
                      f'<mode>{key[1]}</mode></key>\n')
            return ('      <attributes>\n'
                    f'        <divisions>{div}</divisions>\n'
                    + keyxml +
                    '        <time><beats>4</beats>'
                    '<beat-type>4</beat-type></time>\n'
                    f'        <clef>{CLEF_XML[clef if clef in CLEF_XML else "G"]}'
                    '</clef>\n'
                    + ('' if clef == 'percussion' else
                       (f'        {tr}\n' if tr else ''))
                    + '      </attributes>\n')

        pk = chart['pickup']
        if pk:
            content = ''
            if pk['engraved'] and sp and '0' in sp['measures']:
                content = strip_lifted(sp['measures']['0'], clef == 'percussion')
            if with_directions:
                if hdr.get('feel'):
                    content = direction(hdr['feel'].capitalize()) + content
                for t in pk['texts']:
                    content = direction(t, 'below') + content
            out.append((f'    <measure implicit="yes" number="0">\n{content}'
                        '    </measure>\n', False))

        need_attrs = source is None
        was_groove = False
        for plan in plans:
            sec = plan['sec']
            kind, arg = plan['content'][label]
            if kind == 'default':
                kind = 'groove' if default_groove else 'tacet'
                arg = '' if kind == 'groove' else None
            for off in range(sec['bars']):
                absbar = plan['start'] + off
                pieces = []
                if need_attrs:
                    pieces.append(attributes())
                    need_attrs = False
                # slashes are instructions, not pitches: mute the part's
                # playback through a groove region, restore after (the
                # dynamics="0" note attribute alone is ignored by
                # MuseScore's importer — measured, not assumed)
                if off == 0 and kind == 'groove' and not was_groove:
                    pieces.append('      <direction>'
                                  '<sound dynamics="0"/></direction>\n')
                    was_groove = True
                elif off == 0 and kind != 'groove' and was_groove:
                    pieces.append('      <direction>'
                                  '<sound dynamics="80"/></direction>\n')
                    was_groove = False
                if with_directions and absbar == 1 and not chart['pickup']:
                    if hdr.get('feel'):
                        pieces.append(direction(hdr['feel'].capitalize()))
                    if hdr.get('tempo'):
                        pieces.append(
                            '      <direction placement="above">'
                            '<direction-type><metronome>'
                            '<beat-unit>quarter</beat-unit>'
                            f'<per-minute>{hdr["tempo"]}</per-minute>'
                            '</metronome></direction-type>'
                            f'<sound tempo="{hdr["tempo"]}"/>'
                            '</direction>\n')
                if with_directions and off == 0:
                    mark = sec['name']
                    if re.fullmatch(r'[A-Z]|\d+', mark):
                        pieces.append(rehearsal(mark))
                    if sec['label']:
                        pieces.append(direction(sec['label']))
                    if sec['feel']:
                        pieces.append(direction(sec['feel']))
                    if kind == 'groove' and arg:
                        pieces.append(direction(arg))
                    if kind == 'hits' and arg[1]:
                        pieces.append(direction(arg[1]))
                if with_directions:
                    for tbar, text in sorted(plan['texts'][label]):
                        if tbar == off + 1:
                            pieces.append(direction(text, 'above'))
                for dbar, dbeat, mark in plan.get('dyns', {}).get(label, ()):
                    if dbar == off + 1:
                        doff = int(round((dbeat - 1.0) * div))
                        pieces.append(
                            '      <direction placement="below">'
                            '<direction-type><dynamics>'
                            f'<{mark}/></dynamics></direction-type>'
                            + (f'<offset>{doff}</offset>' if doff else '')
                            + f'<sound dynamics="{SOUND_DYN[mark]}"/>'
                            '</direction>\n')
                if with_harmony and clef != 'percussion' and (
                        label in chord_parts or any(
                            t[1].lower().startswith('solo') for t in
                            plan['texts'][label])):
                    for beat, chord in sec['content'][off]:
                        if chord is None:
                            continue
                        if chord != governing[0] or off == 0:
                            pieces.append(harmony_xml(chord, beat, div))
                        governing[0] = chord
                if absbar in demo_measures[label]:
                    pieces.append(demo_measures[label][absbar])
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
                        pieces.append(rest_bar(div, staves))
                elif kind == 'hits':
                    hmap, _gw = arg
                    pattern = hmap.get(off + 1, hmap.get(None))
                    if listen:
                        pieces.append(rest_bar(div, staves))
                    elif pattern:
                        pieces.append(hits_bar(pattern, div, clef,
                                               staves, fifths))
                    else:
                        pieces.append(slash_bar(div, clef, staves,
                                                fifths))
                elif kind == 'groove':
                    # MuseScore's importer plays slash noteheads no matter
                    # what (dynamics="0", cue, sound directions and
                    # unpitched all measured audible), so the listening
                    # variant renders groove regions as real rests
                    pieces.append(rest_bar(div, staves) if listen else
                                  slash_bar(div, clef, staves, fifths))
                else:
                    pieces.append(rest_bar(div, staves))

                barline = ''
                open_bl = ''
                if sec['repeat'] and off == 0:
                    open_bl = ('      <barline location="left">'
                               '<bar-style>heavy-light</bar-style>'
                               '<repeat direction="forward"/></barline>\n')
                if sec['repeat'] and off == sec['bars'] - 1:
                    barline = ('      <barline location="right">'
                               '<bar-style>light-heavy</bar-style>'
                               f'<repeat direction="backward" '
                               f'times="{sec["repeat"]}"/></barline>\n')
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
                pure_rest = (len(pieces) == 1 and not open_bl
                             and '<repeat' not in barline
                             and pieces[0] == rest_bar(div, staves))
                out.append((f'    <measure number="{absbar}">\n' + open_bl +
                            "".join(pieces) + barline + '    </measure>\n',
                            pure_rest))

        # ---- multirests, parts only: a stretch of waiting prints as one
        # bar carrying its count. Runs break naturally at anything a
        # player must see — marks, texts, dynamics, double bars — because
        # those bars are not pure rests.
        if part_mode:
            i = 0
            while i < len(out):
                if out[i][1]:
                    j = i
                    # a double bar may close a multirest, never hide in one
                    while (j + 1 < len(out) and out[j + 1][1]
                           and '<barline' not in out[j][0]):
                        j += 1
                    n = j - i + 1
                    if n >= 2:
                        content, _ = out[i]
                        content = content.replace(
                            '      <note>',
                            '      <attributes><measure-style>'
                            f'<multiple-rest>{n}</multiple-rest>'
                            '</measure-style></attributes>\n'
                            '      <note>', 1)
                        out[i] = (content, True)
                    i = j + 1
                else:
                    i += 1
        return "".join(c for c, _ in out)

    # ---- whole documents
    def document(part_labels, directions_on, harmony_on, listen=False,
                 part_mode=False):
        L = [XMLHEAD, '<score-partwise version="3.1">\n',
             '  <work><work-title>%s</work-title></work>\n' %
             hdr.get('title', 'Untitled'),
             '  <identification>']
        if hdr.get('composer'):
            L.append('<creator type="composer">%s</creator>' % hdr['composer'])
        if hdr.get('arranger'):
            L.append('<creator type="arranger">%s</creator>' % hdr['arranger'])
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
    title = hdr.get('title', 'chart')
    score_path = os.path.join(outdir, f'{title} — score.musicxml')
    with open(score_path, 'w', encoding='utf-8') as f:
        f.write(document(labels,
                         directions_on=lambda l: l == labels[0],
                         harmony_on=lambda l: l in chord_parts))
    written = [score_path]
    listen_path = os.path.join(outdir, f'{title} — for listening.musicxml')
    with open(listen_path, 'w', encoding='utf-8') as f:
        f.write(document(labels,
                         directions_on=lambda l: l == labels[0],
                         harmony_on=lambda l: l in chord_parts,
                         listen=True))
    written.append(listen_path)
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
