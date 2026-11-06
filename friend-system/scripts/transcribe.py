#!/usr/bin/env python3
"""Transcribe one job's raw clip with WhisperX, word-level. Cached forever.

Usage: transcribe.py <job-name> [--force] [--language lv]

Writes projects/<job>/transcript/words.json:
  {"source": ..., "duration": float, "device": "...", "words": [{"word","start","end"}, ...]}

Device policy:
  NVIDIA GPU present  -> cuda / float16
  otherwise           -> cpu / int8   (Apple Silicon included: MPS is unreliable here)
  CUDA failure at any point falls back to CPU int8 rather than blocking the edit.
"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "large-v3"


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def pick_device():
    if shutil.which("nvidia-smi"):
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, check=True, timeout=20)
            return "cuda", "float16"
        except Exception:
            pass
    return "cpu", "int8"


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def run(audio, device, compute_type, language=None):
    import whisperx
    model = whisperx.load_model(MODEL, device, compute_type=compute_type, language=language)
    audio_data = whisperx.load_audio(str(audio))
    result = model.transcribe(audio_data, batch_size=8 if device == "cuda" else 4, language=language)
    lang = language or result.get("language", "en")
    align_model, meta = whisperx.load_align_model(language_code=lang, device=device)
    aligned = whisperx.align(result["segments"], align_model, meta, audio_data, device,
                             return_char_alignments=False)
    return aligned, lang


def main():
    argv = sys.argv[1:]
    language = None
    if "--language" in argv:
        i = argv.index("--language"); language = argv[i + 1]; del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("-")]
    force = "--force" in argv
    if not args:
        die("usage: transcribe.py <job-name> [--force]")
    job = args[0]
    jobdir = ROOT / "projects" / job
    rawdir, tdir = jobdir / "raw", jobdir / "transcript"
    if not rawdir.is_dir():
        die(f"no such job: {jobdir}")

    clips = [p for p in sorted(rawdir.iterdir())
             if p.is_file() and not p.name.startswith(".")]
    if not clips:
        die(f"no clip in {rawdir}")
    src = clips[0]

    out = tdir / "words.json"
    if out.exists() and not force:
        n = len(json.loads(out.read_text()).get("words", []))
        print(f"cached: {out} ({n} words) — pass --force to redo")
        return
    tdir.mkdir(parents=True, exist_ok=True)

    device, compute_type = pick_device()
    print(f"device={device} compute_type={compute_type} model={MODEL}")
    print(f"source: {src.name}")

    try:
        aligned, lang = run(src, device, compute_type, language)
    except Exception as e:
        if device != "cuda":
            raise
        print(f"CUDA path failed ({type(e).__name__}: {e}) — falling back to CPU int8",
              file=sys.stderr)
        device, compute_type = "cpu", "int8"
        aligned, lang = run(src, device, compute_type, language)

    words = []
    for seg in aligned.get("segments", []):
        for w in seg.get("words", []):
            if w.get("start") is None or w.get("end") is None:
                continue  # unalignable token (digits, symbols) — no timestamp to trust
            words.append({
                "word": (w.get("word") or w.get("text") or "").strip(),
                "start": round(float(w["start"]), 3),
                "end": round(float(w["end"]), 3),
            })

    payload = {
        "source": str(src.relative_to(ROOT)),
        "duration": round(probe_duration(src), 3),
        "language": lang,
        "language_forced": bool(language),
        "model": MODEL,
        "device": f"{device}/{compute_type}",
        "words": words,
    }
    out.write_text(json.dumps(payload, indent=2))
    print(f"wrote {out}  —  {len(words)} words, {payload['duration']}s, lang={lang}")


if __name__ == "__main__":
    main()
