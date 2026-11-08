r"""Run the ffmpeg 9.0.2 `whisper` filter (whisper.cpp + ggml Vulkan) on a vocals stem.

  python whisper_vulkan.py --slug jeremy --model ggml-large-v3-turbo-q8_0.bin [--lang en] [--no-gpu] [--seconds 30]

cwd = %LOCALAPPDATA%\mvh\models\ggml and relative model names (no drive-letter colons in the filtergraph).
The filter writes its JSON to a *relative* destination inside that folder; we move it to
tests/.cache/real/<slug>/whisper_vulkan/<tag>.raw.json, and also write <tag>.words.json (normalised) + timings in index.json.
Never prints lyric text.
"""
import argparse, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mvh_locks import Slot

ROOT = Path(__file__).resolve().parents[3]
GGML = Path(os.environ["LOCALAPPDATA"]) / "mvh" / "models" / "ggml"
FFMPEG = os.environ.get("MVH_FFMPEG") or r"C:\Users\OpenSrcerer\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"


def parse_json_stream(txt):
    """ffmpeg whisper json output: either one JSON doc or one object per line (max_len=1)."""
    txt = txt.strip()
    try:
        d = json.loads(txt)
        return d if isinstance(d, list) else [d]
    except json.JSONDecodeError:
        out = []
        for ln in txt.splitlines():
            ln = ln.strip().rstrip(",")
            if ln.startswith("{"):
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--model", default="ggml-large-v3-turbo-q8_0.bin")
    ap.add_argument("--vad", default="ggml-silero-v5.1.2.bin")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--queue", default="20")
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--no-vad", action="store_true")
    ap.add_argument("--seconds", type=float, default=0)
    ap.add_argument("--input", default="")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()

    outdir = ROOT / "tests" / ".cache" / "real" / a.slug / "whisper_vulkan"
    outdir.mkdir(parents=True, exist_ok=True)
    src = Path(a.input) if a.input else ROOT / "tests" / ".cache" / "real" / a.slug / "sep" / "vocals.wav"
    tag = a.tag or (Path(a.model).stem + ("_cpu" if a.no_gpu else "") + ("_novad" if a.no_vad else "") + (f"_{int(a.seconds)}s" if a.seconds else ""))
    rel_dest = f"_mvh_{a.slug}_{tag}.json"
    opts = [f"model={a.model}", f"language={a.lang}", f"queue={a.queue}", f"use_gpu={0 if a.no_gpu else 1}", "max_len=1", "format=json", f"destination={rel_dest}"]
    if not a.no_vad:
        opts.append(f"vad_model={a.vad}")
    af = "whisper=" + ":".join(opts)
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "info"] + (["-t", str(a.seconds)] if a.seconds else []) + ["-i", str(src), "-af", af, "-f", "null", "-"]
    (GGML / rel_dest).unlink(missing_ok=True)
    with Slot(f"env-sep:whisper:{a.slug}:{tag}", gpu=not a.no_gpu) as slot:
        t0 = time.time()
        r = subprocess.run(cmd, cwd=str(GGML), capture_output=True, text=True, encoding="utf-8", errors="replace")
        wall = time.time() - t0
    log = r.stderr
    dev = [l.strip() for l in log.splitlines() if "ggml_vulkan" in l or "Vulkan" in l][:3]
    if r.returncode or not (GGML / rel_dest).exists():
        (outdir / f"{tag}.ffmpeg.log").write_text(log[-6000:], encoding="utf-8")
        print("FAILED rc", r.returncode, log[-600:].replace("\n", " | ")[:600])
        sys.exit(1)
    raw = (GGML / rel_dest).read_text(encoding="utf-8")
    shutil.move(str(GGML / rel_dest), str(outdir / f"{tag}.raw.json"))
    items = parse_json_stream(raw)
    # normalise: {start,end,text} in ms (whisper.cpp ffmpeg filter) -> seconds
    words = []
    for it in items:
        s = it.get("start", it.get("from")); e = it.get("end", it.get("to"))
        tx = it.get("text", "")
        if s is None or e is None:
            continue
        words.append({"t0": round(float(s) / 1000.0, 3), "t1": round(float(e) / 1000.0, 3), "text": tx.strip()})
    (outdir / f"{tag}.words.json").write_text(json.dumps({"tag": tag, "words": words}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    idxp = outdir / "index.json"
    idx = json.loads(idxp.read_text(encoding="utf-8")) if idxp.exists() else {"runs": {}}
    nonlex = sum(1 for w in words if re.fullmatch(r"[\[\(].*[\]\)]", w["text"] or ""))
    idx["runs"][tag] = {
        "model": a.model, "vad": None if a.no_vad else a.vad, "gpu": not a.no_gpu, "language": a.lang, "queue": a.queue,
        "input": str(src.name), "seconds_limit": a.seconds or None, "wall_s": round(wall, 2), "lock_wait_s": round(slot.waited, 1),
        "other_lock_owners": slot.others, "n_items": len(items), "n_words": len(words), "n_bracket_tags": nonlex,
        "first_word_t": words[0]["t0"] if words else None, "last_word_t": words[-1]["t1"] if words else None,
        "ffmpeg_device_lines": dev, "ffmpeg_cmd_filter": af,
    }
    idxp.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{a.slug} {tag}: wall={wall:.1f}s words={len(words)} tags={nonlex} dev={dev[:1]}")


if __name__ == "__main__":
    main()
