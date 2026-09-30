#!/usr/bin/env python3
"""chartread — the read-aloud part view (CHART-FORMAT.md §4).

Renders a chart, or one player's part, as prose: the part as the player
will experience it, section by section, in sentences. This is the blind
proofread, and it is a first-class output, not a debug aid.

It resolves the chart with the SAME plan builder the compiler uses
(chartc.build_plans), so the prose and the printed page cannot disagree.

Spoken style follows the house rules for screen-reader output: the whole
answer is built first and written once (a screen reader restarts on every
write), chords are spoken as a musician says them ("B flat seven"), and
off-beats are always "the and of four" no matter how the source spelled
them.

Usage:
  chartread.py <file.chart>                    the form, with the changes
  chartread.py <file.chart> --part "alto 1"    one player's part
  chartread.py <file.chart> --part piano --section A
"""
import argparse
import os
import re
import sys

import chartc
import chartdemo

ACC = {-1: ' flat', 0: '', 1: ' sharp'}
QUAL = {
    '7': ' seven', '9': ' nine', '11': ' eleven', '13': ' thirteen',
    'maj': '', 'maj7': ' major seven', 'm': ' minor', 'm7': ' minor seven',
    'm9': ' minor nine', 'm6': ' minor six', '6': ' six',
    'dim': ' diminished', 'dim7': ' diminished seven',
    'm7b5': ' minor seven flat five', 'sus4': ' sus four',
    '7sus4': ' seven sus four', 'aug': ' augmented',
    'maj9': ' major nine', 'm11': ' minor eleven',
    '7#9': ' seven sharp nine',
    '7b9': ' seven flat nine', '7#11': ' seven sharp eleven',
    '7#9#11': ' seven sharp nine sharp eleven',
    '69': ' six nine', 'm69': ' minor six nine', 'alt': ' altered',
    '13b9': ' thirteen flat nine', 'sus2': ' sus two',
    'add9': ' add nine', 'madd9': ' minor add nine',
    'mmaj7': ' minor major seven',
    'maj7#11': ' major seven sharp eleven', '7#5': ' seven sharp five',
    '7b5': ' seven flat five', '7b13': ' seven flat thirteen',
}


ROAD_SPOKEN = {
    'segno': "the sign. The D.S. comes back to this bar.",
    'coda': "the coda starts here.",
    'tocoda': "To Coda. On the way back, jump to the coda after this bar.",
    'fine': "Fine. On the way back, the tune ends at this bar.",
    'ds': "D.S. Back to the sign.",
    'ds_coda': "D.S. al Coda. Back to the sign, then take the coda.",
    'ds_fine': "D.S. al Fine. Back to the sign, and end at Fine.",
    'dc': "D.C. Back to the top.",
    'dc_coda': "D.C. al Coda. Back to the top, then take the coda.",
    'dc_fine': "D.C. al Fine. Back to the top, and end at Fine.",
}


def say_quality(qual):
    """Any quality the compiler accepts, spoken: the table's own words
    first, else spelled out piece by piece ('13#11' -> 'thirteen sharp
    eleven') — a chord the page can print must never crash the voice."""
    if qual in QUAL:
        return QUAL[qual]
    words = {'maj': 'major', 'm': 'minor', 'dim': 'diminished',
             'aug': 'augmented', 'sus': 'sus', 'add': 'add',
             'alt': 'altered', '#': 'sharp', 'b': 'flat',
             '2': 'two', '4': 'four', '5': 'five', '6': 'six',
             '7': 'seven', '9': 'nine', '11': 'eleven',
             '13': 'thirteen'}
    out = []
    for tok in re.findall(r'maj|dim|aug|sus|add|alt|m|#|b|\d+', qual):
        out.append(words.get(tok, tok))
    if qual == '5':
        return ' five, no third'
    return (' ' + ' '.join(out)) if out else ''


def say_chord(chord):
    if chord is None:
        return "no chord"
    step, alter, qual, bass = chord
    s = step + ACC[alter] + say_quality(qual)
    if bass:
        b = bass[0] + ACC[{'b': -1, '#': 1}.get(bass[1:], 0) if len(bass) > 1
                          else 0]
        s += " over " + b
    return s


def say_beat(beat):
    whole = int(beat)
    return f"the and of {whole}" if beat != whole else f"beat {whole}"


def say_bar(bar):
    """One bar of (beat, chord) -> prose."""
    if len(bar) == 1:
        return say_chord(bar[0][1])
    first = say_chord(bar[0][1])
    rest = ", ".join(f"{say_chord(c)} at {say_beat(b)}" for b, c in bar[1:])
    return f"{first}, then {rest}"


def say_changes(sec):
    """A section's changes, endings spoken as their own sentences."""
    ends = sec.get('endings') or []
    if not ends:
        return "Changes: " + say_bars(sec['content'])
    ORD = {1: 'First', 2: 'Second', 3: 'Third', 4: 'Fourth',
           5: 'Fifth', 6: 'Sixth'}
    body = sec['body']
    bits = ["Changes: " + say_bars(sec['content'][:body])]
    pos = body
    for e in ends:
        bits.append(f"{ORD.get(e['num'], str(e['num']))} ending: "
                    + say_bars(sec['content'][pos:pos + e['bars']]))
        pos += e['bars']
    return " ".join(bits)


def say_bars(bars):
    """A section's bars -> prose with runs of identical bars grouped."""
    out, i = [], 0
    while i < len(bars):
        j = i
        while j + 1 < len(bars) and bars[j + 1] == bars[i]:
            j += 1
        n = j - i + 1
        text = say_bar(bars[i])
        out.append(f"{text} for {n} bars" if n > 1 else text)
        i = j + 1
    return "; ".join(out) + "."


def section_heading(sec):
    name = sec['name']
    h = f"Letter {name}" if len(name) == 1 and name.isupper() else \
        f"Bar-{name}" if name.isdigit() else name.capitalize()
    bits = [h]
    if sec['label']:
        bits.append(f'"{sec["label"]}"')
    if sec.get('endings'):
        per = sec['body'] + sec['endings'][0]['bars']
        bits.append(f"{per} bars a pass, with "
                    f"{len(sec['endings'])} endings")
    else:
        bits.append(f"{sec['bars']} bars")
    if sec['feel']:
        bits.append(sec['feel'])
    if sec['repeat']:
        bits.append(f"repeated, play {sec['repeat']} times")
    if sec['open']:
        bits.append("open")
    for bar, kind, val in sec.get('events', ()):
        if kind == 'meter':
            bits.append(f"in {val}" if bar == 1 else
                        f"the meter changes to {val} at bar {bar}")
        elif kind == 'key':
            bits.append(f"the key changes to {val} here" if bar == 1
                        else f"the key changes to {val} at its bar {bar}")
    return ", ".join(bits) + "."


def part_section(plan, label, chord_parts, figures=None):
    """One section of one player's part, as sentences."""
    sec = plan['sec']
    kind, arg = plan['content'][label]
    default_groove = label in plan['rhythm_labels']
    if kind == 'default':
        kind, arg = ('groove', '') if default_groove else ('tacet', None)
    lines = [section_heading(sec)]
    cuer, role = sec.get('_cuer'), sec.get('_cue_role')
    if sec.get('open') and cuer == label:
        lines.append("It goes round till you cue the band out: on the "
                     "last time round, " + chartc.CUE_SOUND[role] + ".")
    elif sec.get('open') and cuer:
        who = ('the drummer' if role == 'drums' else 'the singer'
               if role == 'voice' else f'the {cuer}')
        lines.append(f"It goes round till {who} cues it: listen for "
                     + chartc.CUE_SOUND[role] + ".")
    elif sec.get('open'):
        lines.append("It goes round till the bandleader cues it.")
    texts = sorted(plan['texts'][label], key=lambda t: t[0])
    shows_chords = (label in chord_parts or any(
        isinstance(t[1], str) and t[1].lower().startswith('solo')
        for t in texts)) and \
        label not in plan.get('percussion', ())

    for dbar, dbeat, mark, sub in sorted(plan.get('dyns',
                                                  {}).get(label, ())):
        word = {'pp': 'pianissimo', 'p': 'piano', 'mp': 'mezzo piano',
                'mf': 'mezzo forte', 'f': 'forte', 'ff': 'fortissimo',
                'sfz': 'sforzando', 'fp': 'forte-piano'}[mark]
        if sub:
            word = 'subito ' + word
        where = f"at bar {dbar}"
        if dbeat != 1.0:
            whole = int(dbeat)
            where += (f" on the and of {whole}" if dbeat != whole
                      else f" on beat {whole}")
        lines.append(f"Dynamic: {word} {where}.")
    if figures:
        for item in figures:
            if item.get('cue'):
                lines.append(f"The {item['src_label']}'s line prints "
                             "small here as a cue — not yours to play.")
                continue
            if item.get('soli'):
                lines.append(f"Your soli voice under the {item['soli']}, "
                             "voiced from the changes, written for you.")
            if item.get('src_label'):
                oct_ = chartc.octave_words(item.get('octaves', 0))
                oct_ += chartc.harmony_words(item.get('harm', 0))
                lines.append(f"You double the {item['src_label']}{oct_} "
                             "— the same line, written for you.")
            lo, hi = item['res']['bars']
            words = {'strong-accent': 'marcato — short and fat',
                     'staccato': 'staccato', 'tenuto': 'tenuto — full value',
                     'accent': 'accented'}
            extra = (f" Every note {words[item['every']]}."
                     if item.get('every') else "")
            span = item['res']['bars'][1]
            lines.append(
                (f"Your written figure, {span} bar(s), spoken at "
                 f"concert pitch:{extra}") if item.get('inline') else
                (f"Your line, bars {lo} to {hi}, spoken at "
                 f"concert pitch:{extra}"))
            if item['res'].get('lyrics_text'):
                lines.append(f"Words: {item['res']['lyrics_text']}")
            prose = chartdemo.say_range(item['res'], item['concert_fifths'],
                                        item['fall'],
                                        short=item.get('short', False),
                                        doit=item.get('doit', False),
                                        scoops=item.get('scoops'),
                                        fifths_at=item.get('fifths_at'),
                                        minor_at=item.get('minor_at'),
                                        chords_at=item.get('chords_at'))
            for bar in sorted(prose):
                lines.append(f"Bar {bar}: {prose[bar]}")
        rest = sec['bars'] - sum(
            i['res']['n_units'] // i['res'].get('bar_ticks', chartdemo.BAR)
            for i in figures)
        if rest > 0:
            what = ("slashes with the changes" if kind == 'groove'
                    and shows_chords else
                    "slashes" if kind == 'groove' else "rest")
            lines.append(f"The other {rest} bars of the section: {what}.")
    elif kind == 'engraved':
        lo, hi, at = arg
        span = hi - lo + 1
        where = "all bars" if at == 1 and span == sec['bars'] else \
            f"from bar {at} of the section for {span} bars"
        lines.append(f"Your written line, {where} — engraved bars "
                     f"{lo} to {hi} of the source.")
        if at > 1:
            lines.append(f"Bars 1 to {at - 1}: rest.")
        if at - 1 + span < sec['bars']:
            lines.append(f"Bars {at + span} to {sec['bars']}: rest.")
    elif kind == 'hits':
        hmap, gw = arg
        bits = []
        if None in hmap:
            bits.append("every bar kicks on "
                        + " and ".join(say_beat(b) for b in hmap[None]))
        for bar in sorted(k for k in hmap if k is not None):
            bits.append(f"bar {bar} kicks on "
                        + " and ".join(say_beat(b) for b in hmap[bar]))
        g = f' "{gw}"' if gw else ""
        lines.append(f"Kicks{g} — {'; '.join(bits)}; slashes everywhere "
                     "else.")
        enter = plan.get('enters', {}).get(label)
        if enter:
            lines.append(f"You come in at bar {enter}; rest before that.")
    elif kind == 'groove':
        is_solo = any(isinstance(t[1], str)
                      and t[1].lower().startswith('solo')
                      for t in texts)
        if is_solo and not arg:
            lines.append(f"You solo — {sec['bars']} bars of slashes "
                         "over the changes.")
        else:
            g = f'Groove, "{arg}"' if arg else "Groove"
            what = ("slashes with the changes" if shows_chords
                    else "slashes")
            enter = plan.get('enters', {}).get(label)
            if enter:
                lines.append(f"Bars 1 to {enter - 1}: rest. {g} from "
                             f"bar {enter} — {what}.")
            else:
                lines.append(f"{g} — {what}.")
    elif any(isinstance(t[1], str) and t[1].lower().startswith('solo')
             for t in texts):
        lines.append(f"You solo — {sec['bars']} bars over the changes, "
                     "nothing written out.")
    else:
        lines.append("Rest until the last time round, then the cue."
                     if sec.get('open') and sec.get('_cuer') == label
                     else f"Tacet — {sec['bars']} bars rest.")

    for ref in plan.get('lifts', {}).get(label, ()):
        span = ref['hi'] - ref['lo'] + 1
        at = ref['at'] - plan['start'] + 1
        lines.append(f"Figure at bar {at}, {span} bars — written bars "
                     f"{ref['lo']} to {ref['hi']} of '{ref['part']}', "
                     "lifted exactly from "
                     f"{os.path.basename(ref['file'])}.")
    if shows_chords:
        lines.append(say_changes(sec))
    for bar, text in texts:
        # the printed bar, the number on the page and in the notes above
        # (a sign said "at bar 1" of letter A sent the player to bar 1)
        printed = bar + plan['start'] - 1
        if isinstance(text, tuple) and text[0] == 'road':
            lines.append(f"At bar {printed}: {ROAD_SPOKEN[text[1]]}")
            continue
        if isinstance(text, tuple) and text[0] == 'tempo':
            lines.append(f"At bar {printed}: tempo changes to {text[1]}.")
        else:
            # a technique word says what it means, for anyone who has
            # never held a bow
            said = f'"{text}"' + TECHNIQUE_SAID.get(
                str(text).strip().lower(), "")
            lines.append(f'At bar {printed}: {said}.'
                         if bar > 1 else f'Marked: {said}.')
    return ("\n".join(lines) if figures else " ".join(lines))


TECHNIQUE_SAID = {"arco": ", with the bow", "pizz.": ", plucked",
                  "pizz": ", plucked", "con sord.": ", with the mute",
                  "senza sord.": ", mute off", "sul pont.": ", bow near "
                  "the bridge", "sul tasto": ", bow over the fingerboard"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('chart')
    ap.add_argument('--part', help='a band part label, e.g. "alto 1"')
    ap.add_argument('--section', help='read just this section')
    a = ap.parse_args()

    chart = chartc.parse_chart(a.chart)
    hdr = chart['header']
    band = chart['band']
    groups = chartc.resolve_groups(band, chart.get('groups'))
    labels = [b['label'] for b in band]
    chartc.resolve_trades(chart, band, groups)
    plans, total = chartc.build_plans(chart, band, groups, labels)
    chartc.road_cues(plans, band, labels, None)   # who cues, where cuts go
    findings = chartdemo.Findings()
    meter = chartc.parse_meter(hdr.get('meter', '4/4'))
    resolved, horn_of, key = chartc.resolve_demo(chart, plans, band, labels,
                                                 a.chart, findings, meter)
    for l in labels:
        for item in resolved[l]:
            item['concert_fifths'] = chartc.key_at(
                chart.get('keys') or [(1, key)], item['res']['at'])[0]
            item['fifths_at'] = (lambda b, k=chart.get('keys') or
                                 [(1, key)]: chartc.key_at(k, b)[0])
            item['minor_at'], item['chords_at'] = chartc.spelling_hints(
                chart, key)
    chord_parts = {l for l in labels
                   if l in groups['rhythm'] and
                   'drum' not in next(b for b in band
                                      if b['label'] == l)['instrument'].lower()}
    percussion = {l for l in labels
                  if 'drum' in next(b for b in band
                                    if b['label'] == l)['instrument'].lower()}
    for plan in plans:
        plan['rhythm_labels'] = groups['rhythm']
        plan['percussion'] = percussion

    out = []
    title = hdr.get('title', 'Untitled')

    if a.part:
        want = a.part.lower().strip()
        if want not in [l.lower() for l in labels]:
            sys.exit(f'chartread: no band part called "{a.part}". '
                     f'Parts: {", ".join(labels)}.')
        label = next(l for l in labels if l.lower() == want)
        out.append(f"{title} — the {label} part. "
                   f"{len(plans)} sections, {total} bars.")
        if int(hdr.get('countin', 0)):
            out.append("Bar numbers here are your DAW's, count-in "
                       "included. The printed page starts at one.")
        if chart['pickup']:
            pk = chart['pickup']
            t = "; ".join(f'"{x}"' for x in pk['texts'])
            out.append(f"Pickup, {pk['beats']} beats" +
                       (f", marked {t}." if t else "."))
        for plan in plans:
            if a.section and plan['sec']['name'].lower() != a.section.lower():
                continue
            figures = [i for i in resolved[label] if i['plan'] is plan]
            out.append(part_section(plan, label, chord_parts, figures))
    else:
        bits = [title]
        if hdr.get('composer'):
            bits.append("by " + hdr['composer'])
        if hdr.get('key'):
            k = hdr['key']
            spoken = k[0] + (' flat' if k[1:2] == 'b' else
                             ' sharp' if k[1:2] == '#' else '')
            if 'minor' in k.lower():
                spoken += ' minor'
            bits.append("in " + spoken)
        if hdr.get('feel'):
            bits.append(hdr['feel'])
        out.append(", ".join(bits) +
                   f". {len(band)} parts, {len(plans)} sections, "
                   f"{total} bars" +
                   (", plus a pickup." if chart['pickup'] else "."))
        for plan in plans:
            if a.section and plan['sec']['name'].lower() != a.section.lower():
                continue
            sec = plan['sec']
            out.append(section_heading(sec) + " " + say_changes(sec))

    # One write. A screen reader restarts on every write, so the whole
    # answer lands at once.
    sys.stdout.write("\n\n".join(out) + "\n")


if __name__ == '__main__':
    main()
