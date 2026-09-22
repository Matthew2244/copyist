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


def parse_form(text, vocab=None):
    text = apply_vocab(text, vocab or {})
    text = digitize(text)
    clauses = re.split(r",|\bthen\b|\.|;", text)
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
    low, reps, open_ = _repeat_words(low)

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

    # a form it knows by name — "12 bar blues in b flat" arrives with
    # its changes already in hand, offered for a yes at chords time
    if re.search(r"\bblues\b", low):
        m = BLUES_RE.search(low)
        bars = int(m.group(1)) if m.group(1) else 12
        pre = re.sub(r"\b(is|the|a|an|of)\b", " ", low[:m.start()])
        pre = re.sub(r"[^\w ]", " ", pre).split()
        p = _mk(pre[0] if pre else "head", bars=bars, repeat=reps,
                open_=open_)
        if bars == 12:
            p["form"] = ("minor blues" if m.group(2) else "blues",
                         (m.group(3) or "").strip() or None)
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


def parse_spoken_chords(text, vocab=None):
    """The whole answer -> a chords: line.  Raises SpokenError naming
    the first word it cannot read."""
    text = apply_vocab(text, vocab or {})
    segs = [s.strip() for s in text.split(",") if s.strip()]
    return ", ".join(_spoken_segment(s) for s in segs)


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

FORMS = {
    "blues": ("Bb7, Eb7, Bb7 x2, Eb7 x2, Bb7, Dm7 G7@3, Cm7, F7, "
              "Bb7, F7", "Bb", 12),
    "minor blues": ("Cm7 x4, Fm7 x2, Cm7 x2, Ab7, G7, Cm7, G7",
                    "C", 12),
}

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


def known_changes(kind, key_text, default_key):
    """A form name and a key -> (chords line, bars, spoken name).
    Sharp-side keys spell sharp — a blues in B wants F#7, never Gb7."""
    master, home, bars = FORMS[kind]
    pc = key_pc(key_text)
    if pc is None:
        pc = key_pc(default_key) or 0
    sharp = pc in SHARP_KEYS or "#" in (key_text or "") or \
        "sharp" in (key_text or "").lower()
    names = PC_SHARP if sharp else PC_NAME
    line = transpose_line(master, (pc - key_pc(home)) % 12, names)
    return line, bars, f"the 12-bar {kind} in {names[pc]}"


BLUES_RE = re.compile(r"(?:(\d+)\s*bars?\s+)?(?:a\s+)?(minor\s+)?"
                      r"blues(?:\s+in\s+([a-g](?:\s+(?:flat|sharp))?"
                      r"))?\b")


# ------------------------------------------------------- who plays

def parse_who(text, labels, groups, vocab=None):
    """'horns tacet; trumpet from demo bars 5-12; rhythm grooves' ->
    directive lines.  Raises SpokenError on a target or instruction it
    cannot read."""
    text = apply_vocab(text, vocab or {})
    lines = []
    for phrase in re.split(r";|,|\band\b(?=\s+\w+\s+(?:tacet|groove|"
                           r"solo|from|plays))", text):
        phrase = phrase.strip().strip(",").strip()
        if not phrase:
            continue
        toks = phrase.split()
        target = None
        for k in range(min(3, len(toks)), 0, -1):
            cand = " ".join(toks[:k]).lower()
            hit = next((l for l in list(labels) + list(groups)
                        if l.lower() == cand), None)
            if hit:
                target, rest = hit, toks[k:]
                break
        if not target:
            raise SpokenError(toks[0], phrase)
        r = " ".join(rest).lower().strip()
        r = re.sub(r"^(plays?|is|are)\s+", "", r)
        if r in ("tacet", "out", "rests", "rest"):
            lines.append(f"{target}: tacet")
        elif r in ("grooves", "groove", "time", "plays time", "plays",
                   "play", ""):
            lines.append(f"{target}: groove")
        elif r in ("solo", "solos"):
            lines.append(f"{target}: solo")
        elif r in ("solo open", "solos open", "open solo"):
            lines.append(f"{target}: solo open")
        elif re.fullmatch(r"(from (the )?demo )?(bars? )?\d+\s*(-|to)"
                          r"\s*\d+", r):
            m = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)", r)
            lines.append(f"{target}: from demo bars "
                         f"{m.group(1)}-{m.group(2)}")
        else:
            raise SpokenError(r or phrase, phrase)
    return lines


# ------------------------------------------------- the chart on disk

def splice(path, keep_existing, prog_lines, section_lines):
    """Rewrite the chart: everything above the sections stays word for
    word; named progressions land just before the sections; sections
    are replaced (or kept, with the new ones after)."""
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
        fm = re.fullmatch(r"(?:(\d+)\s*bars?\s+)?(?:a\s+)?(minor\s+)?"
                          r"blues(?:\s+in\s+(.+))?", a.strip(),
                          re.IGNORECASE)
        if fm:
            kind = "minor blues" if fm.group(2) else "blues"
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
            return parse_spoken_chords(a, ctx["vocab"])
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
                lines = parse_who(a, ctx["labels"], ctx["groupnames"],
                                  ctx["vocab"])
                # his standing quant setting rides every from-demo lift
                q = ctx["cfg"].get("quant")
                if q:
                    lines = [ln + f", {q}" if "from demo bars" in ln
                             else ln for ln in lines]
                return lines
            except SpokenError as e:
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

    keep = False
    if not scaffold_only(chart):
        a = ask(f"This chart already has {len(chart['sections'])} "
                "section(s) with real content. keep them and add the "
                "new form after, or replace them", "keep")
        keep = not a.lower().startswith("r")

    say("Tell me the tune in one breath — sections in order, like "
        "'8 bar intro, head is 32 AABA, solos over the head twice, "
        "out on the last A'. Or press Enter and I'll ask one section "
        "at a time.")
    breath = ask("The tune")
    plans, gaps = (parse_form(breath, vocab) if breath else ([], []))
    if breath and plans:
        bits = []
        for p in plans:
            b = p["name"]
            if p["bars"]:
                b += f" {p['bars']}"
            if p["shape"]:
                b += f" {p['shape'].upper()}"
            if p["use"]:
                b += f" over the {p['use']}"
            if p["repeat"] > 1:
                b += f" x{p['repeat']}"
            if p["open"]:
                b += " open"
            bits.append(b)
        say("Placed: " + "; ".join(bits) + ".")
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
    if not plans:
        # the guided walk — he pressed Enter, it leads
        while True:
            nm = ask("Next section — its name, like intro or A "
                     "(Enter to finish)")
            if not nm:
                break
            p = parse_clause(digitize(apply_vocab(nm, vocab))) or _mk(nm)
            plans.append(p)
    if not plans:
        sys.exit("chart: no sections described, nothing written.")

    # bars first — lengths are the skeleton everything else hangs on
    named = {}
    for p in plans:
        if p["kind"] == "solos" and p["bars"] is None and p["use"]:
            continue                      # inherits its form's length
        if p["kind"] == "out" and p["bars"] is None and p["source"]:
            continue
        _ask_bars(p)
    # AABA-style shapes carve (or keep) — his call
    carved = []
    for p in plans:
        if p["shape"]:
            fam = _carve(p)
            if len(fam) > 1:
                named[p["name"]] = fam
            carved.extend(fam)
        else:
            carved.append(p)
    plans = carved

    # demo bar bookkeeping: where each section starts in his DAW
    start = 1
    for p in plans:
        p["start_demo"] = start + countin
        if p["bars"]:
            start += p["bars"]

    # chords, section by section, then who plays
    for p in plans:
        if p["kind"] == "solos":
            src = _resolve_family(p["use"], plans, named)
            if src:
                p["use_sections"] = src
                p["bars"] = sum(s["bars"] for s in src)
            else:
                if p["use"]:
                    say(f"I don't see a section called '{p['use']}' "
                        "to solo over — I'll ask for the changes.")
                _ask_bars(p)
                p["chords_text"] = _chords_for(p, ctx)
        elif p["kind"] == "out":
            src = _resolve_out(p, plans, named)
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

    prog_lines, section_lines = render(plans, named)
    splice(path, keep, prog_lines, section_lines)
    try:
        final = chartc.parse_chart(path)
    except SystemExit as e:
        say(f"Written, but the check found: {e.code}")
        say(f"The file is {path} — say the word and we fix it "
            "together.")
        return
    total = 0
    for sec in final["sections"]:
        total += sec["bars"] * max(sec.get("repeat") or 1, 1)
    say(f"Written and checked: {len(final['sections'])} section(s), "
        f"{total} bars through the form. Next: chart build, and "
        "you'll hear it.")


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
