#!/usr/bin/env python3
"""chartedit — the roadmap conversation ("chart edit").

The main road, in Matthew's words: import whatever MIDI he wants,
describe the ROADMAP of the chart, and Copyist does its thing. This
module is that conversation. It grows out of the chartnew interview
(which already scans the demo and asks the header and band): where
chartnew stops — "carve your sections by hand" — this begins.

The agreed shape (2026-09-22, each point his yes):

- Tell it, then it asks: he says the tune in one breath ("8 bar intro,
  head is 32 AABA, solos over the head twice, out on the last A"), it
  places what it understood and asks one question at a time about only
  the gaps.
- Chords arrive three ways: SPOKEN the way he'd call them on the
  bandstand ("b flat seven, four bars"), PLAYED (a MIDI file of him
  playing the changes — named by pitch-class matching, read back for
  his yes), or LIFTED from a demo track's comping.
- Terse, detail on demand. Every answer echoes back what Copyist
  understood, in one write.
- Learning goes through his yes: an unknown word is never silently
  guessed. The session asks what it means once, writes it to the
  vocabulary file, and reads it forever after. Once learned it is
  deterministic — no AI at build time.

Every prompt states its current value or default before asking (a
screen reader user never changes a thing to learn what it was), and
every answer is validated at the door: a chords line that does not add
up to the section is a sentence naming both counts, asked again — never
a build-time surprise.
"""
import json
import os
import re
import sys

import chartc
import chartdemo

CONFIG_DIR = os.path.expanduser("~/.config/copyist")
VOCAB_PATH = os.path.join(CONFIG_DIR, "vocabulary.json")

NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def porcelain():
    """The machine door: with COPYIST_PORCELAIN=1 every say and ask is
    one JSON line, so a real app can hold the same conversation the
    terminal does — one engine, two front doors."""
    return os.environ.get("COPYIST_PORCELAIN") == "1"


def say(line):
    """One write per thing said — a screen reader restarts on every
    write."""
    if porcelain():
        sys.stdout.write(json.dumps({"type": "say", "text": line})
                         + "\n")
    else:
        sys.stdout.write(line + "\n")
    sys.stdout.flush()


def ask(question, default=""):
    if porcelain():
        sys.stdout.write(json.dumps({"type": "ask", "text": question,
                                     "default": default}) + "\n")
    else:
        suffix = f" (now: {default})" if default != "" else ""
        sys.stdout.write(f"{question}{suffix}: ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        return default
    line = line.strip()
    return line if line else default


# --------------------------------------------------------- vocabulary

def load_vocab():
    try:
        with open(VOCAB_PATH, encoding="utf-8") as f:
            v = json.load(f)
        return {str(k).lower(): str(w) for k, w in v.items()}
    except Exception:
        return {}


def save_vocab(vocab):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(VOCAB_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(vocab.items())), f, indent=2)
        f.write("\n")


def apply_vocab(text, vocab):
    """Replace his words with what he taught them to mean — whole words,
    case-insensitive, longest phrase first so 'walk it down' beats
    'walk'."""
    for word in sorted(vocab, key=len, reverse=True):
        text = re.sub(r"\b" + re.escape(word) + r"\b", vocab[word],
                      text, flags=re.IGNORECASE)
    return text


def learn(word, vocab, asker=ask):
    """Ask once, remember forever — and only through his yes."""
    meaning = asker(f"I don't know '{word}'. Tell me what to read it "
                    "as (or Enter to skip)")
    if meaning:
        vocab[word.lower()] = meaning
        save_vocab(vocab)
        say(f"Learned: '{word}' means '{meaning}', for good. "
            f"(The vocabulary file is {VOCAB_PATH}.)")
    return meaning


# ------------------------------------------------------- number words

UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
         "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def num(tok):
    """'8', 'eight', 'thirty-two' -> int, else None."""
    tok = tok.lower().strip()
    if tok.isdigit():
        return int(tok)
    if tok in UNITS:
        return UNITS[tok]
    if tok in TENS:
        return TENS[tok]
    m = re.fullmatch(r"(\w+)-(\w+)", tok)
    if m and m.group(1) in TENS and m.group(2) in UNITS:
        return TENS[m.group(1)] + UNITS[m.group(2)]
    return None


def digitize(text):
    """Number words become digits, for the form parser only — the
    chord parser keeps its words ('b flat seven' must stay 'seven')."""
    toks = text.split()
    out, i = [], 0
    while i < len(toks):
        bare = toks[i].rstrip(",.;:")
        tail = toks[i][len(bare):]
        n = num(bare)
        if n is not None and bare.lower() in TENS and i + 1 < len(toks):
            n2 = num(toks[i + 1].rstrip(",.;:"))
            if n2 is not None and n2 < 10:
                tail2 = toks[i + 1][len(toks[i + 1].rstrip(",.;:")):]
                out.append(str(n + n2) + tail2)
                i += 2
                continue
        out.append((str(n) + tail) if n is not None else toks[i])
        i += 1
    return " ".join(out)


# --------------------------------------------------- the form parser
#
# One clause per comma (or "then"). Each clause becomes a section plan:
#   {'name', 'bars', 'repeat', 'open', 'kind', 'use', 'source', 'shape'}
# kind: 'plain' | 'solos' | 'out'.  use: the section whose chords this
# one borrows.  shape: 'aaba'-style carve question.  Anything the
# parser cannot place becomes a gap the conversation asks about.

SHAPES = ("aaba", "abac", "abab", "aab", "abca")


# the words a story is told with — each one starts a new clause
CONNECTORS = r"and then|after that|from there|then|finally|next"

# a mood on a section prints as its label, the way a real chart says
# "(quiet)" beside the letter
MOODS = ("quiet", "soft", "gentle", "mellow", "easy", "big", "loud",
         "burning", "greasy", "nasty", "floating", "driving",
         "half-time", "double-time", "laid back", "in your face",
         "building", "sparse", "full")


def parse_form(text, vocab=None):
    text = apply_vocab(text, vocab or {})
    text = digitize(text)
    clauses = re.split(r",|\b(?:" + CONNECTORS + r")\b|\.|;", text)
    plans, gaps = [], []
    for raw in clauses:
        c = raw.strip().strip(".").strip()
        if not c:
            continue
        plan = parse_clause(c)
        if plan is None:
            gaps.append(c)
        else:
            plans.append(plan)
    return plans, gaps


def _mk(name, bars=None, repeat=1, open_=False, kind="plain",
        use=None, source=None, shape=None):
    return {"name": name, "bars": bars, "repeat": repeat, "open": open_,
            "kind": kind, "use": use, "source": source, "shape": shape}


def _repeat_words(c):
    """Strip 'twice' / 'x2' / '3 times' / 'open' off a clause; return
    (rest, repeat, open)."""
    reps, open_ = 1, False
    m = re.search(r"\bopen\b", c)
    if m:
        open_ = True
        c = (c[:m.start()] + c[m.end():]).strip().strip(",")
    m = re.search(r"\btwice\b|\bx\s?(\d+)\b|\b(\d+)\s+times\b", c)
    if m:
        reps = int(m.group(1) or m.group(2) or 2)
        c = (c[:m.start()] + c[m.end():]).strip().strip(",")
    return c.strip(), reps, open_


def parse_clause(c):
    low = c.lower()
    # story openers fall away: "it opens with an 8 bar intro"
    low = re.sub(r"^(?:it|we|the tune|the song)?\s*"
                 r"(?:opens?|starts?|begins?|kicks?\s+off)\s+"
                 r"(?:with\s+|on\s+|up\s+)?", "", low).strip()
    # "ends on the head" is the out; "ends with an 8 bar tag" is a tag
    m = re.match(r"^ends?\s+(?:with|on)\s+(?:the\s+)?(.+)$", low)
    if m:
        rest = m.group(1).strip()
        p = parse_clause(rest)
        if p and (p["bars"] or p.get("form")):
            return p
        return _mk("out", kind="out", source=rest)
    low, reps, open_ = _repeat_words(low)
    # a mood prints as the section's label
    mood = None
    for w in MOODS:
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            mood = w
            low = re.sub(r"\b" + re.escape(w) + r"\b", " ",
                         low).strip()
            low = re.sub(r"\s{2,}", " ", low)
            break
    # the connective tissue after an opener and mood: "with a 4 bar
    # piano intro" is a 4-bar piano intro
    low = re.sub(r"^(?:with|on)\s+", "", low).strip()
    low = re.sub(r"^(?:a|an|the)\s+", "", low).strip()
    p = _clause_core(low, reps, open_)
    if p is not None and mood:
        p["mood"] = mood
    return p


def _clause_core(low, reps, open_):
    # "solos over the head", "solos on the blues"
    m = re.fullmatch(r"solos?(?:\s+(?:over|on)\s+(?:the\s+)?"
                     r"([\w ]+?))?(?:\s+form)?", low)
    if m:
        return _mk("solos", kind="solos", use=(m.group(1) or "").strip()
                   or None, repeat=reps, open_=open_)

    # "out on the last A", "out over the head", "outro ..."
    m = re.fullmatch(r"(?:out|outro)(?:\s+(?:over|on)\s+(?:the\s+)?"
                     r"([\w ]+?))?", low)
    if m:
        return _mk("out", kind="out", source=(m.group(1) or "").strip()
                   or None, repeat=reps, open_=open_)

    # a form it knows by name — "12 bar blues in b flat", "rhythm
    # changes" — arrives with its changes already in hand, offered
    # for a yes at chords time
    for alias, real in FORM_ALIASES.items():
        low = re.sub(r"\b" + re.escape(alias) + r"\b", real, low)
    m = FORM_RE.search(low)
    if m:
        kind = m.group(2)
        fbars = FORMS[kind]["bars"]
        bars = int(m.group(1)) if m.group(1) else fbars
        pre = re.sub(r"\b(is|the|a|an|of)\b", " ", low[:m.start()])
        pre = re.sub(r"[^\w ]", " ", pre).split()
        p = _mk(pre[0] if pre else "head", bars=bars, repeat=reps,
                open_=open_)
        if bars == fbars:
            p["form"] = (kind, (m.group(3) or "").strip() or None)
        return p

    shape = None
    for s in SHAPES:
        if re.search(r"\b" + s + r"\b", low):
            shape = s
            low = re.sub(r"\b" + s + r"\b", "", low).strip()
            break

    # "8 bar intro" / "8 bars of intro"
    m = re.fullmatch(r"(\d+)[- ]bars?(?:\s+of)?\s+([\w ]+)", low)
    if m:
        return _mk(m.group(2).strip(), bars=int(m.group(1)),
                   repeat=reps, open_=open_, shape=shape)
    # "head is 32" / "the head is 32 bars"
    m = re.fullmatch(r"(?:the\s+)?([\w ]+?)\s+is\s+(\d+)(?:\s+bars?)?",
                     low)
    if m:
        return _mk(m.group(1).strip(), bars=int(m.group(2)),
                   repeat=reps, open_=open_, shape=shape)
    # "intro 8" / "intro, 8 bars" (comma already split; "intro 8 bars")
    m = re.fullmatch(r"(?:the\s+)?([\w ]+?)\s+(\d+)(?:\s+bars?)?", low)
    if m and num(m.group(2)) is not None:
        return _mk(m.group(1).strip(), bars=int(m.group(2)),
                   repeat=reps, open_=open_, shape=shape)
    # a bare name — bars become a gap question, not a guess
    m = re.fullmatch(r"(?:an?\s+|the\s+)?([\w ]+)", low)
    if m and len(m.group(1).split()) <= 3:
        return _mk(m.group(1).strip(), repeat=reps, open_=open_,
                   shape=shape)
    return None


# ---------------------------------------------------- spoken chords
#
# "b flat seven 4 bars, e flat seven, c nine f seven at 3" — the way a
# writer calls changes on the bandstand.  Typed symbols pass through
# untouched; the two mix freely.  The output is a chords: line in the
# format's own grammar, validated by the compiler's parser afterwards.

QUALITY_WORDS = [
    ("minor seven flat five", "m7b5"),
    ("minor major seven", "mmaj7"),
    ("seven sharp eleven", "7#11"),
    ("seven flat thirteen", "7b13"),
    ("thirteen flat nine", "13b9"),
    ("seven sus four", "7sus4"),
    ("minor add nine", "madd9"),
    ("diminished seven", "dim7"),
    ("seven sharp five", "7#5"),
    ("seven flat five", "7b5"),
    ("seven flat nine", "7b9"),
    ("seven sharp nine", "7#9"),
    ("augmented seven", "7#5"),
    ("half diminished", "m7b5"),
    ("minor six nine", "m69"),
    ("major seven", "maj7"),
    ("major nine", "maj9"),
    ("minor eleven", "m11"),
    ("minor seven", "m7"),
    ("minor nine", "m9"),
    ("minor six", "m6"),
    ("seven sus", "7sus4"),
    ("add nine", "add9"),
    ("six nine", "69"),
    ("sus four", "sus4"),
    ("sus two", "sus2"),
    ("major triad", "maj"),
    ("minor triad", "m"),
    ("dominant seven", "7"),
    ("dominant", "7"),
    ("triad", "maj"),
    ("thirteen", "13"),
    ("eleven", "11"),
    ("altered", "alt"),
    ("augmented", "aug"),
    ("diminished", "dim"),
    ("major", "maj"),
    ("minor", "m"),
    ("nine", "9"),
    ("seven", "7"),
    ("six", "6"),
    ("sus", "sus4"),
]

SYMBOL_RE = re.compile(r"^[A-Ga-g][b#]?[\w#+()/@.]*$")


class SpokenError(Exception):
    """Names the word it could not read, so the vocabulary can learn."""
    def __init__(self, word, segment):
        self.word, self.segment = word, segment
        super().__init__(f"cannot read '{word}' in '{segment}'")


def _note_at(toks, i):
    """Read a note name at toks[i]: 'b flat' -> ('Bb', 2)."""
    t = toks[i].lower()
    if len(t) == 1 and t in "abcdefg":
        root = t.upper()
        if i + 1 < len(toks) and toks[i + 1].lower() in ("flat", "sharp"):
            return root + ("b" if toks[i + 1].lower() == "flat" else "#"), 2
        return root, 1
    return None, 0


def _spoken_segment(seg):
    """One comma-separated segment -> one bar's text ('Bb7', 'C9 F7@3',
    'Bb7 x4')."""
    toks = seg.split()
    chords, i, dur = [], 0, None
    while i < len(toks):
        t = toks[i].lower()
        if t in ("bar", "bars"):
            i += 1
            continue
        m = re.fullmatch(r"x(\d+)", t)
        if m and chords:                      # a typed 'x4'
            dur = int(m.group(1))
            i += 1
            continue
        if t == "no" and i + 1 < len(toks) and \
                toks[i + 1].lower() == "chord":
            chords.append("nc")
            i += 2
            continue
        if t == "nc":
            chords.append("nc")
            i += 1
            continue
        # "at 3" / "at the and of 3" / "at 3 and" places the last chord
        if t == "at" and chords:
            j = i + 1
            plus = False
            if j + 2 < len(toks) and toks[j].lower() == "the" and \
                    toks[j + 1].lower() == "and" and \
                    toks[j + 2].lower() == "of":
                plus, j = True, j + 3
            if j < len(toks) and num(toks[j]) is not None:
                beat = num(toks[j])
                j += 1
                if j < len(toks) and toks[j].lower() == "and":
                    plus, j = True, j + 1
                chords[-1] += f"@{beat}" + ("+" if plus else "")
                i = j
                continue
            raise SpokenError(toks[j] if j < len(toks) else "at", seg)
        # "over e" — slash bass on the last chord
        if t == "over" and chords:
            bass, used = _note_at(toks, i + 1)
            if bass:
                chords[-1] += "/" + bass
                i += 1 + used
                continue
            raise SpokenError(toks[i + 1] if i + 1 < len(toks)
                              else "over", seg)
        # a typed symbol passes through whole (Bb7, F#m7b5, C7/E) — a
        # bare letter goes the spoken road, where "F minor" can follow
        if SYMBOL_RE.match(toks[i]) and len(toks[i]) > 1:
            sym = toks[i]
            root = sym[0].upper() + sym[1:]
            try:
                chartc.split_chord(root.split("@")[0].split("x")[0])
                chords.append(root)
                i += 1
                continue
            except SystemExit:
                pass
        # a spoken note name, then quality words
        root, used = _note_at(toks, i)
        if root:
            i += used
            qual = ""
            rest = " ".join(x.lower() for x in toks[i:])
            for words, q in QUALITY_WORDS:
                if rest == words or rest.startswith(words + " "):
                    qual = q
                    i += len(words.split())
                    break
            else:
                # a digit quality typed after a spoken root: "b flat 7"
                if i < len(toks) and toks[i] in chartc.CHORD_KINDS:
                    qual = toks[i]
                    i += 1
            # bare letter with no quality is major — the bandstand way
            chords.append(root + (qual if qual != "maj" else ""))
            continue
        n = num(toks[i])
        if n is not None:
            # a stray number is only meaningful before "bars"
            if i + 1 < len(toks) and toks[i + 1].lower() in ("bar",
                                                             "bars"):
                dur = n
                i += 2
                continue
            raise SpokenError(toks[i], seg)
        raise SpokenError(toks[i], seg)
    if not chords:
        raise SpokenError(seg.strip() or "(empty)", seg)
    out = " ".join(chords)
    if dur and dur > 1:
        out += f" x{dur}"
    return out


def _spoken_line(text):
    segs = [s.strip() for s in text.split(",") if s.strip()]
    return ", ".join(_spoken_segment(s) for s in segs)


def parse_spoken_chords(text, vocab=None, key=None):
    """The whole answer -> a chords: line.  Raises SpokenError naming
    the first word it cannot read.  Numbers speak too: when the plain
    read fails and the text is degrees ('two five one in c', '1 4 5'),
    they become symbols in the key and ride the same road."""
    text = apply_vocab(text, vocab or {})
    try:
        return _spoken_line(text)
    except SpokenError:
        conv = degrees_to_chords(text, key or "C")
        if conv is None:
            raise
        return _spoken_line(conv)


# ----------------------------------------------- degrees and numbers
#
# "two five one in C", "1 4 5 1", "flat seven, four, one" — Nashville
# numbers and the numbers a rehearsal is actually run with.  Degrees
# become chord symbols FIRST, then ride the ordinary spoken-chords
# road, so commas, shared bars, xN and 'at 3' keep their meanings.
# Bare degrees default to the diatonic sevenths (two is minor seven,
# five is dominant); quality words after a degree override ('four
# minor'); the read-back and his correction are the contract.

DEGREE_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4,
                "five": 5, "six": 6, "seven": 7}
MAJ_DEGREES = {1: (0, "maj7"), 2: (2, "m7"), 3: (4, "m7"),
               4: (5, "maj7"), 5: (7, "7"), 6: (9, "m7"),
               7: (11, "m7b5")}
MIN_DEGREES = {1: (0, "m7"), 2: (2, "m7b5"), 3: (3, "maj7"),
               4: (5, "m7"), 5: (7, "7"), 6: (8, "maj7"),
               7: (10, "7")}


def _degree_at(toks, i):
    """A degree at toks[i]: 'five'/'5'/'flat seven'/'b7' ->
    (degree, alteration, tokens consumed), else (None, 0, 0)."""
    t = toks[i].lower()
    alter, used = 0, 0
    if t in ("flat", "sharp") and i + 1 < len(toks):
        alter = -1 if t == "flat" else 1
        used, t = 1, toks[i + 1].lower()
    m = re.fullmatch(r"([b#])?([1-7])", t)
    if m:
        if m.group(1):
            alter = -1 if m.group(1) == "b" else 1
        return int(m.group(2)), alter, used + 1
    if t in DEGREE_WORDS:
        return DEGREE_WORDS[t], alter, used + 1
    return None, 0, 0


def degrees_to_chords(text, key_text):
    """Rewrite degree tokens as chord symbols in the key; everything
    else passes through.  None when nothing in the text is a degree."""
    minor = "minor" in (key_text or "").lower()
    m = re.search(r"\bin\s+([a-g](?:\s+(?:flat|sharp))?"
                  r"(?:\s+minor)?)\s*$", text, re.IGNORECASE)
    if m:
        key_text = m.group(1)
        minor = "minor" in key_text.lower()
        text = text[:m.start()].rstrip(" ,")
    pc0 = key_pc(key_text)
    if pc0 is None:
        return None
    sharp = pc0 in SHARP_KEYS or "sharp" in (key_text or "").lower()
    names = PC_SHARP if sharp else PC_NAME
    table = MIN_DEGREES if minor else MAJ_DEGREES
    segs, seen = [], False
    for seg in text.split(","):
        toks = seg.split()
        out, i = [], 0
        while i < len(toks):
            d, alter, used = _degree_at(toks, i)
            if d is None:
                out.append(toks[i])
                i += 1
                continue
            seen = True
            iv, qual = table[d]
            if alter:
                # a borrowed chord: flat-seven arrives dominant, the
                # rest major — the read-back catches the exceptions
                iv += alter
                qual = "7" if d == 7 else "maj7"
            # quality words right after the degree override the default
            rest = " ".join(x.lower() for x in toks[i + used:])
            for words, _ in QUALITY_WORDS:
                if rest == words or rest.startswith(words + " "):
                    qual = ""      # leave the words for the chord road
                    break
            out.append(names[(pc0 + iv) % 12] + qual)
            i += used
        segs.append(" ".join(out))
    return ", ".join(segs) if seen else None


# ------------------------------------------------- chords from playing
#
# Pitch-class matching against the quality table: required tones must
# all sound, nothing outside required+optional may sound, the root must
# be present.  The most specific full explanation wins; the bass note
# breaks ties.  Anything unexplained is a question, never a guess.

TEMPLATES = [
    # (quality, required pcs, optional pcs) — root-relative
    ("13", {0, 4, 9, 10}, {7, 2, 5}),
    ("13b9", {0, 4, 9, 10, 1}, {7, 5}),
    ("9", {0, 4, 10, 2}, {7}),
    ("maj9", {0, 4, 11, 2}, {7}),
    ("m9", {0, 3, 10, 2}, {7}),
    ("m11", {0, 3, 10, 5}, {7, 2}),
    ("69", {0, 4, 9, 2}, {7}),
    ("m69", {0, 3, 9, 2}, {7}),
    ("7b9", {0, 4, 10, 1}, {7}),
    ("7#9", {0, 4, 10, 3}, {7}),
    ("7#11", {0, 4, 10, 6}, {7, 2}),
    ("7b13", {0, 4, 10, 8}, {7, 2}),
    ("7#5", {0, 4, 8, 10}, set()),
    ("7b5", {0, 4, 6, 10}, set()),
    ("7sus4", {0, 5, 10}, {7, 2}),
    ("maj7#11", {0, 4, 11, 6}, {7, 2}),
    ("mmaj7", {0, 3, 7, 11}, set()),
    ("m7b5", {0, 3, 6, 10}, set()),
    ("dim7", {0, 3, 6, 9}, set()),
    ("7", {0, 4, 10}, {7}),
    ("maj7", {0, 4, 11}, {7}),
    ("m7", {0, 3, 10}, {7}),
    ("m6", {0, 3, 9}, {7}),
    ("6", {0, 4, 9}, {7}),
    ("add9", {0, 4, 7, 2}, set()),
    ("madd9", {0, 3, 7, 2}, set()),
    ("dim", {0, 3, 6}, set()),
    ("aug", {0, 4, 8}, set()),
    ("sus4", {0, 5, 7}, set()),
    ("sus2", {0, 2, 7}, set()),
    ("maj", {0, 4}, {7}),
    ("m", {0, 3}, {7}),
]

# spelled per key later would be better; for naming played chords the
# flat side reads most naturally on the bandstand
PC_NAME = {0: "C", 1: "Db", 2: "D", 3: "Eb", 4: "E", 5: "F", 6: "Gb",
           7: "G", 8: "Ab", 9: "A", 10: "Bb", 11: "B"}


def name_chord(pitches):
    """A set of sounding MIDI pitches -> a chord symbol, or None."""
    if not pitches:
        return None
    pcs = {p % 12 for p in pitches}
    bass = min(pitches) % 12
    best = None
    for root in sorted(pcs, key=lambda r: (r != bass,)):
        rel = {(p - root) % 12 for p in pcs}
        for qual, req, opt in TEMPLATES:
            if req <= rel and rel <= req | opt:
                score = (len(req & rel), -(len(rel - req)))
                cand = (score, root == bass, qual, root)
                if best is None or cand[:2] > best[:2]:
                    best = cand
                break        # templates are ordered most-specific-first
    if best is None:
        return None
    _, _, qual, root = best
    sym = PC_NAME[root] + ("" if qual == "maj" else qual)
    if bass != root:
        sym += "/" + PC_NAME[bass]
    return sym


def detect_bars(notes, barof, first, last, half_beat=None,
                half_ticks=None):
    """Name each bar's chord from played notes.  Returns (bars, misses):
    bars is a list of per-bar chord text in demo bar order, misses the
    bar numbers nothing could explain.

    Only ONSETS count — a voicing held across the barline restates as
    the same chord, which is the format's own way; counting held notes
    made the first test hallucinate mid-bar changes.  A bar splits in
    two only when a second onset cluster sits a genuine half-bar
    (half_ticks) after the first, and the second chord lands at
    half_beat."""
    by_bar = {}
    for n in notes:
        b = barof(n.on)
        if first <= b <= last:
            by_bar.setdefault(b, []).append(n)
    bars, misses = [], []
    prev = "nc"
    for b in range(first, last + 1):
        ns = by_bar.get(b, [])
        if not ns:
            bars.append(prev)      # a held chord restates — the format's way
            continue
        whole = name_chord({n.pitch for n in ns})
        split = None
        if half_beat and half_ticks:
            head_on = min(n.on for n in ns)
            late = [n for n in ns if n.on - head_on >= half_ticks * 0.9]
            early = [n for n in ns if n not in late]
            a = name_chord({n.pitch for n in early})
            z = name_chord({n.pitch for n in late})
            if a and z and a != z:
                split = f"{a} {z}@{half_beat}"
        if split:
            bars.append(split)
            prev = split.split("@")[0].split()[-1]
        elif whole:
            bars.append(whole)
            prev = whole
        else:
            bars.append("nc")
            misses.append(b)
    return bars, misses


def compress(bars):
    """['Bb7','Bb7','Eb7'] -> 'Bb7 x2, Eb7' — the way it's said."""
    out = []
    for b in bars:
        if out and out[-1][0] == b:
            out[-1][1] += 1
        else:
            out.append([b, 1])
    return ", ".join(b + (f" x{n}" if n > 1 else "") for b, n in out)


# ------------------------------------------------- forms it knows
#
# "Train it to write more, smarter" (Matthew, 2026-09-22): the
# conversation knows the common forms cold, transposed to any key —
# and always reads them back for a yes, never written unasked.

_RC_A = ("Bb6 G7@3, Cm7 F7@3, Bb6 G7@3, Cm7 F7@3, Fm7 Bb7@3, "
         "Eb6 Ebm6@3, Dm7 G7@3, Cm7 F7@3")

FORMS = {
    "blues": {"line": ("Bb7, Eb7, Bb7 x2, Eb7 x2, Bb7, Dm7 G7@3, "
                       "Cm7, F7, Bb7, F7"), "home": "Bb", "bars": 12},
    "minor blues": {"line": "Cm7 x4, Fm7 x2, Cm7 x2, Ab7, G7, Cm7, G7",
                    "home": "C", "bars": 12},
    # the canonical session changes; every variant is one edit away,
    # and the whole thing is offered for a yes before it's written
    "rhythm changes": {"home": "Bb", "bars": 32,
                       "sections": [("A", _RC_A), ("A2", _RC_A),
                                    ("B", "D7 x2, G7 x2, C7 x2, F7 x2"),
                                    ("A3", _RC_A)]},
}

# bandstand names for the same forms, folded in before parsing
FORM_ALIASES = {"i got rhythm": "rhythm changes",
                "rhythm change": "rhythm changes"}

# tune-level words a breath may carry: they belong to the header, not
# to any one section
FEELS = ("swing", "shuffle", "bossa nova", "bossa", "latin", "funk",
         "gospel", "ballad", "rock", "samba", "afro-cuban", "second line")


def extract_globals(text):
    """Pull the tune-level words out of a breath — feel, tempo, meter,
    key — so 'swing at 160, 8 bar intro' never becomes a 160-bar
    section called swing. Returns (remaining text, header updates)."""
    g = {}
    m = re.search(r"\bat\s+(\d{2,3})\b(?:\s*bpm)?", text, re.I)
    if not m:
        m = re.search(r"\b(\d{2,3})\s*bpm\b", text, re.I)
    if m:
        g["tempo"] = m.group(1)
        text = text[:m.start()] + text[m.end():]
    m = re.search(r"\bin\s+the\s+key\s+of\s+([a-g](?:\s+(?:flat|"
                  r"sharp))?(?:\s+minor)?)\b", text, re.I)
    if m:
        k = m.group(1)
        root = key_pc(k)
        names = PC_SHARP if "sharp" in k.lower() else PC_NAME
        g["key"] = names[root] + (" minor" if "minor" in k.lower()
                                  else "")
        text = text[:m.start()] + text[m.end():]
    m = re.search(r"\bin\s+(\d+)/(\d+)\b", text)
    if m:
        g["meter"] = f"{m.group(1)}/{m.group(2)}"
        text = text[:m.start()] + text[m.end():]
    elif re.search(r"\bwaltz\b", text, re.I):
        g["meter"] = "3/4"
        text = re.sub(r"\bwaltz\b", "", text, flags=re.I)
    for f in FEELS:
        if re.search(r"\b" + f + r"\b", text, re.I):
            g["feel"] = f
            text = re.sub(r"\b" + f + r"\b", "", text, flags=re.I)
            break
    return text, g

_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def key_pc(text):
    """'b flat', 'F#', 'Eb minor' -> pitch class, else None."""
    if not text:
        return None
    m = re.match(r"\s*([A-Ga-g])\s*(flat|sharp|b|#)?", text)
    if not m:
        return None
    alt = {"flat": -1, "b": -1, "sharp": 1, "#": 1}.get(
        (m.group(2) or "").lower(), 0)
    return (_PC[m.group(1).upper()] + alt) % 12


PC_SHARP = {0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F",
            6: "F#", 7: "G", 8: "G#", 9: "A", 10: "A#", 11: "B"}
SHARP_KEYS = {7, 2, 9, 4, 11, 6}         # G D A E B F#


def transpose_line(text, semis, names=PC_NAME):
    """Move every chord letter in a bars-grammar line by semitones."""
    def move(m):
        pc = (_PC[m.group(1)] + {'b': -1, '#': 1, '': 0}[m.group(2)]
              + semis) % 12
        return names[pc] + m.group(3)
    return re.sub(r"\b([A-G])([b#]?)([\w#@+.]*)", move, text)


def _form_key(kind, key_text, default_key):
    f = FORMS[kind]
    pc = key_pc(key_text)
    if pc is None:
        pc = key_pc(default_key) or 0
    sharp = pc in SHARP_KEYS or "#" in (key_text or "") or \
        "sharp" in (key_text or "").lower()
    names = PC_SHARP if sharp else PC_NAME
    return f, pc, (pc - key_pc(f["home"])) % 12, names


def known_changes(kind, key_text, default_key):
    """A one-line form and a key -> (chords line, bars, spoken name).
    Sharp-side keys spell sharp — a blues in B wants F#7, never Gb7."""
    f, pc, semis, names = _form_key(kind, key_text, default_key)
    master = f.get("line") or ", ".join(ln for _, ln in f["sections"])
    line = transpose_line(master, semis, names)
    return line, f["bars"], f"the {f['bars']}-bar {kind} in {names[pc]}"


def form_carve_sections(kind, key_text, default_key):
    """A carving form (rhythm changes) -> ([(name, line)], spoken)."""
    f, pc, semis, names = _form_key(kind, key_text, default_key)
    secs = [(nm, transpose_line(ln, semis, names))
            for nm, ln in f["sections"]]
    return secs, f"{kind} in {names[pc]}"


FORM_RE = re.compile(r"(?:(\d+)\s*bars?\s+)?(?:a\s+)?"
                     r"(minor blues|rhythm changes|blues)"
                     r"(?:\s+in\s+([a-g](?:\s+(?:flat|sharp))?))?\b")


# ------------------------------------------------ notes, spoken
#
# The fix-it tool from the design: one lick, said the way a player
# says it.  Durations stick until changed, octaves follow the line
# (nearest to the previous note; "up" or "down" forces the leap),
# and the output is the format's own notes: grammar — so the compiler
# validates the exact line the writer heard read back.

DUR_WORDS = {"whole": "w", "half": "h", "quarter": "q",
             "eighth": "e", "eighths": "e", "8th": "e",
             "sixteenth": "s", "sixteenths": "s", "16th": "s",
             "quarters": "q", "halves": "h", "wholes": "w"}

_NOTE_BASE = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}


def _dur_at(toks, i):
    """A duration at toks[i]: 'quarter', 'dotted half', 'e', 'q.' ->
    (dur string, tokens consumed), else (None, 0)."""
    if i >= len(toks):
        return None, 0
    t = toks[i].lower().rstrip(",")
    if t == "dotted" and i + 1 < len(toks):
        d, used = _dur_at(toks, i + 1)
        if d and not d.endswith("."):
            return d + ".", used + 1
        return None, 0
    if t in DUR_WORDS:
        return DUR_WORDS[t], 1
    if re.fullmatch(r"[whqes]\.?", t):
        return t, 1
    return None, 0


def notes_from_words(text):
    """'F4 quarter, G eighth, rest eighth, up B flat half' -> notes:
    grammar text.  Raises SpokenError on a word it cannot read."""
    toks = [t for t in text.replace(",", " ").split() if t]
    pieces = []
    prev_midi = None
    prev_dur = "q"
    dirn = None
    i = 0
    while i < len(toks):
        t = toks[i].lower()
        if t in ("up", "down"):
            dirn = t
            i += 1
            continue
        if t in ("rest", "rests"):
            i += 1
            d, used = _dur_at(toks, i)
            if d:
                i += used
            else:
                d = prev_dur
            prev_dur = d
            pieces.append(f"rest {d}")
            continue
        # a note name: 'f4', 'bb3', 'b flat 4', 'c sharp', 'g'
        m = re.fullmatch(r"([a-g])([b#]?)(-?\d)?", t)
        if not m:
            raise SpokenError(toks[i], text)
        letter, acc = m.group(1), m.group(2)
        octv = int(m.group(3)) if m.group(3) else None
        i += 1
        if not acc and i < len(toks) and \
                toks[i].lower().rstrip(",") in ("flat", "sharp"):
            acc = "b" if toks[i].lower().startswith("f") else "#"
            i += 1
        if octv is None and i < len(toks) and \
                re.fullmatch(r"-?\d", toks[i].rstrip(",")):
            octv = int(toks[i].rstrip(","))
            i += 1
        d, used = _dur_at(toks, i)
        if d:
            i += used
        else:
            d = prev_dur
        # ties: 'tied [to] eighth' / 'plus eighth'
        while i < len(toks) and toks[i].lower().rstrip(",") in \
                ("tied", "plus", "held"):
            j = i + 1
            if j < len(toks) and toks[j].lower() == "to":
                j += 1
            d2, used2 = _dur_at(toks, j)
            if not d2:
                raise SpokenError(toks[i], text)
            d += "+" + d2
            i = j + used2
        prev_dur = d.split("+")[-1].rstrip(".")
        pc = _NOTE_BASE[letter] + {"b": -1, "#": 1, "": 0}[acc]
        if octv is not None:
            midi = pc + (octv + 1) * 12
        elif prev_midi is None:
            midi = pc + 60 - (_NOTE_BASE["c"])  # around middle C
            midi = pc + 60 if pc <= 6 else pc + 48
        else:
            # nearest to the previous note; up/down force the leap
            cands = [pc + 12 * k for k in range(0, 10)]
            if dirn == "up":
                cands = [c for c in cands if c > prev_midi]
            elif dirn == "down":
                cands = [c for c in cands if c < prev_midi]
            midi = min(cands, key=lambda c: (abs(c - prev_midi), -c))
        dirn = None
        prev_midi = midi
        octave = midi // 12 - 1
        pieces.append(f"{letter.upper()}{acc}{octave} {d}")
    if not pieces:
        raise SpokenError(text.strip() or "(empty)", text)
    return ", ".join(pieces)


def notes_ticks(text):
    """Total ticks of a notes: line, via the compiler's own parser —
    or None with the error sentence when it refuses."""
    try:
        items, _, _ = chartc.parse_notes(text, "the line")
        return sum(t for t, _ in items), None
    except SystemExit as e:
        return None, str(e.code)


# ------------------------------------------------------- who plays

WHO_TARGET_ALIASES = {"everybody": "all", "everyone": "all",
                      "the band": "all", "band": "all",
                      "everybody else": "all", "the horns": "horns",
                      "the rhythm section": "rhythm",
                      "rhythm section": "rhythm"}

MELODY_WORDS = ("melody", "the melody", "has the melody",
                "plays the melody", "sings", "sings it",
                "sings the melody", "has it", "from the demo",
                "on the demo", "demo")


def parse_who(text, labels, groups, vocab=None, melody_range=None):
    """'horns tacet; bass walks, piano comps; voice sings the melody'
    -> directive lines, in bandstand language.  Raises SpokenError on
    a target or instruction it cannot read."""
    text = apply_vocab(text, vocab or {})
    chunks = []
    for semi in re.split(r";", text):
        # a hits list carries its own commas — never split those
        if re.search(r"\b(hits|kicks)\s+on\b", semi, re.IGNORECASE):
            chunks.append(semi)
        else:
            chunks.extend(re.split(
                r",|\band\b(?=\s+[\w ]+?\s+(?:tacet|groove|solo|from|"
                r"plays|walks|comps|lays|sits|sings|has|hits|kicks))",
                semi))
    lines = []
    for phrase in chunks:
        phrase = phrase.strip().strip(",").strip()
        if not phrase:
            continue
        toks = phrase.split()
        target = None
        for k in range(min(3, len(toks)), 0, -1):
            cand = " ".join(toks[:k]).lower()
            cand = WHO_TARGET_ALIASES.get(cand, cand)
            hit = next((l for l in list(labels) + list(groups)
                        if l.lower() == cand), None)
            if hit:
                target, rest = hit, toks[k:]
                break
        if not target:
            raise SpokenError(toks[0], phrase)
        r = " ".join(rest).lower().strip()
        r = re.sub(r"^(plays?|is|are)\s+", "", r)
        m = re.fullmatch(r"(?:hits|kicks)\s+on\s+(.+)", r)
        if m:
            lines.append(f"{target}: hits on {m.group(1)}")
        elif re.fullmatch(r"(?:comes?\s+)?in\s+at\s+(?:bar\s+)?\d+",
                          r):
            n = re.search(r"(\d+)", r).group(1)
            lines.append(f"build: add {target} at {n}")
        elif r in ("tacet", "out", "rests", "rest", "lays out",
                   "lay out", "sits out", "sit out", "sits this out"):
            lines.append(f"{target}: tacet")
        elif r in ("grooves", "groove", "time", "plays time", "plays",
                   "play", "walks", "walk", "comps", "comp", "in", ""):
            lines.append(f"{target}: groove")
        elif r in ("solo", "solos"):
            lines.append(f"{target}: solo")
        elif r in ("solo open", "solos open", "open solo"):
            lines.append(f"{target}: solo open")
        elif r in MELODY_WORDS:
            if melody_range is None:
                raise SpokenError(r, phrase)
            a, b = melody_range
            lines.append(f"{target}: from demo bars {a}-{b}")
        elif re.fullmatch(r"(from (the )?demo )?(bars? )?\d+\s*(-|to)"
                          r"\s*\d+", r):
            m = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)", r)
            lines.append(f"{target}: from demo bars "
                         f"{m.group(1)}-{m.group(2)}")
        else:
            raise SpokenError(r or phrase, phrase)
    return lines


# ------------------------------------------------- the chart on disk

def splice(path, keep_existing, prog_lines, section_lines,
           header=None):
    """Rewrite the chart: everything above the sections stays word for
    word (tune-level words from the breath land in the header); named
    progressions land just before the sections; sections are replaced
    (or kept, with the new ones after)."""
    src = open(path, encoding="utf-8").read().splitlines()
    head, sections, in_sec = [], [], False
    for line in src:
        top = line and line[0] not in " \t"
        if top and re.match(r"section\b", line.strip()):
            in_sec = True
        elif top and in_sec:
            in_sec = False          # a top-level line after the sections
        if in_sec:
            sections.append(line)
        else:
            head.append(line)
    while head and not head[-1].strip():
        head.pop()
    for k, v in (header or {}).items():
        head = set_header(head, k, v)
    out = head + [""]
    out += prog_lines + ([""] if prog_lines else [])
    if keep_existing and sections:
        out += sections + [""]
    out += section_lines
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")


def scaffold_only(chart):
    """True when the sections are still chartnew's untouched scaffold —
    nc bars and nothing else — safe to replace without asking."""
    if not chart["sections"]:
        return True
    for sec in chart["sections"]:
        for bar in sec.get("content") or []:
            for _, sym in bar:
                if sym is not None:
                    return False
        if sec.get("directives"):
            return False
    return True


# ------------------------------------------------- the conversation

def _ask_bars(plan):
    while plan["bars"] is None:
        a = ask(f"How many bars is the {plan['name']}")
        n = num(a)
        if n:
            plan["bars"] = n
        else:
            say(f"I need a number of bars for the {plan['name']}.")


def _carve(plan):
    """An AABA-shaped section carves into lettered 8s, or stays whole —
    his call, one question."""
    shape = plan["shape"].upper()
    n = len(plan["shape"])
    if plan["bars"] is None or plan["bars"] % n:
        return [plan]
    per = plan["bars"] // n
    a = ask(f"Carve the {plan['name']} into {n} {per}-bar sections "
            f"({', '.join(shape)}), or keep one "
            f"{plan['bars']}-bar section? carve or keep", "carve")
    if a.lower().startswith("k"):
        return [plan]
    parts, seen = [], {}
    for letter in shape:
        seen[letter] = seen.get(letter, 0) + 1
        nm = letter if seen[letter] == 1 else f"{letter}{seen[letter]}"
        parts.append(_mk(nm, bars=per))
        parts[-1]["family"] = plan["name"]
        parts[-1]["letter"] = letter
        parts[-1]["nth"] = seen[letter]
    return parts


def _chords_for(plan, ctx):
    """One section's chords, by whichever door he picks. Returns the
    chords text (bars grammar), validated to the section's length."""
    name, bars = plan["name"], plan["bars"]
    prior = {p["name"]: p for p in ctx["done"] if p.get("chords_text")}
    # a later A of a carved form defaults to the first A's changes
    twin = None
    if plan.get("letter") and plan.get("nth", 1) > 1:
        twin = next((p for p in ctx["done"]
                     if p.get("letter") == plan["letter"]
                     and p.get("nth") == 1), None)
    if twin and twin.get("chords_text"):
        a = ask(f"{name} — same changes as {twin['name']}? yes or no",
                "yes")
        if not a.lower().startswith("n"):
            return twin["chords_text"]
    if plan.get("section_line"):
        say(f"{name}: {plan['section_line']}")
        a = ctx["ask"]("Take those changes? yes or no", "yes")
        if not a.lower().startswith("n"):
            return plan["section_line"]
    if plan.get("form"):
        kind, keyword = plan["form"]
        line, fbars, spoken = known_changes(kind, keyword, ctx["key"])
        if fbars == bars:
            say(f"I know {spoken}: {line}")
            a = ctx["ask"]("Take those changes? yes or no", "yes")
            if not a.lower().startswith("n"):
                return line
    doors = "say them, 'play <midi file>', 'from demo'"
    if prior:
        doors += ", 'same as <section>'"
    while True:
        a = ask(f"Chords for {name} ({bars} bars) — {doors}, or Enter "
                "for none yet")
        if not a:
            return f"nc x{bars}" if bars > 1 else "nc"
        m = re.fullmatch(r"same as (.+)", a.strip(), re.IGNORECASE)
        if m:
            src = m.group(1).strip().lower()
            hit = next((p for p in ctx["done"]
                        if p["name"].lower() == src
                        and p.get("chords_text")), None)
            if hit:
                if hit["bars"] == bars:
                    return hit["chords_text"]
                say(f"{hit['name']} is {hit['bars']} bars and {name} "
                    f"is {bars} — they can't share changes whole.")
            else:
                say(f"No section called '{m.group(1).strip()}' has "
                    "chords yet.")
            continue
        low_a = a.strip().lower()
        for alias, real in FORM_ALIASES.items():
            low_a = re.sub(r"\b" + re.escape(alias) + r"\b", real,
                           low_a)
        fm = re.fullmatch(r"(?:(\d+)\s*bars?\s+)?(?:a\s+)?"
                          r"(minor blues|rhythm changes|blues)"
                          r"(?:\s+in\s+(.+))?", low_a)
        if fm:
            kind = fm.group(2)
            line, fbars, spoken = known_changes(kind, fm.group(3),
                                                ctx["key"])
            if fbars != bars:
                say(f"{spoken} is {fbars} bars and {name} is {bars} — "
                    "another door, then.")
                continue
            say(f"I know {spoken}: {line}")
            yn = ctx["ask"]("Take those changes? yes or no", "yes")
            if yn.lower().startswith("n"):
                continue
            return line
        if a.lower().startswith("play "):
            text = _detect_from_file(a[5:].strip(), bars, ctx)
        elif a.lower().startswith("from demo"):
            text = _detect_from_demo(a, plan, ctx)
        else:
            text = _spoken(a, ctx)
        if text is None:
            continue
        try:
            got = len(chartc.parse_bars(text, name))
        except SystemExit as e:
            say(f"That didn't parse: {e.code}")
            continue
        if got != bars:
            say(f"That's {got} bars and {name} is {bars} — same door, "
                "try again.")
            continue
        return text


def _spoken(a, ctx):
    while True:
        try:
            return parse_spoken_chords(a, ctx["vocab"],
                                       key=ctx["key"])
        except SpokenError as e:
            meaning = learn(e.word, ctx["vocab"], asker=ctx["ask"])
            if not meaning:
                return None


def _detect_from_file(fname, bars, ctx):
    """He played the changes into a MIDI file; name them and read them
    back for his yes."""
    tries = [fname, os.path.join(ctx["base"], fname)]
    if ctx["cfg"].get("midi"):
        tries.append(os.path.join(
            os.path.expanduser(ctx["cfg"]["midi"]), fname))
    path = next((t for t in tries if os.path.exists(t)), None)
    if path is None:
        where = " or the midi folder" if ctx["cfg"].get("midi") else ""
        say(f"No file called {fname} beside the chart{where}.")
        return None
    dm = chartdemo.Demo(path)
    notes = [n for ns in dm.tracks.values() for n in ns]
    if not notes:
        say(f"{fname} has no notes.")
        return None
    barof = dm.bar_of
    first = min(barof(n.on) for n in notes)
    last = barof(max(n.off or n.on for n in notes))
    nm, dn = ctx["meter"]
    got, misses = detect_bars(notes, barof, first, last,
                              half_beat=ctx["half_beat"],
                              half_ticks=dm.division * 4 * nm // dn // 2)
    got = got[:bars]
    line = compress(got)
    say(f"I hear: {line}")
    if misses:
        say("Couldn't name bar(s) " +
            ", ".join(str(b) for b in misses) + " — they land as the "
            "held chord; fix by voice if that's wrong.")
    a = ctx["ask"]("Use these? yes or no", "yes")
    return line if not a.lower().startswith("n") else None


def _detect_from_demo(a, plan, ctx):
    """Lift the changes from a comping track of the chart's own demo."""
    if ctx["demo"] is None:
        say("This chart names no demo to lift from.")
        return None
    dm = ctx["demo"]
    m = re.search(r'from demo\s*(?:"([^"]+)"|([\w ]+?))?\s*'
                  r'(?:bars?\s+(\d+)\s*-\s*(\d+))?$', a.strip())
    track = (m.group(1) or (m.group(2) or "").strip()) if m else ""
    names = {dm.names.get(ti, f"track {ti}").strip(): ti
             for ti in sorted(dm.tracks)}
    if track:
        ti = next((v for k, v in names.items()
                   if k.lower() == track.lower()), None)
        if ti is None:
            say("The demo's tracks are: " + ", ".join(names) + ".")
            return None
    elif len(names) == 1:
        ti = next(iter(names.values()))
    else:
        say("Which track? The demo has: " + ", ".join(names) + ".")
        return None
    if m and m.group(3):
        first, last = int(m.group(3)), int(m.group(4))
    else:
        first = plan["start_demo"]
        last = first + plan["bars"] - 1
    nm, dn = ctx["meter"]
    got, misses = detect_bars(dm.tracks[ti], dm.bar_of, first, last,
                              half_beat=ctx["half_beat"],
                              half_ticks=dm.division * 4 * nm // dn // 2)
    line = compress(got)
    say(f"From the demo, bars {first}-{last}: {line}")
    if misses:
        say("Couldn't name bar(s) " +
            ", ".join(str(b) for b in misses) + ".")
    ans = ctx["ask"]("Use these? yes or no", "yes")
    return line if not ans.lower().startswith("n") else None


def _who_for(plan, ctx):
    """Who plays this section — directives, defaults stated."""
    if plan["kind"] == "solos":
        while True:
            a = ask(f"Who solos in {plan['name']}? part names, comma "
                    "separated, or Enter for nobody named")
            if not a:
                return []
            picks, ok = [], True
            for name in [x.strip() for x in a.split(",") if x.strip()]:
                hit = next((l for l in ctx["labels"] + ctx["groupnames"]
                            if l.lower() == name.lower()), None)
                if hit:
                    picks.append(f"{hit}: solo" +
                                 (" open" if plan["open"] else ""))
                else:
                    say(f"'{name}' is not in this band. The band is: "
                        + ", ".join(ctx["labels"]) + ".")
                    ok = False
                    break
            if ok:
                return picks
    while True:
        a = ask(f"Who plays in {plan['name']}? like 'horns tacet; "
                "trumpet from demo bars 5-12', or Enter for the "
                "defaults (rhythm grooves, horns tacet)")
        if not a:
            return []
        while True:
            try:
                rng = None
                if ctx["demo"] and plan.get("start_demo") and \
                        plan.get("bars"):
                    rng = (plan["start_demo"],
                           plan["start_demo"] + plan["bars"] - 1)
                lines = parse_who(a, ctx["labels"], ctx["groupnames"],
                                  ctx["vocab"], melody_range=rng)
                # his standing quant setting rides every from-demo lift
                q = ctx["cfg"].get("quant")
                if q:
                    lines = [ln + f", {q}" if "from demo bars" in ln
                             else ln for ln in lines]
                return lines
            except SpokenError as e:
                if e.word in MELODY_WORDS:
                    say("This chart names no demo to lift the melody "
                        "from — name bars, or another instruction.")
                    break
                # a chords-shaped answer on a who question must not
                # teach the vocabulary that 'b' means something
                try:
                    parse_spoken_chords(a, ctx["vocab"])
                    say(f"Those read as chords — this question is who "
                        f"PLAYS in {plan['name']}; its chords are "
                        "already set.")
                    break
                except SpokenError:
                    pass
                if not learn(e.word, ctx["vocab"], asker=ctx["ask"]):
                    say("Skipping that line, then — the band is: "
                        + ", ".join(ctx["labels"]) + ".")
                    break


def edit(path, demo=None, composer="", cfg=None):
    """The roadmap conversation, start to written chart."""
    cfg = cfg or {}
    if not os.path.exists(path):
        import chartnew
        say("No chart there yet — the interview first, then the "
            "roadmap.")
        chartnew.interview(path, demo, composer=composer, cfg=cfg)
    try:
        chart = chartc.parse_chart(path)
    except SystemExit as e:
        sys.exit(f"chart: this chart doesn't compile yet, and the "
                 f"roadmap needs a clean read: {e.code}")
    base = os.path.dirname(os.path.abspath(path))
    labels = [b["label"] for b in chart["band"]]
    groups = chartc.resolve_groups(chart["band"], chart["groups"])
    groupnames = [g for g in groups if groups[g]]
    meter = chartc.parse_meter(chart["header"].get("meter", "4/4"))
    countin = int(chart["header"].get("countin", 0) or 0)
    dm = None
    if chart["header"].get("demo"):
        p = os.path.join(base, chart["header"]["demo"])
        if os.path.exists(p):
            dm = chartdemo.Demo(p)
    vocab = load_vocab()
    ctx = {"vocab": vocab, "labels": labels, "groupnames": groupnames,
           "demo": dm, "base": base, "ask": ask, "done": [],
           "meter": meter, "cfg": cfg,
           "key": chart["header"].get("key", "C"),
           # a two-chord bar's second chord lands mid-bar
           "half_beat": meter[0] // 2 + 1 if meter[0] >= 4 and
           meter[0] % 2 == 0 else None}

    ctx["countin"] = countin
    ctx["path"] = path

    if not scaffold_only(chart):
        if run_commands(path, ctx) != "replace":
            return
    _new_form(path, ctx)


# ---------------------------------------------- the new-form road

def _gather_plans(ctx):
    """The breath, its tune-level words, the gaps, the guided walk."""
    vocab = ctx["vocab"]
    say("Tell me the tune in one breath — sections in order, like "
        "'8 bar intro, head is 32 AABA, solos over the head twice, "
        "out on the last A'. Or press Enter and I'll ask one section "
        "at a time.")
    breath = ask("The tune")
    hdr = {}
    if breath:
        breath, hdr = extract_globals(breath)
        if hdr:
            say("Tune-level: " +
                "; ".join(f"{k} {v}" for k, v in hdr.items()) + ".")
    plans, gaps = (parse_form(breath, vocab) if breath.strip()
                   else ([], []))
    if plans:
        bits = []
        for p in plans:
            b = p["name"]
            if p["bars"]:
                b += f" {p['bars']}"
            if p["shape"]:
                b += f" {p['shape'].upper()}"
            if p.get("form"):
                b += f" ({p['form'][0]})"
            if p["use"]:
                b += f" over the {p['use']}"
            if p["repeat"] > 1:
                b += f" x{p['repeat']}"
            if p["open"]:
                b += " open"
            bits.append(b)
        say("Placed: " + "; ".join(bits) + ".")
    _resolve_gaps(plans, gaps, vocab)
    if not plans:
        # the guided walk — he pressed Enter, it leads
        while True:
            nm = ask("Next section — its name, like intro or A "
                     "(Enter to finish)")
            if not nm:
                break
            p = parse_clause(digitize(apply_vocab(nm, vocab))) or \
                _mk(nm)
            plans.append(p)
    return plans, hdr


def _resolve_gaps(plans, gaps, vocab):
    for g in gaps:
        while True:
            a = ask(f"I couldn't place '{g}'. Say it another way, or "
                    "Enter to drop it")
            if not a:
                break
            p = parse_clause(digitize(apply_vocab(a, vocab)))
            if p:
                plans.append(p)
                break
            say("Still can't place that — a section is a name and a "
                "length, like 'shout 16'.")


def _shape_plans(ctx, plans, existing=()):
    """Bars first, repeated names numbered (verse, verse 2), shapes
    and known forms carved.  Returns (plans, named families)."""
    named = {}
    for p in plans:
        if p["kind"] == "solos" and p["bars"] is None and p["use"]:
            continue                      # inherits its form's length
        if p["kind"] == "out" and p["bars"] is None and p["source"]:
            continue
        _ask_bars(p)
    # a pop form repeats its names; number them so nothing collides,
    # and the second verse can offer the first verse's changes
    used = {str(n).lower() for n in existing}
    renamed = False
    for p in plans:
        base, k, name = p["name"], 1, p["name"]
        while name.lower() in used:
            k += 1
            name = f"{base} {k}"
        used.add(name.lower())
        if name != base:
            renamed = True
        p.setdefault("letter", base)
        p.setdefault("nth", k)
        p["name"] = name
    if renamed:
        say("Repeated names numbered themselves: " +
            "; ".join(p["name"] for p in plans) + ".")
    carved = []
    for p in plans:
        kind = (p.get("form") or (None,))[0]
        if kind and "sections" in FORMS.get(kind, {}):
            secs, spoken = form_carve_sections(kind, p["form"][1],
                                               ctx["key"])
            per = (p["bars"] or FORMS[kind]["bars"]) // len(secs)
            fam = []
            for nm, line in secs:
                q = _mk(nm, bars=per)
                q["section_line"] = line
                q["letter"] = nm[0]
                q["nth"] = int(nm[1:]) if len(nm) > 1 else 1
                fam.append(q)
            named[p["name"]] = fam
            say(f"{spoken} carves itself: " +
                ", ".join(nm for nm, _ in secs) + f" — {per} bars "
                "each.")
            carved.extend(fam)
        elif p["shape"]:
            fam = _carve(p)
            if len(fam) > 1:
                named[p["name"]] = fam
            carved.extend(fam)
        else:
            carved.append(p)
    return carved, named


def _start_demo(plans, countin, start_bar=1):
    """Where each section starts in his DAW's numbering."""
    start = start_bar
    for p in plans:
        p["start_demo"] = start + countin
        if p["bars"]:
            start += p["bars"]


def _realize_plans(ctx, plans, named, extra=()):
    """Chords, section by section, then who plays.  `extra` holds
    already-written sections a new solos/out may lean on."""
    pool = list(plans) + list(extra)
    for p in plans:
        if p["kind"] == "solos":
            src = _resolve_family(p["use"], pool, named)
            if src:
                p["use_sections"] = src
                p["bars"] = sum(s["bars"] for s in src)
                # the progression carries the family's real name, not
                # the word that reached it ("the form")
                real = next((k for k, v in named.items()
                             if v is src), None)
                p["use"] = real or src[0]["name"]
            else:
                if p["use"]:
                    say(f"I don't see a section called '{p['use']}' "
                        "to solo over — I'll ask for the changes.")
                _ask_bars(p)
                p["chords_text"] = _chords_for(p, ctx)
        elif p["kind"] == "out":
            src = _resolve_out(p, pool, named)
            if src:
                p["bars"] = src["bars"]
                p["chords_text"] = src.get("chords_text") or \
                    f"nc x{p['bars']}"
            else:
                if p["source"]:
                    say(f"I couldn't read 'out on the {p['source']}' "
                        "against the sections I have — I'll ask.")
                _ask_bars(p)
                p["chords_text"] = _chords_for(p, ctx)
        else:
            p["chords_text"] = _chords_for(p, ctx)
        ctx["done"].append(p)
        p["who"] = _who_for(p, ctx)


def _report(path):
    try:
        final = chartc.parse_chart(path)
    except SystemExit as e:
        say(f"Written, but the check found: {e.code}")
        say(f"The file is {path} — say the word and we fix it "
            "together.")
        return None
    total = 0
    for sec in final["sections"]:
        total += sec["bars"] * max(sec.get("repeat") or 1, 1)
    say(f"Written and checked: {len(final['sections'])} section(s), "
        f"{total} bars through the form. Next: chart build, and "
        "you'll hear it.")
    return final


def _new_form(path, ctx):
    plans, hdr = _gather_plans(ctx)
    if not plans:
        sys.exit("chart: no sections described, nothing written.")
    if hdr.get("key"):
        # "in the key of e flat" then "1 4 5 1" must land in E flat
        ctx["key"] = hdr["key"]
    plans, named = _shape_plans(ctx, plans)
    _start_demo(plans, ctx["countin"])
    _realize_plans(ctx, plans, named)
    prog_lines, section_lines = render(plans, named)
    splice(path, False, prog_lines, section_lines, header=hdr)
    # a replaced form's named progressions may now reference nothing;
    # stale changes on the page are worse than a clean drop
    lines = _lines(path)
    used = set(re.findall(r"^\s*use chords ([\w ]+?)(?:\s+x\d+)?\s*$",
                          "\n".join(lines), re.MULTILINE))
    kept, dropped = [], []
    for l in lines:
        m = re.match(r"chords ([\w ]+?):", l) \
            if l and l[0] not in " \t" else None
        if m and m.group(1).strip() not in used:
            dropped.append(m.group(1).strip())
            continue
        kept.append(l)
    if dropped:
        _save_lines(path, kept)
        say("Dropped old changes nothing uses now: "
            + ", ".join(dropped) + ".")
    _report(path)


# --------------------------------------- editing an existing chart
#
# The sledgehammer question ("keep or replace?") grew into a desk: a
# chart with real sections opens on what-are-we-doing, and each move
# lands in the file at once, checked by the same parser as always.

def _lines(path):
    return open(path, encoding="utf-8").read().splitlines()


def _save_lines(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")


def _section_span(lines, name):
    """The [start, end) line span of one section's block, trailing
    blanks included."""
    pat = re.compile(r"section\s+" + re.escape(name) + r"\s*(,|$)",
                     re.IGNORECASE)
    start = None
    for i, l in enumerate(lines):
        if l and l[0] not in " \t" and pat.match(l.strip()):
            start = i
            break
    if start is None:
        return None
    j = start + 1
    while j < len(lines) and (not lines[j] or lines[j][0] in " \t"):
        j += 1
    return (start, j)


def set_header(lines, key, value):
    """Replace a top-level 'key: value' header line, or insert one
    before the band block."""
    for i, l in enumerate(lines):
        if l and l[0] not in " \t" and \
                re.match(key + r":\s", l.strip() + " "):
            lines[i] = f"{key}: {value}"
            return lines
    at = next((i for i, l in enumerate(lines)
               if l.strip() == "band:"), 0)
    while at > 0 and not lines[at - 1].strip():
        at -= 1                    # sit with the header, not adrift
    lines.insert(at, f"{key}: {value}")
    return lines


def _sec_plan(chart, name, ctx):
    """A plan dict for one already-written section, DAW numbering
    included, or None."""
    start = 1
    for s in chart["sections"]:
        if s["name"].lower() == name.lower():
            return {"name": s["name"], "bars": s["bars"],
                    "kind": "plain", "repeat": max(s.get("repeat")
                                                   or 1, 1),
                    "open": False, "use": None, "source": None,
                    "shape": None,
                    "start_demo": start + ctx["countin"]}
        start += s["bars"]
    return None


def _raw_chords(lines, name):
    """The raw chords text a section carries — its own line, or the
    named progression it uses."""
    span = _section_span(lines, name)
    if not span:
        return None
    for i in range(span[0] + 1, span[1]):
        s = lines[i].strip()
        m = re.match(r"chords:\s*(.+)$", s)
        if m:
            return m.group(1)
        m = re.match(r"use chords ([\w ]+?)(?:\s+x\d+)?$", s)
        if m:
            for l in lines:
                if l and l[0] not in " \t":
                    d = re.match(r"chords " + re.escape(m.group(1))
                                 + r":\s*(.+)$", l.strip())
                    if d:
                        return d.group(1)
    return None


def transpose_chart(path, target, current_key):
    """Move the key and every chord symbol; played material stays as
    played, and the caller says so out loud."""
    tpc = key_pc(target)
    semis = (tpc - (key_pc(current_key) or 0)) % 12
    sharp = tpc in SHARP_KEYS or "sharp" in target.lower() or \
        "#" in target
    names = PC_SHARP if sharp else PC_NAME
    lines = _lines(path)
    out = []
    for l in lines:
        s = l.strip()
        m = re.match(r"^(\s*)(ending\s+\d+,\s*\d+\s*bars?:\s*chords:"
                     r"\s*)(.+)$", l, re.IGNORECASE)
        if m:
            out.append(m.group(1) + m.group(2)
                       + transpose_line(m.group(3), semis, names))
            continue
        m = re.match(r"^(\s*)(chords(?:\s+[\w ]+)?:\s*)(.+)$", l)
        if m and not s.startswith("use "):
            out.append(m.group(1) + m.group(2)
                       + transpose_line(m.group(3), semis, names))
            continue
        m = re.match(r"^key:\s*([A-Ga-g][b#]?)(.*)$", l)
        if m and l[0] not in " \t":
            pc = (key_pc(m.group(1)) + semis) % 12
            out.append(f"key: {names[pc]}{m.group(2)}")
            continue
        out.append(l)
    _save_lines(path, out)
    return names[tpc]


def _set_section_chords(lines, span, text):
    for i in range(span[0] + 1, span[1]):
        s = lines[i].strip()
        if s.startswith("chords:") or s.startswith("use chords"):
            lines[i] = "  chords: " + text
            return lines
    lines.insert(span[0] + 1, "  chords: " + text)
    return lines


def _set_section_who(lines, span, who, heads):
    """Replace a section's part directives, leaving chords, feel,
    events and endings where they stand."""
    body = []
    for i in range(span[0] + 1, span[1]):
        s = lines[i].strip()
        m = re.match(r"([\w ]+?):", s)
        if m and m.group(1).strip().lower() in heads:
            continue
        body.append(lines[i])
    while body and not body[-1].strip():
        body.pop()
    new = lines[:span[0] + 1] + body + \
        ["  " + w for w in who] + [""] + lines[span[1]:]
    return new


def _add_sections(path, ctx, text, after):
    chart = chartc.parse_chart(path)
    existing = [s["name"] for s in chart["sections"]]
    plans, gaps = parse_form(text, ctx["vocab"])
    _resolve_gaps(plans, gaps, ctx["vocab"])
    if not plans:
        say("Nothing to add, then.")
        return
    plans, named = _shape_plans(ctx, plans, existing=existing)
    total = sum(s["bars"] for s in chart["sections"])
    _start_demo(plans, ctx["countin"], total + 1)
    lines = _lines(path)
    extra = []
    for s in chart["sections"]:
        e = _sec_plan(chart, s["name"], ctx)
        e["chords_text"] = _raw_chords(lines, s["name"])
        e["letter"], e["nth"] = s["name"], 1
        extra.append(e)
    _realize_plans(ctx, plans, named, extra=extra)
    prog_lines, section_lines = render(plans, named)
    lines = _lines(path)
    if after:
        span = _section_span(lines, after)
        at = span[1] if span else len(lines)
    else:
        at = len(lines)
    block = ([""] if at and lines[at - 1:at] != [""] else []) + \
        prog_lines + ([""] if prog_lines else []) + section_lines
    lines[at:at] = block
    _save_lines(path, lines)
    say("Added: " + "; ".join(f"{p['name']} {p['bars']}"
                              for p in plans) + ".")


def _rest_pieces(ticks):
    """Rests that fill this many ticks, or None when they can't."""
    out = []
    for letter, t in (("h", 48), ("q", 24), ("e", 12), ("s", 6)):
        while ticks >= t:
            out.append(f"rest {letter}")
            ticks -= t
    return ", ".join(out) if out and ticks == 0 else None


def _figure_from_file(fname, ctx):
    """A played lick from a MIDI file -> (figure source line, bars,
    spoken description), or None."""
    tries = [fname, os.path.join(ctx["base"], fname)]
    if ctx["cfg"].get("midi"):
        tries.append(os.path.join(
            os.path.expanduser(ctx["cfg"]["midi"]), fname))
    p = next((t for t in tries if os.path.exists(t)), None)
    if p is None:
        say(f"No file called {fname} beside the chart"
            + (" or the midi folder" if ctx["cfg"].get("midi")
               else "") + ".")
        return None
    dm = chartdemo.Demo(p)
    names = [dm.names.get(ti, f"track {ti}").strip()
             for ti in sorted(dm.tracks)]
    track = None
    if len(names) > 1:
        say("That file has tracks: " + ", ".join(names) + ".")
        want = ask("Which one")
        track = next((n for n in names
                      if n.lower() == want.lower()), None)
        if track is None:
            say("Didn't find that track.")
            return None
        notes = dm.tracks[[ti for ti in sorted(dm.tracks)
                           if dm.names.get(ti, "").strip() == track][0]]
    else:
        notes = next(iter(dm.tracks.values()))
    last = max((n.off or n.on) for n in notes)
    bars = dm.bar_of(max(0, last - 1))
    rel = os.path.relpath(p, ctx["base"])
    line = f'  from midi "{rel}"'
    if track:
        line += f', track "{track}"'
    line += f", bars 1-{bars}"
    return line, bars, f"{bars} bar(s) played in " \
        f"{os.path.basename(p)}"


def _notes_for(path, ctx, chart, part_text, sec_text):
    """One lick into a real figure — said, typed in the notes
    grammar, or played into a MIDI file — placed at a bar of a
    section."""
    target = next((l for l in ctx["labels"] + ctx["groupnames"]
                   if l.lower() == part_text.lower()), None)
    if target is None:
        say(f"'{part_text}' is not in this band — the band is: "
            + ", ".join(ctx["labels"]) + ".")
        return
    plan = _sec_plan(chart, sec_text, ctx)
    if plan is None:
        say(f"No section called '{sec_text}'.")
        return
    nm, dn = ctx["meter"]
    bar_ticks = 96 * nm // dn
    while True:
        a = ask(f"The line for {target} in {plan['name']} — like "
                "'F4 quarter, G eighth, rest eighth, B flat half', "
                "or 'play <file.mid>' (Enter to drop it)")
        if not a:
            return
        if a.lower().startswith("play "):
            got = _figure_from_file(a[5:].strip(), ctx)
            if got is None:
                continue
            source_line, fig_bars, described = got
        else:
            text_out = a
            total, err = notes_ticks(text_out)
            if err is not None:
                try:
                    text_out = notes_from_words(
                        apply_vocab(a, ctx["vocab"]))
                except SpokenError as e:
                    say(f"Couldn't read '{e.word}' — a note is like "
                        "'B flat 3 quarter'; durations stick until "
                        "you change them.")
                    continue
                total, err = notes_ticks(text_out)
                if err is not None:
                    say(err)
                    continue
            if total % bar_ticks:
                rests = _rest_pieces(bar_ticks - total % bar_ticks)
                if rests is None:
                    say("That doesn't land on a barline and rests "
                        "can't square it — check the durations.")
                    continue
                yn = ask(f"That's {total / 24:g} beats — pad with "
                         "rests to the barline? yes or no", "yes")
                if yn.lower().startswith("n"):
                    continue
                text_out += ", " + rests
                total += bar_ticks - total % bar_ticks
            fig_bars = total // bar_ticks
            source_line = f"  notes: {text_out}"
            described = text_out
        start = ask(f"Starting at which bar of {plan['name']}? 1 to "
                    f"{plan['bars']}", "1")
        b0 = num(start) or 1
        if b0 < 1 or b0 - 1 + fig_bars > plan["bars"]:
            say(f"{fig_bars} bar(s) starting at bar {b0} runs past "
                f"{plan['name']}'s {plan['bars']} — pick again.")
            continue
        name = f"{target} {plan['name']} bar {b0}"
        k = 2
        while name in chart["figures"]:
            name = f"{target} {plan['name']} bar {b0} take {k}"
            k += 1
        say(f"{name}, {fig_bars} bar(s): {described}")
        yn = ask("Write it? yes or no", "yes")
        if yn.lower().startswith("n"):
            continue
        lines = _lines(path)
        at = next((i for i, l in enumerate(lines)
                   if l and l[0] not in " \t"
                   and l.strip().startswith("section ")), len(lines))
        lines[at:at] = [f"figure {name}, {fig_bars} bars:",
                        source_line, ""]
        span = _section_span(lines, plan["name"])
        place = f"  {target}: figure {name}"
        if b0 > 1:
            place += f" at bar {b0}"
        j = span[1]
        while j > span[0] + 1 and not lines[j - 1].strip():
            j -= 1
        lines.insert(j, place)
        _save_lines(path, lines)
        say(f"{target} plays it in {plan['name']} — chart build to "
            "hear it.")
        return


def run_commands(path, ctx):
    """The editing desk. Returns 'done', or 'replace' to hand the
    chart to the fresh-form road."""
    heads = {l.lower() for l in ctx["labels"]} | \
        {g.lower() for g in ctx["groupnames"]}
    shown = False
    while True:
        try:
            chart = chartc.parse_chart(path)
        except SystemExit as e:
            say(f"The chart stopped parsing: {e.code}")
            return "done"
        secs = chart["sections"]
        summary = "; ".join(
            f"{s['name']} {s['bars']}"
            + (f" x{s['repeat']}" if s.get("repeat") else "")
            for s in secs)
        if not shown:
            say(f"This chart has {len(secs)} section(s): {summary}.")
            say("Say what to do: chords of <section> / who plays in "
                "<section> / notes for <part> in <section> / add "
                "<new sections> / cut <section> / rename <section> "
                "to <name> / repeat <section> N times / make "
                "<section> open / tempo <number> / feel <words> / "
                "transpose to <key> / read it back / replace the "
                "form. Enter when done.")
            shown = True
        a = ask("What are we doing").strip()
        if not a or a.lower() in ("done", "nothing", "quit", "stop"):
            return "done"
        low = apply_vocab(a, ctx["vocab"]).lower().strip()
        if low in ("help", "?"):
            shown = False
            continue
        if low.startswith("replace"):
            return "replace"
        if low in ("read it back", "read", "what's there",
                   "whats there", "what is there"):
            total = sum(s["bars"] * max(s.get("repeat") or 1, 1)
                        for s in secs)
            say(f"{len(secs)} section(s): {summary} — {total} bars "
                "through the form.")
            continue
        m = re.fullmatch(r"tempo\s+(.+)", low)
        if m:
            _save_lines(path, set_header(_lines(path), "tempo",
                                         m.group(1)))
            say(f"Tempo is now {m.group(1)}.")
            continue
        m = re.fullmatch(r"feel\s+(.+)", low)
        if m:
            _save_lines(path, set_header(_lines(path), "feel",
                                         m.group(1)))
            say(f"Feel is now {m.group(1)}.")
            continue
        m = re.fullmatch(r"transpose(?:\s+(?:to|into))?\s+(.+)", low)
        if m:
            if key_pc(m.group(1)) is None:
                say(f"I can't read '{m.group(1)}' as a key.")
                continue
            src = open(path, encoding="utf-8").read()
            if "demo" in src or "from midi" in src or "notes:" in src:
                say("Your played material stays as played — this "
                    "moves the key and every chord symbol only.")
            yn = ask(f"Transpose the whole chart to {m.group(1)}? "
                     "yes or no", "yes")
            if yn.lower().startswith("n"):
                continue
            newkey = transpose_chart(path, m.group(1),
                                     chart["header"].get("key", "C"))
            ctx["key"] = newkey
            say(f"Done — the chart is in {newkey} now.")
            continue
        m = re.fullmatch(r"(?:change\s+)?(?:the\s+)?chords\s+"
                         r"(?:of|for|in)\s+(?:the\s+)?(.+)", low)
        if m:
            plan = _sec_plan(chart, m.group(1).strip(), ctx)
            if not plan:
                say(f"No section called '{m.group(1).strip()}'. "
                    f"The sections are: {summary}.")
                continue
            text = _chords_for(plan, ctx)
            lines = _lines(path)
            span = _section_span(lines, plan["name"])
            _save_lines(path, _set_section_chords(lines, span, text))
            say(f"{plan['name']} now plays: {text}")
            continue
        m = re.fullmatch(r"who(?:\s+plays)?(?:\s+in)?\s+"
                         r"(?:the\s+)?(.+)", low)
        if m:
            plan = _sec_plan(chart, m.group(1).strip(), ctx)
            if not plan:
                say(f"No section called '{m.group(1).strip()}'. "
                    f"The sections are: {summary}.")
                continue
            who = _who_for(plan, ctx)
            lines = _lines(path)
            span = _section_span(lines, plan["name"])
            _save_lines(path, _set_section_who(lines, span, who,
                                               heads))
            say(f"{plan['name']}: " + ("; ".join(who) if who
                                       else "back to the defaults") + ".")
            continue
        m = re.fullmatch(r"cut\s+(?:the\s+)?(.+)", low)
        if m:
            plan = _sec_plan(chart, m.group(1).strip(), ctx)
            if not plan:
                say(f"No section called '{m.group(1).strip()}'.")
                continue
            yn = ask(f"Cut {plan['name']} ({plan['bars']} bars)? "
                     "yes or no", "no")
            if not yn.lower().startswith("y"):
                continue
            lines = _lines(path)
            span = _section_span(lines, plan["name"])
            _save_lines(path, lines[:span[0]] + lines[span[1]:])
            say(f"{plan['name']} is out.")
            continue
        m = re.fullmatch(r"add\s+(.+)", low)
        if m:
            rest = m.group(1)
            after = None
            am = re.search(r"\s+after\s+(?:the\s+)?([\w ]+)$", rest)
            if am and _section_span(_lines(path),
                                    am.group(1).strip()):
                after = am.group(1).strip()
                rest = rest[:am.start()]
            _add_sections(path, ctx, rest, after)
            continue
        m = re.fullmatch(r"notes\s+for\s+([\w ]+?)\s+in\s+"
                         r"(?:the\s+)?(.+)", low)
        if m:
            _notes_for(path, ctx, chart, m.group(1).strip(),
                       m.group(2).strip())
            continue
        m = re.fullmatch(r"rename\s+(?:the\s+)?([\w ]+?)\s+to\s+"
                         r"([\w ]+)", low)
        if m:
            lines = _lines(path)
            span = _section_span(lines, m.group(1).strip())
            if not span:
                say(f"No section called '{m.group(1).strip()}'.")
                continue
            hm = re.match(r"(\s*section\s+)[\w ]+?(\s*(?:,.*)?)$",
                          lines[span[0]])
            lines[span[0]] = hm.group(1) + m.group(2).strip() + \
                hm.group(2)
            _save_lines(path, lines)
            say(f"{m.group(1).strip()} is called "
                f"{m.group(2).strip()} now.")
            continue
        m = re.fullmatch(r"repeat\s+(?:the\s+)?([\w ]+?)\s+"
                         r"(\d+)\s*(?:times|x)?", low)
        if m:
            lines = _lines(path)
            span = _section_span(lines, m.group(1).strip())
            if not span:
                say(f"No section called '{m.group(1).strip()}'.")
                continue
            head_line = lines[span[0]]
            if re.search(r"repeat \d+x", head_line):
                head_line = re.sub(r"repeat \d+x",
                                   f"repeat {m.group(2)}x", head_line)
            else:
                head_line = re.sub(r"(section [\w ]+?, \d+ bars)",
                                   r"\1, repeat " + m.group(2) + "x",
                                   head_line)
            lines[span[0]] = head_line
            _save_lines(path, lines)
            say(f"{m.group(1).strip()} repeats {m.group(2)} times "
                "now.")
            continue
        m = re.fullmatch(r"make\s+(?:the\s+)?([\w ]+?)\s+"
                         r"(open|closed)", low)
        if m:
            lines = _lines(path)
            span = _section_span(lines, m.group(1).strip())
            if not span:
                say(f"No section called '{m.group(1).strip()}'.")
                continue
            h = lines[span[0]]
            if m.group(2) == "open" and ", open" not in h:
                lines[span[0]] = h + ", open"
            elif m.group(2) == "closed":
                lines[span[0]] = h.replace(", open", "")
            _save_lines(path, lines)
            say(f"{m.group(1).strip()} is {m.group(2)} now.")
            continue
        say("I didn't get that — 'help' lists what I can do here.")


def _resolve_family(name, plans, named):
    """'head' -> the carved sections of that family, or the one
    section itself."""
    if not name:
        return None
    if name in named:
        return named[name]
    hit = next((p for p in plans if p["name"].lower() == name.lower()
                and p["kind"] == "plain"), None)
    if hit is None:
        # "solos over the blues" reaches the section by its form
        hit = next((p for p in plans
                    if (p.get("form") or ("",))[0] == name.lower()),
                   None)
    if hit is None and name.lower() in ("form", "the form", "tune",
                                        "the tune", "head",
                                        "the head", "it",
                                        "everything", "the changes"):
        # "solos over the form": the carved family, else the section
        # that carries a known form, else one named head, else the
        # biggest — a 16-bar shout must never outrank a 12-bar blues
        if len(named) == 1:
            return next(iter(named.values()))
        formed = [p for p in plans if p.get("form")]
        if formed:
            return [formed[0]]
        heads = [p for p in plans if p["name"].lower() == "head"]
        if heads:
            return [heads[0]]
        plain = [p for p in plans
                 if p["kind"] == "plain" and p.get("bars")]
        if plain:
            return [max(plain, key=lambda p: p["bars"])]
    return [hit] if hit else None


def _resolve_out(p, plans, named):
    """'out on the last A' -> the section whose changes the out plays."""
    src = (p["source"] or "").lower()
    m = re.fullmatch(r"last (\w+)", src)
    if m:
        fam = [q for q in plans if q.get("letter", "").lower() ==
               m.group(1).lower()]
        if fam:
            return fam[-1]
        hit = [q for q in plans if q["name"].lower() == m.group(1).lower()]
        return hit[-1] if hit else None
    fam = _resolve_family(src, plans, named)
    if fam and len(fam) == 1:
        return fam[0]
    return None


def render(plans, named):
    """Plans -> chart text.  A carved family whose changes solos borrow
    becomes a named progression; everything else prints inline."""
    prog_lines, section_lines = [], []
    for p in plans:
        if p["kind"] == "solos" and p.get("use_sections"):
            fam_name = p["use"]
            texts = [s.get("chords_text") or f"nc x{s['bars']}"
                     for s in p["use_sections"]]
            prog_lines.append(f"chords {fam_name}: " + ", ".join(texts))
    for p in plans:
        head = f"section {p['name']}, {p['bars']} bars"
        if p.get("mood"):
            head += f', label "{p["mood"]}"'
        if p["repeat"] > 1:
            head += f", repeat {p['repeat']}x"
        if p["open"]:
            head += ", open"
        section_lines.append(head)
        if p["kind"] == "solos" and p.get("use_sections"):
            section_lines.append(f"  use chords {p['use']}")
        else:
            section_lines.append(f"  chords: {p['chords_text']}")
        for w in p.get("who") or []:
            section_lines.append(f"  {w}")
        section_lines.append("")
    return prog_lines, section_lines
