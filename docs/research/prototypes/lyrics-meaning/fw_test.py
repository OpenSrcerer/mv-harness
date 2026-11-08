import sys, time, difflib, re, os, subprocess
import numpy as np, mutagen
from faster_whisper import WhisperModel
FF = r"C:\Users\OpenSrcerer\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
def load16k(path): return np.frombuffer(subprocess.run([FF,"-v","error","-i",path,"-ac","1","-ar","16000","-f","f32le","-"],capture_output=True,check=True).stdout,dtype=np.float32).copy()
model_name = sys.argv[1]
t=time.time(); m = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=8, download_root="models_fw"); print("load s", round(time.time()-t,1))
for p in sys.argv[2:]:
    t=time.time()
    segs, info = m.transcribe(load16k(p), word_timestamps=True, vad_filter=os.environ.get("VAD")=="1", condition_on_previous_text=False,
                              beam_size=5, temperature=[0.0,0.2,0.4,0.6], compression_ratio_threshold=2.4,
                              log_prob_threshold=-1.0, no_speech_threshold=0.6, hallucination_silence_threshold=2.0)
    segs = list(segs); dt=time.time()-t
    words = [w for s in segs for w in (s.words or [])]
    probs = [w.probability for w in words]
    hyp = " ".join(w.word.strip() for w in words).lower()
    f = mutagen.File(p); ref = " ".join(f.tags["unsyncedlyrics"][0].split()).lower() if f.tags and "unsyncedlyrics" in f.tags else None
    sim = difflib.SequenceMatcher(None, re.sub(r"[^\w ]","",ref).split(), re.sub(r"[^\w ]","",hyp).split()).ratio() if ref else None
    print(os.path.basename(p), f"lang={info.language}({info.language_probability:.2f}) dur={info.duration:.0f}s vad_kept={info.duration_after_vad:.0f}s",
          f"time={dt:.1f}s RTF={dt/info.duration:.3f} segs={len(segs)} words={len(words)}",
          f"mean_p={sum(probs)/max(1,len(probs)):.2f} low_p(<0.4)={sum(1 for x in probs if x<0.4)}",
          f"avg_logprob={[round(s.avg_logprob,2) for s in segs][:6]} no_speech={[round(s.no_speech_prob,2) for s in segs][:6]}",
          f"similarity_to_embedded_lyrics={None if sim is None else round(sim,2)}")
