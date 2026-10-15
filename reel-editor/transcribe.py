"""Transcribe a reel with word-level timestamps -> words.json"""
import json, shutil, subprocess, sys
import numpy as np

def _add_cuda_dlls():
    # pip-installed nvidia-cublas/cudnn wheels ship DLLs that Windows won't find on its own
    try:
        import os, nvidia
        for root in nvidia.__path__:
            for sub in ("cublas", "cudnn", "cuda_nvrtc"):
                d = os.path.join(root, sub, "bin")
                if os.path.isdir(d):
                    os.add_dll_directory(d)
                    os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
    except ImportError:
        pass

_add_cuda_dlls()
from faster_whisper import WhisperModel

def load_model():
    try:
        return WhisperModel("large-v3", device="cuda", compute_type="float16")
    except Exception as e:
        print(f"GPU unavailable ({e}); falling back to CPU", file=sys.stderr)
        return WhisperModel("medium", device="cpu", compute_type="int8")

def load_audio(video):
    # decode via ffmpeg ourselves (faster-whisper's PyAV path is version-fragile)
    ff = shutil.which("ffmpeg") or "ffmpeg"
    raw = subprocess.run([ff, "-v", "error", "-i", video, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)

def main(video, out):
    model = load_model()
    segments, info = model.transcribe(load_audio(video), word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words:
            words.append({"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)})
    json.dump({"language": info.language, "words": words}, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(words)} words, lang={info.language}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
