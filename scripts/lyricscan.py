"""Scan files about to be committed for real-song lyric text. Prints file paths and match counts only, never lyric text."""
import json, re, sys, glob, os
from collections import Counter

REPO = r"C:\Users\OpenSrcerer\Desktop\playground\mv-harness"
N = 5
tok = lambda s: re.findall(r"[a-z']+", s.lower())


def texts_from(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("plainLyrics", "syncedLyrics", "text", "word", "lyrics", "plain"):
                yield from texts_from(v)
            elif isinstance(v, (dict, list)):
                yield from texts_from(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from texts_from(v)


src = []
for p in glob.glob(os.path.join(REPO, r"tests\.cache\real\*\lyrics_src\*.json")) + \
        glob.glob(os.path.join(REPO, r"tests\.cache\real\*\whisper_cpu\*_lead_vocals.json")) + \
        glob.glob(os.path.join(REPO, r"tests\.cache\real\*\align_mms\*_words.json")):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    words = []
    for t in texts_from(d):
        words += tok(re.sub(r"\[\d+:\d+\.\d+\]", " ", t))
    src.append((p, words))

grams = set()
for _, w in src:
    for i in range(len(w) - N + 1):
        g = tuple(w[i:i + N])
        if len(set(g)) >= 3:
            grams.add(g)
print("lyric sources:", len(src), "distinct 5-grams:", len(grams))

files = open(sys.argv[1], encoding="utf-8").read().split("\n")
hits = []
for f in files:
    if not f:
        continue
    p = os.path.join(REPO, f)
    try:
        b = open(p, "rb").read()
        if b"\0" in b[:4096]:
            continue
        w = tok(b.decode("utf-8", "ignore"))
    except Exception:
        continue
    c = sum(1 for i in range(len(w) - N + 1) if tuple(w[i:i + N]) in grams)
    if c:
        hits.append((c, f))
for c, f in sorted(hits, reverse=True):
    print(c, f)
print("files with matches:", len(hits))
