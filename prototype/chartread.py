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
}


def say_chord(chord):
    if chord is None:
        return "no chord"
    step, alter, qual, bass = chord
    s = step + ACC[alter] + QUAL[qual]
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
    bits.append(f"{sec['bars']} bars")
    if sec['feel']:
        bits.append(sec['feel'])
    if sec['repeat']:
        bits.append(f"repeated, play {sec['repeat']} times")
    if sec['open']:
        bits.append("open")
    return ", ".join(bits) + "."


def part_section(plan, label, chord_parts, figures=None):
    """One section of one player's part, as sentences."""
    sec = plan['sec']
    kind, arg = plan['content'][label]
    default_groove = label in plan['rhythm_labels']
    if kind == 'default':
        kind, arg = ('groove', '') if default_groove else ('tacet', None)
    lines = [section_heading(sec)]
    texts = sorted(plan['texts'][label])
    shows_chords = (label in chord_parts or any(
        t[1].lower().startswith('solo') for t in texts)) and \
        label not in plan.get('percussion', ())

    for dbar, dbeat, mark in sorted(plan.get('dyns', {}).get(label, ())):
        word = {'pp': 'pianissimo', 'p': 'piano', 'mp': 'mezzo piano',
                'mf': 'mezzo forte', 'f': 'forte', 'ff': 'fortissimo'}[mark]
        where = f"at bar {dbar}"
        if dbeat != 1.0:
            whole = int(dbeat)
            where += (f" on the and of {whole}" if dbeat != whole
                      else f" on beat {whole}")
        lines.append(f"Dynamic: {word} {where}.")
    if figures:
        for item in figures:
            lo, hi = item['res']['bars']
            extra = (" Every note marcato — short and fat."
                     if item.get('marcato') else "")
            lines.append(f"Your line, bars {lo} to {hi}, spoken at "
                         f"concert pitch:{extra}")
            prose = chartdemo.say_range(item['res'], item['concert_fifths'],
                                        item['fall'],
                                        short=item.get('short', False),
                                        scoops=item.get('scoops'))
            for bar in sorted(prose):
                lines.append(f"Bar {bar}: {prose[bar]}")
        rest = sec['bars'] - sum(i['res']['n_units'] // chartdemo.BAR
                                 for i in figures)
        if rest > 0:
            lines.append(f"The other {rest} bars of the section: rest.")
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
    elif kind == 'groove':
        g = f'Groove, "{arg}"' if arg else "Groove"
        what = "slashes with the changes" if shows_chords else "slashes"
        lines.append(f"{g} — {what}.")
    elif any(t[1].lower().startswith('solo') for t in texts):
        lines.append(f"You solo — {sec['bars']} bars over the changes, "
                     "nothing written out.")
    else:
        lines.append(f"Tacet — {sec['bars']} bars rest.")

    if shows_chords:
        lines.append("Changes: " + say_bars(sec['content']))
    for bar, text in texts:
        lines.append(f'At bar {bar}: "{text}".'
                     if bar > 1 else f'Marked: "{text}".')
    return ("\n".join(lines) if figures else " ".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('chart')
    ap.add_argument('--part', help='a band part label, e.g. "alto 1"')
    ap.add_argument('--section', help='read just this section')
    a = ap.parse_args()

    chart = chartc.parse_chart(a.chart)
    hdr = chart['header']
    band = chart['band']
    groups = chartc.resolve_groups(band)
    labels = [b['label'] for b in band]
    plans, total = chartc.build_plans(chart, band, groups, labels)
    findings = chartdemo.Findings()
    resolved, horn_of, key = chartc.resolve_demo(chart, plans, band, labels,
                                                 a.chart, findings)
    for l in labels:
        for item in resolved[l]:
            item['concert_fifths'] = key[0]
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
            out.append(section_heading(sec) + " Changes: " +
                       say_bars(sec['content']))

    # One write. A screen reader restarts on every write, so the whole
    # answer lands at once.
    sys.stdout.write("\n\n".join(out) + "\n")


if __name__ == '__main__':
    main()
