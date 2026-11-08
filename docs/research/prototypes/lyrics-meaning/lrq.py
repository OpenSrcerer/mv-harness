import json, urllib.request, urllib.parse, re, sys, time
UA = "mv-harness-research/0.1 (https://github.com/OpenSrcerer)"
def get(path, params):
    url = "https://lrclib.net" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t=time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read(); code=r.status; hdr=dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read(); code=e.code; hdr=dict(e.headers)
    return code, json.loads(body or b"null"), hdr, time.time()-t
def summarize(o):
    if not isinstance(o, dict): return o
    s = {k:v for k,v in o.items() if k not in ("syncedLyrics","plainLyrics")}
    sl = o.get("syncedLyrics"); pl = o.get("plainLyrics")
    s["synced_lines"] = len([l for l in (sl or "").splitlines() if re.match(r"\[\d+:\d+", l)])
    s["synced_nonempty_lines"] = len([l for l in (sl or "").splitlines() if re.match(r"\[\d+:\d+[.:]\d+\]\s*\S", l)])
    s["has_word_tags"] = bool(re.search(r"<\d+:\d+\.\d+>", sl or ""))
    s["plain_lines"] = len([l for l in (pl or "").splitlines() if l.strip()])
    if sl:
        ts = re.findall(r"^\[(\d+):(\d+\.\d+)\]", sl, re.M)
        if ts: s["first_ts"]=ts[0]; s["last_ts"]=ts[-1]
    return s
songs = [("MEGAFAUNA","KITCALIBER","HALCYONDAZE",217),("Versatile","Cosmic","Versatile",228)]
for t,a,al,d in songs:
    for path, p in [("/api/get",{"track_name":t,"artist_name":a,"album_name":al,"duration":d}),
                    ("/api/get-cached",{"track_name":t,"artist_name":a,"album_name":al,"duration":d}),
                    ("/api/get",{"track_name":t,"artist_name":a})]:
        c,o,h,dt = get(path,p)
        print(path, p, c, round(dt,2), json.dumps(summarize(o)))
    c,o,h,dt = get("/api/search",{"track_name":t,"artist_name":a})
    print("search", t, a, c, len(o) if isinstance(o,list) else o, [summarize(x) for x in (o or [])][:5] if isinstance(o,list) else "")
    c,o,h,dt = get("/api/search",{"q":t})
    print("search q", t, c, len(o) if isinstance(o,list) else o, [ (x.get("artistName"),x.get("trackName"),x.get("duration"), bool(x.get("syncedLyrics"))) for x in (o or [])][:10] if isinstance(o,list) else "")
print("headers sample:", {k:v for k,v in h.items()})
