#!/usr/bin/env python3
"""Split every raw clip into TAKES (loud spans from the silence map) and transcribe each span on its own.

Why: a full-clip WhisperX pass drops or smears repeated takes — on the gratitude clips it returned 2 words for a
26 s clip, and pinned late words onto early takes. Per-span transcription (windowed, padded) is the honest read:
one entry per attempt, with word timings in the clip's own timebase.

Usage (whisperx venv):  takes.py <job> [--language en] [--db 35] [--min 0.5] [--merge 0.45] [--prompt "Acme, Product Name"]
--prompt is a list of names and keywords handed to Whisper as its initial prompt, so brand names and jargon come out spelled right
("Claude", not "cloud"). Idea from a reference skill reviewed.
Writes projects/<job>/analysis/takes.json + prints a table. Then run take_pick.py <job> (which attempt of each line to use)."""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def silences(path, db, dur_min=0.20):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"silencedetect=noise=-{db}dB:d={dur_min}",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    spans, cur = [], None
    for line in out.splitlines():
        if "silence_start:" in line: cur = float(line.split("silence_start:")[1].split()[0])
        elif "silence_end:" in line and cur is not None:
            spans.append((cur, float(line.split("silence_end:")[1].split()[0]))); cur = None
    if cur is not None: spans.append((cur, 10 ** 9))
    return spans


def loud_spans(path, duration, db, merge, min_len):
    sil = silences(path, db)
    loud, t = [], 0.0
    for s, e in sil:
        if s - t > 0.01: loud.append([t, s])
        t = min(e, duration)
    if duration - t > 0.01: loud.append([t, duration])
    merged = []
    for a, b in loud:
        if merged and a - merged[-1][1] <= merge: merged[-1][1] = b
        else: merged.append([a, b])
    return [(a, b) for a, b in merged if b - a >= min_len]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("job"); ap.add_argument("--language", default="en")
    ap.add_argument("--db", type=int, default=35); ap.add_argument("--min", type=float, default=0.5)
    ap.add_argument("--merge", type=float, default=0.45); ap.add_argument("--pad", type=float, default=0.35)
    ap.add_argument("--prompt", default=None, help="names / keywords Whisper should spell correctly")
    ap.add_argument("--file", action="append", help="explicit file(s) instead of everything in raw/ (e.g. a voiceover)")
    a = ap.parse_args()
    P = ROOT / "projects" / a.job
    clips = ([Path(f) if Path(f).is_absolute() else P / f for f in a.file] if a.file
             else sorted(p for p in (P / "raw").iterdir() if not p.name.startswith(".")))
    import whisperx
    model = whisperx.load_model("large-v3", "cpu", compute_type="int8", language=a.language,
                               asr_options=({"initial_prompt": a.prompt} if a.prompt else None))
    align = whisperx.load_align_model(language_code=a.language, device="cpu")
    result = {}
    for c in clips:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(c)],
                                   capture_output=True, text=True).stdout)
        spans = loud_spans(c, dur, a.db, a.merge, a.min)
        audio = whisperx.load_audio(str(c))
        takes = []
        for s, e in spans:
            s0, e0 = max(0, s - a.pad), min(dur, e + a.pad)
            chunk = audio[int(s0 * 16000):int(e0 * 16000)]
            r = model.transcribe(chunk, batch_size=4, language=a.language)
            if not r["segments"]:
                takes.append({"start": round(s, 2), "end": round(e, 2), "text": "", "words": []}); continue
            r = whisperx.align(r["segments"], *align, chunk, "cpu")
            # score = the aligner's confidence that this word is really in the audio at this spot. A swallowed,
            # clipped or mispronounced word scores low; take_pick.py ranks the attempts with it.
            words = [{"word": w["word"], "start": round(w.get("start", 0) + s0, 3), "end": round(w.get("end", 0) + s0, 3),
                      "score": round(float(w.get("score", 0)), 3)}
                     for seg in r["segments"] for w in seg.get("words", []) if "start" in w]
            takes.append({"start": round(s, 2), "end": round(e, 2), "text": " ".join(w["word"] for w in words), "words": words})
        result[c.name] = {"duration": round(dur, 3), "takes": takes}
        print(f"===== {c.name}  {dur:.1f}s  {len(takes)} takes")
        for t in takes:
            print(f"  {t['start']:6.2f}-{t['end']:6.2f} ({t['end']-t['start']:5.2f}s)  {t['text'][:120]}")
    (P / "analysis").mkdir(exist_ok=True)
    (P / "analysis" / "takes.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print("->", P / "analysis" / "takes.json")


if __name__ == "__main__":
    main()
