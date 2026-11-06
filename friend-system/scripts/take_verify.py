#!/usr/bin/env python3
"""Which wording does the AUDIO fit best? Forced-aligns each candidate sentence against one attempt and ranks them
by the aligner's word confidence. Built for the cases Whisper's text cannot settle: numbers ("forty" vs "fifty"
vs "twenty"), prices, names. Numbers are spelled out in the candidates (the aligner cannot score digits).

Usage (whisperx venv):
  take_verify.py <job> <clip> <start> <end> "candidate one" "candidate two" ...
Prints, per candidate, the mean confidence over all words and over the words that differ between candidates.
It ranks; it does not hear. A margin under ~0.1 means the candidates are not separable: ask the speaker."""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def main():
    job, clip, s, e, *cands = sys.argv[1:]
    s, e = float(s), float(e)
    import whisperx
    audio = whisperx.load_audio(str(ROOT / "projects" / job / "raw" / clip))
    s0, e0 = max(0, s - 0.25), e + 0.25
    chunk = audio[int(s0 * 16000):int(e0 * 16000)]
    model, meta = whisperx.load_align_model(language_code=json.loads((ROOT / "projects" / job / "job.json").read_text()).get("language", "en"), device="cpu")
    split = [c.lower().split() for c in cands]
    common = set(split[0]).intersection(*split[1:]) if len(split) > 1 else set()
    rows = []
    for c in cands:
        r = whisperx.align([{"text": c, "start": 0.0, "end": len(chunk) / 16000}], model, meta, chunk, "cpu")
        ws = [w for seg in r["segments"] for w in seg["words"]]
        sc = [(w["word"], round(float(w.get("score", 0)), 2)) for w in ws]
        allm = sum(x for _, x in sc) / len(sc)
        diff = [x for w, x in sc if w.lower() not in common] or [x for _, x in sc]
        rows.append((sum(diff) / len(diff), allm, c, sc))
    for d, a, c, sc in sorted(rows, reverse=True):
        print(f"differing words {d:.2f}   all words {a:.2f}   {c}")
        print("      " + "  ".join(f"{w}:{x}" for w, x in sc))

main()
