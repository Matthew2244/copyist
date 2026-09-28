#!/usr/bin/env python3
"""
chartexcerpt — a bar range out of a Copyist MusicXML document.

Keeps the measures numbered from `first` to `last` (as printed) in every
part, and carries into the first kept measure everything it needs to
stand on its own: divisions, key, time, clefs, staves, transposition,
and the last tempo marking before it. A multi-measure rest the range
cuts through is shortened to the bars it keeps. Everything else — words,
repeat signs, chord symbols — stays exactly as printed.
"""

import re

_CARRY = ('divisions', 'key', 'time', 'staves', 'clef', 'transpose')


def _num(m):
    n = re.match(r'<measure\b[^>]*\bnumber="([^"]*)"', m)
    return int(n.group(1)) if n and n.group(1).isdigit() else None


def _attr_state(measures):
    """The attributes in force after these measures, element by element
    (a clef is kept per staff number)."""
    state = {}
    for m in measures:
        for block in re.findall(r'<attributes>(.*?)</attributes>', m, re.S):
            for tag in _CARRY:
                for el in re.finditer(r'<%s\b[^>]*?(?:/>|>.*?</%s>)'
                                      % (tag, tag), block, re.S):
                    key = tag
                    if tag == 'clef':
                        num = re.search(r'number="(\d+)"', el.group(0))
                        key = 'clef' + (num.group(1) if num else '1')
                    state[key] = el.group(0)
    return state


def _last_tempo(measures):
    found = None
    for m in measures:
        for d in re.findall(r'<direction\b.*?</direction>', m, re.S):
            if '<metronome' in d:
                found = d
    return found


def _multi(m):
    r = re.search(r'<multiple-rest>(\d+)</multiple-rest>', m)
    return int(r.group(1)) if r else 0


def _set_multi(m, k):
    m = re.sub(r'<attributes><measure-style><multiple-rest>\d+'
               r'</multiple-rest></measure-style></attributes>', '', m)
    m = re.sub(r'<measure-style><multiple-rest>\d+</multiple-rest>'
               r'</measure-style>', '', m)
    if k > 1:
        m = re.sub(r'(<measure\b[^>]*>)', r'\1<attributes><measure-style>'
                   '<multiple-rest>%d</multiple-rest></measure-style>'
                   '</attributes>' % k, m, count=1)
    return m


def _cut_part(body, first, last):
    measures = re.findall(r'<measure\b.*?</measure>', body, re.S)
    before = [m for m in measures if (_num(m) or 0) < first]
    keep = [m for m in measures
            if _num(m) is not None and first <= _num(m) <= last]
    if not keep:
        return None
    # a multirest the range cuts: shorten it to what the range keeps
    run_from, run_left = None, 0
    for m in measures:
        n = _num(m)
        if n is None:
            continue
        if _multi(m):
            run_from, run_left = n, _multi(m)
        if n >= first:
            break
    out = []
    for m in keep:
        n = _num(m)
        k = _multi(m)
        if n == first and not k and run_from is not None and \
                run_from < first < run_from + run_left:
            k = run_from + run_left - first
            m = _set_multi(m, k)
        if k:
            m = _set_multi(m, min(k, last - n + 1))
        out.append(m)
    state = _attr_state(before + [out[0]])
    head = ''.join(state[k] for k in
                   ('divisions', 'key', 'time', 'staves', 'transpose')
                   if k in state)
    head += ''.join(state[k] for k in sorted(state) if k.startswith('clef'))
    first_m = out[0]
    first_m = re.sub(r'<attributes>(?!<measure-style>).*?</attributes>', '',
                     first_m, count=1, flags=re.S)
    tempo = _last_tempo(before) if '<metronome' not in first_m else None
    first_m = re.sub(r'(<measure\b[^>]*>)',
                     lambda g: g.group(1) + '<attributes>' + head +
                     '</attributes>' + (tempo or ''), first_m, count=1)
    out[0] = first_m
    return '\n'.join(out)


def excerpt(xml, first, last):
    """The document with only bars first..last (printed numbers) in each
    part. None when no part has any of those bars."""
    parts = list(re.finditer(r'(<part id="[^"]+">)(.*?)(</part>)', xml, re.S))
    if not parts:
        return None
    out, at, kept = [], 0, False
    for p in parts:
        body = _cut_part(p.group(2), first, last)
        out.append(xml[at:p.start()])
        if body is None:
            out.append(p.group(0))
        else:
            kept = True
            out.append(p.group(1) + '\n' + body + '\n' + p.group(3))
        at = p.end()
    out.append(xml[at:])
    return ''.join(out) if kept else None


def bar_range(text):
    """'9-24', '9 to 24', 'bars 9 through 24', '12' -> (9, 24); 'all',
    'whole', '' -> None."""
    t = (text or '').strip().lower()
    if t in ('', 'all', 'whole', 'whole song', 'entire song', 'everything'):
        return None
    nums = [int(x) for x in re.findall(r'\d+', t)]
    if len(nums) == 1:
        return nums[0], nums[0]
    if len(nums) == 2 and nums[0] <= nums[1]:
        return nums[0], nums[1]
    raise ValueError(f"'{text}' is not a bar range — say it like 9-24, "
                     "or all for the whole song")
