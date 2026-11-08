import sys, json, time, subprocess, numpy as np, onnxruntime as ort
FF = r"C:\Users\OpenSrcerer\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
D = sys.argv[1]
def load16k(path):
    raw = subprocess.run([FF,"-v","error","-i",path,"-ac","1","-ar","16000","-f","f32le","-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)
def hz_to_mel(f):  # slaney
    f = np.asanyarray(f, float); m = f/(200/3); lin = 1000/(200/3); logstep = np.log(6.4)/27
    return np.where(f>=1000, lin + np.log(np.maximum(f,1e-10)/1000)/logstep, m)
def mel_to_hz(m):
    m = np.asanyarray(m, float); lin = 1000/(200/3); logstep = np.log(6.4)/27
    return np.where(m>=lin, 1000*np.exp(logstep*(m-lin)), (200/3)*m)
def mel_fb(sr=16000, n_fft=512, n_mels=96, fmin=0, fmax=8000):
    fft_f = np.linspace(0, sr/2, n_fft//2+1)
    mel_f = mel_to_hz(np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_mels+2))
    fdiff = np.diff(mel_f); ramps = mel_f[:,None] - fft_f[None,:]
    w = np.zeros((n_mels, len(fft_f)))
    for i in range(n_mels):
        lo = -ramps[i]/fdiff[i]; hi = ramps[i+2]/fdiff[i+1]
        w[i] = np.maximum(0, np.minimum(lo, hi))
    w *= (2.0/(mel_f[2:n_mels+2]-mel_f[:n_mels]))[:,None]
    return w.astype(np.float32)
def logmel(y):
    n_fft, hop = 512, 256
    win = (0.5 - 0.5*np.cos(2*np.pi*np.arange(n_fft)/n_fft)).astype(np.float32)
    nfr = 1 + (len(y)-n_fft)//hop
    idx = np.arange(n_fft)[None,:] + hop*np.arange(nfr)[:,None]
    S = np.abs(np.fft.rfft(y[idx]*win, axis=1))**2
    M = S @ mel_fb().T
    return np.log10(1 + 10000*M).astype(np.float32)
def patches(X, size, hop):
    n = 1 + max(0,(len(X)-size))//hop
    return np.stack([X[i*hop:i*hop+size] for i in range(n)])
so = ort.SessionOptions(); so.intra_op_num_threads = 8
S = lambda f: ort.InferenceSession(f"{D}/{f}.onnx", so, providers=["CPUExecutionProvider"])
mus, emo, deam, eff, mt = S("msd-musicnn-1"), S("emomusic-msd-musicnn-2"), S("deam-msd-musicnn-2"), S("discogs-effnet-bsdynamic-1"), S("mtg_jamendo_moodtheme-discogs-effnet-1")
classes = json.load(open(f"{D}/mtg_jamendo_moodtheme-discogs-effnet-1.json"))["classes"]
for path in sys.argv[2:]:
    t0=time.time(); y = load16k(path); t1=time.time(); X = logmel(y); t2=time.time()
    P = patches(X,187,93); E = mus.run(["embeddings"], {"melspectrogram": P})[0]
    va = emo.run(None, {"embeddings": E})[0]; va2 = deam.run(None, {"model/Placeholder:0": E})[0]
    P2 = patches(X,128,62); E2 = eff.run(["embeddings"], {"melspectrogram": P2})[0]
    tags = mt.run(None, {"embeddings": E2})[0]; t3=time.time()
    m = tags.mean(0); top = np.argsort(-m)[:8]
    print(path.split("\\")[-1], f"dur={len(y)/16000:.0f}s decode={t1-t0:.2f}s mel={t2-t1:.2f}s models={t3-t2:.2f}s",
          f"musicnn patches={len(P)} (hop {93*256/16000:.2f}s) effnet patches={len(P2)} (hop {62*256/16000:.2f}s)")
    print("  emomusic valence/arousal mean", va.mean(0).round(2), "min", va.min(0).round(2), "max", va.max(0).round(2))
    print("  deam valence/arousal mean", va2.mean(0).round(2))
    print("  top moodtheme:", [(classes[i], round(float(m[i]),3)) for i in top])
    # arousal curve coarse (per ~30 s)
    k = max(1,len(va)//8); print("  arousal curve (emomusic, ~8 bins):", [round(float(va[i:i+k,1].mean()),2) for i in range(0,len(va),k)])
