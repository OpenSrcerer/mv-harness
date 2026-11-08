"""Task 1+2: identity (ffprobe tags, chromaprint, MusicBrainz) and LRCLIB cascade per PLAN 5. Prints NO lyric text."""
import sys, os, json, re, time, subprocess, urllib.request, urllib.parse, urllib.error
sys.path.insert(0, os.path.dirname(__file__))
from bw_common import *
from rapidfuzz import fuzz
UA = "mv-harness/0.0-dev (https://github.com/OpenSrcerer/mv-harness)"
_last = [0.0]
def http(url, gap):
    w = gap - (time.time() - _last[0])
    if w > 0: time.sleep(w)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body, code, hdr = r.read(), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        body, code, hdr = e.read(), e.code, dict(e.headers)
    _last[0] = time.time()
    return code, body, hdr, time.time() - t
def probe(path):
    o = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration:format_tags:stream=codec_name,sample_rate,channels", "-of", "json", path], capture_output=True, check=True).stdout
    return json.loads(o)
def chroma(path):
    r = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0", "-vn", "-t", "120", "-f", "chromaprint", "-fp_format", "base64", "-"], capture_output=True)
    return r.stdout.decode().strip(), r.returncode
def norm(s): return re.sub(r"\s*[\(\[].*?[\)\]]", "", s or "").strip().lower()
def lr_summary(o):
    if not isinstance(o, dict): return None
    s = {k: o.get(k) for k in ("id", "trackName", "artistName", "albumName", "duration", "instrumental")}
    sl = o.get("syncedLyrics") or ""
    s["has_synced"] = bool(sl); s["has_plain"] = bool(o.get("plainLyrics"))
    s["synced_lines"] = len(re.findall(r"^\[\d+:\d+", sl, re.M))
    s["word_tags"] = bool(re.search(r"<\d+:\d+\.\d+>", sl))
    return s
def run(slug):
    path = SONGS[slug]; http_dir = sdir(slug, "http"); res = {"slug": slug}
    pr = probe(path); tags = {k.lower(): v for k, v in pr["format"].get("tags", {}).items()}
    dur = float(pr["format"]["duration"])
    res["tags"] = {k: v for k, v in tags.items() if "lyric" not in k}
    res["embedded_lyrics_tag"] = {k: len(v) for k, v in tags.items() if "lyric" in k}
    res["duration_s"] = dur; res["stream"] = pr["streams"][0]
    fp, rc = chroma(path); res["chromaprint"] = {"rc": rc, "len_chars": len(fp), "head": fp[:24]}
    open(os.path.join(sdir(slug, "identity"), "chromaprint.txt"), "w").write(fp)
    title, artist, album = tags.get("title"), tags.get("artist"), tags.get("album")
    # ---- MusicBrainz (1 req/s)
    mb = {}
    def mbq(path_, params, name):
        params = dict(params, fmt="json")
        c, b, h, dt = http("https://musicbrainz.org/ws/2/" + path_ + "?" + urllib.parse.urlencode(params), 1.1)
        open(os.path.join(sdir(slug, "identity"), f"mb_{name}.json"), "wb").write(b)
        return c, (json.loads(b) if c == 200 else None)
    q = f'recording:"{title}" AND artist:"{artist}"'
    c, o = mbq("recording", {"query": q, "limit": 8}, "search")
    mb["query_used"] = "full_title"
    if not (o or {}).get("count") and norm(title) != title.lower():
        q = f'recording:"{norm(title)}" AND artist:"{artist}"'
        c, o = mbq("recording", {"query": q, "limit": 8}, "search_normtitle"); mb["query_used"] = "title_without_parentheses"
    cands = []
    for r in (o or {}).get("recordings", []):
        L = (r.get("length") or 0) / 1000
        cands.append({"title": r.get("title"), "score": r.get("score"), "len_s": L, "ddur": round(L - dur, 2) if L else None,
                      "artist": [a["name"] for a in r.get("artist-credit", [])], "releases": [x.get("title") for x in r.get("releases", [])][:2], "id": r.get("id")})
    mb["search_status"] = c; mb["count"] = (o or {}).get("count"); mb["cands"] = cands[:6]
    acc = [x for x in cands if (x["score"] or 0) >= 90 and x["len_s"] and abs(x["ddur"]) <= 3]
    mb["accepted_score90_dur3s"] = acc[:1]
    if tags.get("isrc"):
        c2, o2 = mbq("isrc/" + tags["isrc"], {"inc": "artist-credits+releases"}, "isrc")
        mb["isrc_status"] = c2; mb["isrc_recordings"] = [{"title": r.get("title"), "len_s": (r.get("length") or 0) / 1000, "id": r.get("id")} for r in (o2 or {}).get("recordings", [])]
    res["musicbrainz"] = mb
    # ---- LRCLIB cascade
    pool = {}; log = []
    def rec(name, url):
        c, b, h, dt = http(url, 0.4)
        open(os.path.join(http_dir, name + ".json"), "wb").write(b)
        try: o = json.loads(b or b"null")
        except Exception: o = None
        log.append({"step": name, "status": c, "secs": round(dt, 2), "retry_after": h.get("Retry-After")})
        return c, o
    d = round(dur)
    base = {"track_name": title, "artist_name": artist}
    c, o = rec("get_with_album", "https://lrclib.net/api/get?" + urllib.parse.urlencode({**base, "album_name": album or "", "duration": d}))
    if c == 200 and isinstance(o, dict): pool[o["id"]] = ("get_album", o)
    c, o = rec("get_no_album", "https://lrclib.net/api/get?" + urllib.parse.urlencode({**base, "duration": d}))
    if c == 200 and isinstance(o, dict): pool.setdefault(o["id"], ("get_noalbum", o))
    c, o = rec("search_track_artist", "https://lrclib.net/api/search?" + urllib.parse.urlencode(base))
    for x in (o or []) if isinstance(o, list) else []: pool.setdefault(x["id"], ("search", x))
    c, o = rec("search_q", "https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": f"{title} {artist}"}))
    for x in (o or []) if isinstance(o, list) else []: pool.setdefault(x["id"], ("search_q", x))
    ranked = []
    for i, (src, x) in pool.items():
        ts = fuzz.token_set_ratio(norm(title), norm(x.get("trackName"))); ar = fuzz.token_set_ratio(norm(artist), norm(x.get("artistName")))
        dd = (x.get("duration") or 0) - dur
        s = lr_summary(x); s.update(src=src, title_sim=round(ts), artist_sim=round(ar), ddur=round(dd, 3))
        s["passes_text_gate"] = ts >= 90 and ar >= 85
        ranked.append(s)
    ranked.sort(key=lambda s: (not s["passes_text_gate"], abs(s["ddur"]), not s["has_synced"]))
    res["lrclib"] = {"log": log, "pool_size": len(pool), "ranked": ranked[:8]}
    gate = [s for s in ranked if s["passes_text_gate"]]
    ch = gate[0] if gate else None
    if ch:
        ch = dict(ch); ad = abs(ch["ddur"])
        ch["verdict"] = "accept" if ad <= 2 else ("accept_flag_version_mismatch" if ad <= 5 else "reject")
        if ch["verdict"] != "reject": 
            o = pool[ch["id"]][1]
            json.dump(o, open(os.path.join(sdir(slug, "lyrics_src"), "chosen_lrclib.json"), "w", encoding="utf-8"))
    res["lrclib"]["chosen"] = ch
    json.dump(res, open(os.path.join(sdir(slug, "identity"), "identity_lrclib_summary.json"), "w"), indent=1)
    return res
if __name__ == "__main__":
    for slug in (sys.argv[1:] or list(SONGS)):
        r = run(slug)
        print("=" * 8, slug, json.dumps({k: r[k] for k in ("tags", "embedded_lyrics_tag", "duration_s", "chromaprint")}))
        print(" MB:", json.dumps(r["musicbrainz"])[:900])
        print(" LRCLIB:", json.dumps({"log": r["lrclib"]["log"], "pool": r["lrclib"]["pool_size"], "chosen": r["lrclib"]["chosen"]}))
        print(" ranked:", json.dumps([(s["id"], s["src"], s["title_sim"], s["artist_sim"], s["ddur"], s["has_synced"]) for s in r["lrclib"]["ranked"][:6]]))
