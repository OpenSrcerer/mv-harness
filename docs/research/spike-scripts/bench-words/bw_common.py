"""Shared helpers for bench-words (no lyric text is ever printed)."""
import os, subprocess, json, sys
import numpy as np
REPO = r"C:\Users\OpenSrcerer\Desktop\playground\mv-harness"
CACHE = os.path.join(REPO, "tests", ".cache", "real")
FF = os.environ.get("MVH_FFMPEG") or r"C:\Users\OpenSrcerer\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
FP = FF.replace("ffmpeg.exe", "ffprobe.exe")
SONGS = {
    "jeremy": os.path.join(REPO, "songs", "Jeremy (Redux Version).flac"),
    "newton-vs-nye": os.path.join(REPO, "songs", "Sir Isaac Newton vs Bill Nye.flac"),
    "megafauna": r"C:\Users\OpenSrcerer\Desktop\playground\viz\MEGAFAUNA.flac",
    "versatile": r"C:\Users\OpenSrcerer\Desktop\playground\viz\Versatile.flac",
}
def sdir(slug, sub):
    d = os.path.join(CACHE, slug, sub); os.makedirs(d, exist_ok=True); return d
def load16k(path):
    out = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32).copy()
def stem_path(slug, name="lead_vocals"):
    return os.path.join(CACHE, slug, "sep", name + ".wav")

import re, json as _json
def lrc_lines(synced):
    out = []
    for ln in synced.splitlines():
        m = re.match(r"^\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)$", ln)
        if m and m.group(3).strip():
            out.append({"t": int(m.group(1)) * 60 + float(m.group(2)), "text": m.group(3).strip()})
    return out
def lyric_lines(slug):
    """Chosen LRCLIB synced lines for slug (jeremy 22859144, newton 3921433). Returns list of {t,text}."""
    http = sdir(slug, "http")
    if slug == "jeremy":
        o = [x for x in _json.load(open(os.path.join(http, "search_track_artist.json"), encoding="utf-8")) if x["id"] == 22859144][0]
    elif slug == "newton-vs-nye":
        o = _json.load(open(os.path.join(http, "get_with_album.json"), encoding="utf-8")); assert o["id"] == 3921433
    else:
        raise KeyError(slug)
    return lrc_lines(o["syncedLyrics"]), o
def norm_words(text):
    t = text.lower().replace("’", "'")
    t = re.sub(r"[^\w\s']", " ", t).replace("'", "")
    return t.split()
def load_stem16k(slug, name="lead_vocals"):
    import soundfile as sf, soxr
    x, sr = sf.read(stem_path(slug, name), dtype="float32")
    m = x.mean(1) if x.ndim > 1 else x
    return soxr.resample(m, sr, 16000, quality="HQ").astype(np.float32)
