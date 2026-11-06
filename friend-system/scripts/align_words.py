#!/usr/bin/env python3
"""Correct word timings for lines that contain NUMBERS. Whisper's aligner cannot place digits: "122" gets ~0.08 s and
the rest of the line is squeezed ahead of the audio, so the last 1-1.7 s of speech looks like silence. Cutting or captioning from
those timings clips the end of the line.

Fix: align the VERIFIED wording with every number spelled out ("one hundred twenty two"), then merge each spelled
group back into one digit token spanning the group.

Input  transcript/lines.json: [{"id","clip","start","end","text"}]   text = what is said, numbers as digits, with
       the punctuation wanted on screen. Verify the numbers first (take_verify.py).
Output transcript/words_aligned.json: {id: {"clip","words":[{"w","s","e","score"}]}}   times in SOURCE seconds.
Usage (whisperx venv): align_words.py <job>"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import json, sys, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

def spell(n):
    if n < 20: return [ONES[n]]
    if n < 100: return [TENS[n // 10]] + ([ONES[n % 10]] if n % 10 else [])
    if n < 1000: return [ONES[n // 100], "hundred"] + (spell(n % 100) if n % 100 else [])
    return spell(n // 1000) + ["thousand"] + (spell(n % 1000) if n % 1000 else [])

def main():
    job = sys.argv[1]; P = ROOT / "projects" / job
    lang = json.loads((P / "job.json").read_text()).get("language", "en") if (P / "job.json").exists() else "en"
    lines = json.loads((P / "transcript" / "lines.json").read_text())
    import whisperx
    model, meta = whisperx.load_align_model(language_code=lang, device="cpu")
    out = {}
    for L in lines:
        audio = whisperx.load_audio(str(P / "raw" / L["clip"]))
        s0, e0 = max(0, L["start"] - 0.3), L["end"] + 0.3
        chunk = audio[int(s0 * 16000):int(e0 * 16000)]
        disp = L["text"].split(); spoken, group = [], []
        for gi, tok in enumerate(disp):
            core = re.sub(r"[^\w']", "", tok)
            ws = [x for x in (spell(int(core)) if core.isdigit() else [tok.lower().strip(".,?!")]) if x]
            spoken += ws; group += [gi] * len(ws)
        r = whisperx.align([{"text": " ".join(spoken), "start": 0.0, "end": len(chunk) / 16000}], model, meta, chunk, "cpu")
        aw = [w for seg in r["segments"] for w in seg["words"]]
        if len(aw) != len(spoken): sys.exit(f"{L['id']}: aligner returned {len(aw)} words for {len(spoken)}")
        words = []
        for gi, tok in enumerate(disp):
            g = [aw[i] for i in range(len(aw)) if group[i] == gi]
            sc = [float(x.get("score", 0)) for x in g]
            words.append({"w": tok, "s": round(g[0]["start"] + s0, 3), "e": round(g[-1]["end"] + s0, 3), "score": round(min(sc), 2)})
        out[L["id"]] = {"clip": L["clip"], "words": words}
        print(f"{L['id']:12s} {L['clip']} {words[0]['s']:.2f}-{words[-1]['e']:.2f}  min score {min(w['score'] for w in words):.2f}   "
              + " ".join(f"{w['w']}[{w['s']-words[0]['s']:.2f}]" for w in words))
    (P / "transcript" / "words_aligned.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

main()
