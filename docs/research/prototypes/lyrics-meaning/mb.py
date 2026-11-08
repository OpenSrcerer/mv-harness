import sys; sys.stdout.reconfigure(encoding="utf-8")
import json, urllib.request, urllib.parse, time
UA = "mv-harness-research/0.1 ( https://github.com/OpenSrcerer )"
def mb(path, params):
    params = dict(params, fmt="json")
    url = "https://musicbrainz.org/ws/2/" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    time.sleep(1.1)
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, e.read()[:200]
c,o = mb("isrc/QM42K1758179", {"inc":"artist-credits+releases"})
print("ISRC", c, json.dumps([(r.get("title"), r.get("length"), [a["name"] for a in r.get("artist-credit",[])], r.get("id")) for r in o.get("recordings",[])]) if c==200 else o)
for q in ['recording:"MEGAFAUNA" AND artist:"KITCALIBER"','recording:"Versatile" AND artist:"Cosmic"','artist:"KITCALIBER"']:
    ent = "artist" if q.startswith("artist") else "recording"
    c,o = mb(ent, {"query":q, "limit":5})
    if ent=="recording":
        print(q, c, o.get("count"), [(r.get("title"), r.get("length"), [a["name"] for a in r.get("artist-credit",[])], r.get("score"), [rel.get("title") for rel in r.get("releases",[])][:2], r.get("id")) for r in o.get("recordings",[])])
    else:
        print(q, c, o.get("count"), [(a.get("name"), a.get("score"), a.get("country"), a.get("disambiguation"), a.get("id")) for a in o.get("artists",[])])
