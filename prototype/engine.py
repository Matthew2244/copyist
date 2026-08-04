#!/usr/bin/env python3
"""
The engine's machine-readable surface — DESIGN.md section 5.2.

The GUIs are meant to be thin, which only works if the protocol between them
and the engine is good. This is that protocol, deliberately built before either
GUI so the UI cannot quietly become the place where logic lives. The MCP server
in section 5 will speak the same shapes.

    python3 engine.py analyze FILE.mid
    python3 engine.py convert FILE.mid --out OUT.musicxml [--key "C# minor"]
                                        [--reach 17] [--comfortable 14]

Always prints one JSON object to stdout, including on failure:

    {"ok": false, "error": "..."}
"""

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analyze as A                                    # noqa: E402
import convert as C                                    # noqa: E402
from spelling import ps13, double_accidentals          # noqa: E402


def verdict_of(st):
    if not st:
        return "unknown", "Too few notes to classify."
    if st["exact"] > 0.95 or st["peak"] < 1.0:
        return "hard-quantized", ("Onsets are exactly on the grid. "
                                  "Quantization is free and cannot be wrong.")
    if abs(st["r1"]) < 0.20 and st["pct"] < 95:
        return "humanized", ("Quantized, then humanized. The offsets are "
                             "independent noise and identical at every "
                             "metrical position, so the grid underneath is "
                             "exact and can be recovered.")
    if st["r1"] > 0.25 or st["pct"] >= 95:
        return "live", ("Played live. Deviation depends on where you are in "
                        "the bar, so there is real timing intent to preserve.")
    return "ambiguous", "Inconclusive between humanize and live playing."


def do_analyze(path):
    mid = A.parse_midi(path)
    x = A.extract(mid)
    div = mid["division"]
    notes = x["notes"]
    if not notes:
        return {"ok": False, "error": "No notes in that file."}

    bpm = 60_000_000 / x["tempos"][0][1] if x["tempos"] else 120.0
    ts = (x["timesigs"][0][1], x["timesigs"][0][2]) if x["timesigs"] else (4, 4)
    gname, st = A.classify_timing(notes, div, bpm)
    kind, explanation = verdict_of(st)
    keys = A.estimate_key(notes)
    sim, wide = A.texture(notes)

    tracks = []
    for ti in range(len(mid["tracks"])):
        tn = [n for n in notes if n.track == ti]
        if not tn and ti not in x["names"]:
            continue
        lo = min((n.pitch for n in tn), default=0)
        hi = max((n.pitch for n in tn), default=0)
        tracks.append({
            "index": ti,
            "name": x["names"].get(ti, ""),
            "notes": len(tn),
            "programs": sorted(x["programs"].get(ti, [])),
            "drums": any(n.chan == 9 for n in tn),
            "low": lo, "high": hi,
        })

    lengths = A.classify_lengths(notes, div, bpm)
    vels = sorted(n.vel for n in notes)

    return {
        "ok": True,
        "file": os.path.abspath(path),
        "notes": len(notes),
        "division": div,
        "tempo": {"bpm": round(bpm, 2), "events": len(x["tempos"]),
                  "constant": len(x["tempos"]) <= 1},
        "meter": {"beats": ts[0], "beatType": ts[1],
                  "stated": bool(x["timesigs"])},
        "timing": {
            "grid": gname, "kind": kind, "explanation": explanation,
            "sd": round(st.get("sd", 0.0), 1),
            "peak": round(st.get("peak", 0.0), 1),
            "onGrid": round(st.get("exact", 0.0) * 100, 1),
            "autocorrelation": round(st.get("r1", 0.0), 3),
            "nullPercentile": round(st.get("pct", 0.0)),
        },
        "lengths": {
            "onGrid": round(lengths.get("exact", 0.0) * 100, 1),
            "medianMs": round(lengths.get("median", 0.0), 1),
            "quantized": lengths.get("exact", 0.0) > 0.9,
        },
        "keys": [{"name": n, "confidence": round(c * 100)} for n, c in keys],
        "texture": {"maxSimultaneous": sim, "widestSemitones": wide,
                    "widestName": A.name_interval(wide)},
        "velocity": {"low": vels[0], "high": vels[-1],
                     "distinct": len(set(vels))},
        "pedal": x["cc64"],
        "markers": [{"tick": t, "text": s} for t, s in x["markers"]],
        "tracks": tracks,
    }


def do_convert(path, out, key, reach, comfortable, level="full"):
    buf = io.StringIO()
    with redirect_stdout(buf):
        C.convert(path, out, key, reach, comfortable, level)
    text = buf.getvalue()
    if not os.path.exists(out):
        return {"ok": False, "error": text.strip()[:500] or "Conversion failed."}

    findings = getattr(C, "LAST_FINDINGS", None)
    summary = getattr(C, "LAST_SUMMARY", {}) or {}
    return {
        "ok": True,
        "output": os.path.abspath(out),
        "notatedMidi": summary.get("notatedMidi"),
        "summary": summary,
        "findings": findings.items if findings else [],
        "log": text,
    }


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("command", choices=["analyze", "convert"])
    ap.add_argument("input")
    ap.add_argument("--out")
    ap.add_argument("--key")
    ap.add_argument("--reach", type=int, default=17)
    ap.add_argument("--comfortable", type=int, default=14)
    ap.add_argument("--detail", default="full")
    try:
        a = ap.parse_args()
    except SystemExit:
        print(json.dumps({"ok": False, "error": "Bad arguments."}))
        return 2

    try:
        if a.command == "analyze":
            result = do_analyze(a.input)
        else:
            out = a.out or a.input.rsplit(".", 1)[0] + ".musicxml"
            result = do_convert(a.input, out, a.key, a.reach,
                                a.comfortable, a.detail)
    except Exception as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    print(json.dumps(result, indent=1))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
