"""Transcribe a reel with word-level timestamps -> words.json"""
import json, os, subprocess, sys
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
try:
    from faster_whisper import WhisperModel
except ImportError as e:
    # Windows Smart App Control blocks ctranslate2/PyAV's unsigned DLLs ("An Application Control
    # policy has blocked this file", seen 2026-10-23). transcribe.js runs the same Whisper family
    # on Microsoft's signed ONNX Runtime instead (~75 s for a 90 s reel on CPU).
    WhisperModel = None
    _import_error = e

def load_model():
    try:
        return WhisperModel("large-v3", device="cuda", compute_type="float16")
    except Exception as e:
        print(f"GPU unavailable ({e}); falling back to CPU", file=sys.stderr)
        return WhisperModel("medium", device="cpu", compute_type="int8")

def load_audio(video):
    # decode via ffmpeg ourselves (faster-whisper's PyAV path is version-fragile)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from render import ffmpeg_bin   # finds the WinGet install when ffmpeg isn't on PATH
    ff = ffmpeg_bin()
    raw = subprocess.run([ff, "-v", "error", "-i", video, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)

def transcribe_onnx(video, out):
    here = os.path.dirname(os.path.abspath(__file__))
    pcm = os.path.splitext(out)[0] + ".f32le"
    open(pcm, "wb").write(load_audio(video).tobytes())
    try:
        subprocess.run(["node", os.path.join(here, "transcribe.js"), pcm, out], check=True, cwd=here)
    finally:
        os.remove(pcm)


def main(video, out):
    if WhisperModel is None:
        print(f"faster-whisper unavailable ({_import_error}); using transcribe.js (ONNX Runtime)", file=sys.stderr)
        return transcribe_onnx(video, out)
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
