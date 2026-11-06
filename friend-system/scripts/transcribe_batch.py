#!/usr/bin/env python3
"""Transcribe many source clips in one process (model loaded once), read-only.

Usage: transcribe_batch.py [--language lv] <clip> [<clip> ...]

Always pass --language for this user's footage (Latvian). Auto-detect misfires on short clips:
it turned "Krēsli, krēsli" into Russian and "Ū, šis ir labs!" into English nonsense.

Cache: ~/.cache/video-editor/transcripts/<basename>.<bytes>.json — keyed by name+size so the
same footage is never transcribed twice, even before it has been assigned to a job.
Each file has the same schema as projects/<job>/transcript/words.json.
"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import json, os, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcribe import MODEL, pick_device, probe_duration  # noqa: E402

CACHE = Path.home() / ".cache/video-editor/transcripts"


def key(p, language=None):
    """Keyed by name+size+language: the same clip transcribed as 'lv' and as 'en' are different results the personal-brand clips are ENGLISH and a cached lv pass returned one line per clip)."""
    lang = f".{language}" if language else ""
    return CACHE / f"{p.name}.{p.stat().st_size}{lang}.json"


def main():
    argv = sys.argv[1:]
    language = None
    if "--language" in argv:
        i = argv.index("--language"); language = argv[i + 1]; del argv[i:i + 2]
    clips = [Path(a) for a in argv]
    if not clips:
        sys.exit("usage: transcribe_batch.py <clip> [...]")
    CACHE.mkdir(parents=True, exist_ok=True)
    todo = [c for c in clips if not key(c, language).exists()]
    for c in clips:
        if c not in todo:
            print(f"cached  {key(c, language).name}")
    if not todo:
        return

    import whisperx
    device, ct = pick_device()
    print(f"device={device}/{ct} model={MODEL} — loading (first run downloads ~3 GB)", flush=True)
    model = whisperx.load_model(MODEL, device, compute_type=ct, language=language)
    align = {}

    for i, c in enumerate(todo, 1):
        t0 = time.time()
        audio = whisperx.load_audio(str(c))
        res = model.transcribe(audio, batch_size=4, language=language)
        lang = language or res.get("language", "en")
        if lang not in align:
            align[lang] = whisperx.load_align_model(language_code=lang, device=device)
        am, meta = align[lang]
        al = whisperx.align(res["segments"], am, meta, audio, device, return_char_alignments=False)
        words = [{"word": (w.get("word") or "").strip(),
                  "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)}
                 for s in al.get("segments", []) for w in s.get("words", [])
                 if w.get("start") is not None and w.get("end") is not None]
        payload = {"source": str(c), "duration": round(probe_duration(c), 3), "language": lang, "language_forced": bool(language),
                   "model": MODEL, "device": f"{device}/{ct}",
                   "text": " ".join(s["text"].strip() for s in res["segments"]),
                   "words": words}
        key(c, language).write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"[{i}/{len(todo)}] {c.name}  lang={lang}  {len(words)} words  "
              f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
