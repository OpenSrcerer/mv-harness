import sys, subprocess, collections, numpy as np
from faster_whisper import WhisperModel
FF = r"C:\Users\OpenSrcerer\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
a = np.frombuffer(subprocess.run([FF,"-v","error","-i",sys.argv[2],"-ac","1","-ar","16000","-f","f32le","-"],capture_output=True,check=True).stdout,dtype=np.float32).copy()
m = WhisperModel(sys.argv[1], device="cpu", compute_type="int8", cpu_threads=8, download_root="models_fw")
segs, info = m.transcribe(a, word_timestamps=True, condition_on_previous_text=False, beam_size=5)
for s in segs:
    w = [x.word.strip().lower() for x in s.words]
    grams = collections.Counter(tuple(w[i:i+3]) for i in range(len(w)-2))
    top = grams.most_common(1)[0][1] if grams else 0
    dur = [x.end-x.start for x in s.words]
    print(f"seg {s.start:6.1f}-{s.end:6.1f} words={len(w)} unique_ratio={len(set(w))/max(1,len(w)):.2f} top_trigram_repeats={top} cr={s.compression_ratio:.1f} avg_logprob={s.avg_logprob:.2f} no_speech={s.no_speech_prob:.2f} words/sec={len(w)/max(0.1,s.end-s.start):.1f} zero-dur-words={sum(1 for d in dur if d<0.02)}")
