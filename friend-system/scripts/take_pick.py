#!/usr/bin/env python3
"""Which attempt of each line goes in the video. Run after takes.py, BEFORE writing the cut list.

Why: "problems truly have occurred where I've done multiple takes for a video but you select the
wrong one ... always go through the footage and find the correct take where I say every word fully and there
aren't mispronunciations or incomplete words/sentences that I redo better."

What it does
  pick  <job>   Groups consecutive takes that are attempts at the SAME line, then judges every attempt:
                  complete   it reaches the end of the line (length vs the longest attempt; no dangling last word)
                  weak words the aligner's confidence per word (takes.py). Low = swallowed, clipped or mispronounced.
                             Also judged against the SAME word in the other attempts.
                  ending     the last word is not shorter than the speaker says it elsewhere (a swallowed ending)
                  stumbles   a repeated word, a restart, or a pause inside the take
                The pick is the LAST complete attempt (the speaker redoes a line until it is right) unless it has a defect
                that an earlier complete attempt does not. Everything is printed, nothing is hidden.
                Writes analysis/take_pick.json.
  check <job>   Every cut in transcript/cuts.json must lie inside a PICKED attempt, or carry
                "take_override": "<why>" (the speaker's own choice of wording, for example). Exit 1 otherwise.
                deliver.py-style gate: run it after any change to the cut list.

It cannot hear. Low scores are a strong hint, not a verdict. VERIFY means: cut that attempt's audio out on its own,
transcribe it again alone, and put the flagged word with its clip and timecode in front of the speaker with the cut list.
When two complete attempts are worded differently, the choice of wording is the speaker's.

Usage (any python):  take_pick.py pick <job> [--weak 0.5]     take_pick.py check <job>"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, re, statistics, sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Words a finished sentence never ends on. HARD ones count as unfinished even when Whisper adds a full stop
# ("five days was around." / "cost us around"); SOFT ones can end a sentence ("looked like.") and only count as
# unfinished without a terminal . ? !
HARD = {"and", "the", "a", "an", "till", "until", "that", "but", "so", "because", "with", "for", "or",
        "if", "when", "we", "they", "around", "about", "was", "were", "are", "our", "my", "only", "than", "by",
        "un", "ir", "ka", "kas", "ar", "par", "no", "uz", "lai", "bet", "jo", "kad", "tu", "es"}
# "up" and "of" end real sentences ("lift each other up.", "content you'd like to see more of."): SOFT, i.e. unfinished only without a full stop
SOFT = {"you", "your", "i", "it's", "is", "in", "like", "it", "up", "of", "out", "off", "over", "to"}
DANGLING = HARD | SOFT


def norm(w): return re.sub(r"[^\w']+", "", w.lower(), flags=re.UNICODE)


def same_line(a, b, need=0.6):
    """Are word lists a and b attempts at the same line? Same opening, or the shorter one sits inside the longer
    ('Latvians have a saying' inside 'Did you know that Latvians have a saying, which ...')."""
    if not a or not b: return False
    n = min(len(a), len(b), 8)
    if n < 2: return a[0] == b[0]
    if SequenceMatcher(None, a[:n], b[:n]).ratio() >= need: return True
    if need > 0.6: return False                                # containment only counts inside one clip
    sh, lo = (a, b) if len(a) <= len(b) else (b, a)
    m = SequenceMatcher(None, sh, lo).find_longest_match(0, len(sh), 0, len(lo)).size
    return m >= 3 and m >= 0.9 * len(sh)


def unfinished(t):
    """Trails off: ends on '...', on a word a sentence cannot end on, or on a SOFT word without a full stop.
    In the same clip, whatever follows is the retry."""
    last = t["words"][-1]["word"].rstrip(); k = t["norm"][-1]
    if last.endswith(("...", "\u2026")) or k in HARD: return True
    return k in SOFT and not last.endswith((".", "?", "!"))


def judge(job, weak):
    P = ROOT / "projects" / job
    data = json.loads((P / "analysis" / "takes.json").read_text())
    flat = []
    for clip, d in data.items():
        for i, t in enumerate(d["takes"], 1):
            if not t["words"]: continue
            if "score" not in t["words"][0]:
                sys.exit("takes.json has no word scores - re-run takes.py (it now records them)")
            flat.append({"clip": clip, "n": i, "start": t["start"], "end": t["end"], "words": t["words"],
                         "norm": [norm(w["word"]) for w in t["words"]], "text": t["text"]})
    lines, cur = [], []
    for t in flat:                                              # consecutive attempts at the same line, clips included
        # a new clip is usually a new line, so across clips the openings must match closely (0.75) to be a retry
        if cur and (any(same_line(t["norm"], c["norm"], 0.6 if c["clip"] == t["clip"] else 0.75) for c in cur)
                    or (cur[-1]["clip"] == t["clip"] and unfinished(cur[-1]))): cur.append(t)
        else:
            if cur: lines.append(cur)
            cur = [t]
    if cur: lines.append(cur)

    out = []
    for li, att in enumerate(lines, 1):
        longest = max(len(a["norm"]) for a in att)
        best_score, durs = {}, {}                              # the same word across attempts
        for a in att:
            for w, k in zip(a["words"], a["norm"]):
                best_score[k] = max(best_score.get(k, 0), w["score"]); durs.setdefault(k, []).append(w["end"] - w["start"])
        for a in att:
            ws, ks = a["words"], a["norm"]; flags = []
            # the LAST attempt is the one the speaker stopped on, so a shorter wording there is a decision, not a false start
            need = 0.5 if a is att[-1] else 0.8
            a["complete"] = len(ks) >= need * longest and not unfinished(a)
            if not a["complete"]:
                flags.append(f"trails off on '{ws[-1]['word']}'" if unfinished(a) else "stops early")
            # Words of 4+ letters carry the meaning and are judged strictly, also against the same word in the
            # other attempts. Short joining words (it, and, the) are normally reduced in speech and score low in
            # good takes too, so they are only noted when nearly absent, and never decide the pick.
            # The aligner cannot score digits, and the word after a numeral ("120 euros") inherits a bogus low score.
            # Neither is judged here; take_verify.py settles numbers by aligning spelled-out candidates.
            after_num = [i > 0 and any(c.isdigit() or c in "$\u20ac" for c in ws[i - 1]["word"]) for i in range(len(ws))]
            wk = [w for i, (w, k) in enumerate(zip(ws, ks)) if len(k) >= 4 and not after_num[i] and
                  (w["score"] < weak or (best_score[k] - w["score"] >= 0.25 and w["score"] < 0.7))]
            soft = [w for w, k in zip(ws, ks) if len(k) < 4 and w["score"] < 0.3]
            a["weak"] = [{"word": w["word"], "score": w["score"], "at": w["start"]} for w in wk]
            if wk: flags.append("UNCLEAR: " + ", ".join(f"{w['word']} {w['score']:.2f} at {w['start']:.2f}s" for w in wk))
            if soft: flags.append("(short word barely audible: " + ", ".join(f"{w['word']} {w['score']:.2f}" for w in soft) + ")")
            last, lk = ws[-1], ks[-1]
            med = statistics.median(durs[lk]); ld = last["end"] - last["start"]
            a["short_ending"] = len(durs[lk]) > 1 and len(lk) >= 5 and ld < 0.6 * max(durs[lk])
            if a["short_ending"]: flags.append(f"last word '{last['word']}' only {ld:.2f}s (the speaker says it in {max(durs[lk]):.2f}s elsewhere)")
            rep = [ks[i] for i in range(1, len(ks)) if ks[i] == ks[i - 1] and len(ks[i]) > 1
                   and ws[i - 1]["word"].rstrip()[-1:].isalnum()]          # "do, do it" is a sentence, "the the" is a stutter
            gaps = [round(ws[i]["start"] - ws[i - 1]["end"], 2) for i in range(1, len(ws)) if ws[i]["start"] - ws[i - 1]["end"] >= 0.6]
            tri = [" ".join(ks[i:i + 3]) for i in range(len(ks) - 2)]
            restart = any(tri[i] == tri[j] for i in range(len(tri)) for j in range(i + 3, len(tri)))   # not "over and over and over"
            if rep: flags.append("repeats '" + rep[0] + "'")
            if restart: flags.append("restarts inside the take")
            if gaps: flags.append(f"(pause {max(gaps)}s inside - check nothing was said there)")
            a["stumbles"] = bool(rep or restart)
            a["defects"] = len(a["weak"]) + a["short_ending"] + a["stumbles"]
            a["flags"] = flags
            a["mean"] = round(statistics.mean(w["score"] for w in ws), 3); a["min"] = min(w["score"] for w in ws)
        done = [a for a in att if a["complete"]]
        if not done:
            pick, why = att[-1], "NO complete attempt - last one taken; read it before using"
        else:
            pick = done[-1]
            why = ("last complete attempt, clean" + (" - VERIFY the pause" if any("pause" in f for f in pick["flags"]) else "")
                   if not pick["defects"] else None)
            if why is None:
                cleaner = [a for a in done if a["defects"] < pick["defects"]]
                if cleaner:
                    pick = min(reversed(cleaner), key=lambda a: a["defects"])
                    why = "an earlier attempt is cleaner than the last one - VERIFY both"
                else:
                    why = "last complete attempt; it has flags and no attempt is cleaner - VERIFY"
        texts = {" ".join(a["norm"]) for a in done}
        out.append({"line": li, "attempts": att, "pick": pick, "why": why, "wording_differs": len(texts) > 1})
    return P, out


def cmd_pick(a):
    P, out = judge(a.job, a.weak)
    save = []
    for L in out:
        att, pick = L["attempts"], L["pick"]
        clips = sorted({x["clip"] for x in att})
        print(f"\nLINE {L['line']}  {', '.join(clips)}  ({len(att)} attempt{'s' if len(att) > 1 else ''})")
        for x in att:
            mark = "PICK" if x is pick else ("  ok" if x["complete"] else "   -")
            print(f" {mark} {x['clip'][-8:]} #{x['n']:<2d} {x['start']:6.2f}-{x['end']:6.2f}  {len(x['norm']):2d} words  "
                  f"min {x['min']:.2f}  {x['text'][:70]}")
            for fl in x["flags"]: print(f"{'':28s}! {fl}")
        print(f"   -> {pick['clip']} #{pick['n']} {pick['start']}-{pick['end']}: {L['why']}")
        if L["wording_differs"] and sum(x["complete"] for x in att) > 1:
            print("   -> the complete attempts are worded differently: the speaker's choice. Show the speaker the texts.")
        save.append({"line": L["line"], "why": L["why"], "wording_differs": L["wording_differs"],
                     "pick": {k: pick[k] for k in ("clip", "n", "start", "end", "text", "flags")},
                     "attempts": [{k: x[k] for k in ("clip", "n", "start", "end", "text", "complete", "flags", "mean", "min")} for x in att]})
    (P / "analysis" / "take_pick.json").write_text(json.dumps({"weak_below": a.weak, "lines": save}, indent=1, ensure_ascii=False))
    need = sum("VERIFY" in s["why"] or "NO complete" in s["why"] for s in save)
    print(f"\n{len(save)} lines, {need} to verify before the cut list is written -> {P / 'analysis' / 'take_pick.json'}")


def cmd_check(a):
    P = ROOT / "projects" / a.job
    pk = json.loads((P / "analysis" / "take_pick.json").read_text())["lines"]
    cuts = json.loads((P / "transcript" / "cuts.json").read_text())["cuts"]
    bad = 0
    for i, c in enumerate(cuts, 1):
        mid = (c["start"] + c["end"]) / 2
        hit = [(L, x) for L in pk for x in L["attempts"] if x["clip"] == c["source"] and x["start"] - 0.4 <= mid <= x["end"] + 0.4]
        if not hit:
            print(f"cut {i:2d} {c['source']} {c['start']:.2f}-{c['end']:.2f}: not inside any take   <-- check"); bad += 1; continue
        L, x = hit[0]; p = L["pick"]
        if x["clip"] == p["clip"] and x["n"] == p["n"]:
            print(f"cut {i:2d} line {L['line']:2d} attempt #{x['n']} = the pick")
        elif c.get("take_override"):
            print(f"cut {i:2d} line {L['line']:2d} attempt #{x['n']} (pick is #{p['n']}) - override: {c['take_override']}")
        else:
            print(f"cut {i:2d} line {L['line']:2d} uses attempt #{x['n']} {x['start']}-{x['end']} but the pick is "
                  f"{p['clip']} #{p['n']} {p['start']}-{p['end']}   <-- WRONG TAKE"); bad += 1
    print("\nevery cut uses the picked take" if not bad else f"\n{bad} cut(s) to fix"); sys.exit(1 if bad else 0)


ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("pick"); p.add_argument("job"); p.add_argument("--weak", type=float, default=0.5); p.set_defaults(fn=cmd_pick)
p = sub.add_parser("check"); p.add_argument("job"); p.set_defaults(fn=cmd_check)
a = ap.parse_args(); a.fn(a)
