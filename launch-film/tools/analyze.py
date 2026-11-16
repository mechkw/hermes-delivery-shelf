import librosa, numpy as np, json, sys
y, sr = librosa.load(sys.argv[1], sr=22050, mono=True)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time')
onset_env = librosa.onset.onset_strength(y=y, sr=sr)
onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units='time')
rms = librosa.feature.rms(y=y, hop_length=512)[0]
times = librosa.times_like(rms, sr=sr, hop_length=512)
# low band energy for kicks
S = np.abs(librosa.stft(y, hop_length=512))
freqs = librosa.fft_frequencies(sr=sr)
low = S[freqs<150].sum(0); high=S[freqs>4000].sum(0)
print("tempo", tempo, "nbeats", len(beats))
print("beats first 16", np.round(beats[:16],3))
# per-second rms summary
for s in range(0,80,2):
    m=(times>=s)&(times<s+2)
    print(s, round(float(rms[m].mean()),3), round(float(low[m].mean()),1), round(float(high[m].mean()),1))
fps=30
n=int(80*fps)
def resample(a):
    return np.interp(np.arange(n)/fps, times, a).tolist()
nm=lambda a:(a/np.percentile(a,99)).clip(0,1.5)
json.dump({"tempo":float(np.atleast_1d(tempo)[0]),"beats":beats.tolist(),"onsets":onsets.tolist(),
  "rms":resample(nm(rms)),"low":resample(nm(low)),"high":resample(nm(high))}, open("audio.json","w"))
