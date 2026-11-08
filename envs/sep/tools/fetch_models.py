"""Fetch + SHA-pin the separator models. Run with envs/sep/.venv-cpu python.
Writes envs/sep/models.fragment.json (separator entries). Whisper/ggml entries are merged by fetch_ggml.py."""
import hashlib, json, os, sys, time
from pathlib import Path
import requests

MODEL_DIR = Path(os.environ["LOCALAPPDATA"]) / "mvh" / "models" / "separator"
FRAG = Path(__file__).resolve().parents[1] / "models.fragment.json"
MIRROR = "https://github.com/nomadkaraoke/python-audio-separator/releases/download/model-configs"
UPSTREAM = "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models"

MODELS = [
    dict(id="sep.bs-roformer-sw-6stem", ckpt="BS-Roformer-SW.ckpt", licence="CC-BY-NC-SA-4.0 per the survey (unblend model card for bs_roformer_sw); personal non-commercial use", used_by=["separate_hq"]),
    dict(id="sep.mel-roformer-vocals-kimberley", ckpt="vocals_mel_band_roformer.ckpt", licence="not verified in W0 (upstream card not read); treat as personal non-commercial use", used_by=["separate_hq"]),
    dict(id="sep.mel-roformer-karaoke-aufr33-viperx", ckpt="mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt", licence="not verified in W0 (aufr33 + viperx via UVR model zoo); treat as personal non-commercial use", used_by=["separate_hq"]),
    dict(id="sep.mdx23c-drumsep", ckpt="MDX23C-DrumSep-aufr33-jarredou.ckpt", licence="unclear (survey: aufr33 + jarredou); treat as personal non-commercial use", used_by=["separate_hq", "drums"]),
]

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def main():
    from audio_separator.separator import Separator
    sep = Separator(model_file_dir=str(MODEL_DIR), info_only=True)
    entries = []
    for m in MODELS:
        t = time.time()
        name, mtype, friendly, path, yaml_cfg = sep.download_model_files(m["ckpt"])
        files = []
        for fn in [m["ckpt"]] + ([yaml_cfg] if yaml_cfg else []):
            p = MODEL_DIR / fn
            url = f"{MIRROR}/{fn}"
            if requests.head(url, allow_redirects=True, timeout=60).status_code != 200:
                url = f"{UPSTREAM}/{fn}" if fn == m["ckpt"] else f"{UPSTREAM}/mdx_model_data/mdx_c_configs/{fn}"
            files.append(dict(path=f"separator/{fn}", url=url, revision=url.split("/download/")[1].split("/")[0],
                              sha256=sha256(p), size=p.stat().st_size))
        entries.append(dict(id=m["id"], envs=["sep-rocm", "sep-cpu"], files=files, licence=m["licence"], used_by=m["used_by"],
                            note=f"audio-separator friendly name: {friendly}; arch {mtype}"))
        print(m["id"], [f["size"] for f in files], f"{time.time()-t:.0f}s", flush=True)
    # merge into fragment
    frag = json.loads(FRAG.read_text(encoding="utf-8")) if FRAG.exists() else {"models": []}
    keep = [e for e in frag["models"] if not e["id"].startswith("sep.")]
    frag["models"] = entries + keep
    FRAG.write_text(json.dumps(frag, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
