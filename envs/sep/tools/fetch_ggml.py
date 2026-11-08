"""Fetch + SHA-pin ggml whisper and Silero VAD models (HF, pinned to commit revisions) into %LOCALAPPDATA%\mvh\models\ggml.
Merges ggml.* entries into envs/sep/models.fragment.json. Run with any env that has `requests`."""
import hashlib, json, os, sys, time
from pathlib import Path
import requests

DEST = Path(os.environ["LOCALAPPDATA"]) / "mvh" / "models" / "ggml"
FRAG = Path(__file__).resolve().parents[1] / "models.fragment.json"
ITEMS = [
    ("ggml.whisper-large-v3-turbo-q8_0", "ggerganov/whisper.cpp", "5359861c739e955e79d9a303bcbc70fb988958b1", "ggml-large-v3-turbo-q8_0.bin", ["lyrics"], "MIT (OpenAI Whisper weights, converted by whisper.cpp)"),
    ("ggml.whisper-large-v3", "ggerganov/whisper.cpp", "5359861c739e955e79d9a303bcbc70fb988958b1", "ggml-large-v3.bin", ["lyrics"], "MIT (OpenAI Whisper weights, converted by whisper.cpp)"),
    ("ggml.silero-vad-v5.1.2", "ggml-org/whisper-vad", "9ffd54a1e1ee413ddf265af9913beaf518d1639b", "ggml-silero-v5.1.2.bin", ["lyrics"], "MIT (Silero VAD v5.1.2, ggml conversion)"),
]
DEST.mkdir(parents=True, exist_ok=True)
frag = json.loads(FRAG.read_text(encoding="utf-8")) if FRAG.exists() else {"models": []}
for mid, repo, rev, fn, used, lic in ITEMS:
    url = f"https://huggingface.co/{repo}/resolve/{rev}/{fn}"
    p = DEST / fn
    h = requests.head(url, allow_redirects=True, timeout=60)
    h.raise_for_status()
    # LFS sha256 is the etag on the resolve redirect
    r0 = requests.head(url, allow_redirects=False, timeout=60)
    want = (r0.headers.get("x-linked-etag") or r0.headers.get("etag") or "").strip('"')
    size = int(h.headers.get("content-length", 0))
    if not (p.exists() and p.stat().st_size == size):
        t = time.time(); tmp = p.with_suffix(".part")
        with requests.get(url, stream=True, timeout=120) as r, open(tmp, "wb") as f:
            r.raise_for_status()
            for ch in r.iter_content(1 << 20):
                f.write(ch)
        os.replace(tmp, p)
        print(fn, "downloaded", f"{time.time()-t:.0f}s", flush=True)
    sha = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            sha.update(b)
    sha = sha.hexdigest()
    ok = (sha == want) if len(want) == 64 else None
    print(fn, p.stat().st_size, sha, "matches LFS etag" if ok else ("MISMATCH vs " + want if ok is False else "no LFS etag"), flush=True)
    if ok is False:
        sys.exit(2)
    entry = dict(id=mid, envs=["main", "ffmpeg-whisper"], files=[dict(path=f"ggml/{fn}", url=url, revision=rev, sha256=sha, size=p.stat().st_size)],
                 licence=lic, used_by=used)
    frag["models"] = [e for e in frag["models"] if e["id"] != mid] + [entry]
    FRAG.write_text(json.dumps(frag, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
