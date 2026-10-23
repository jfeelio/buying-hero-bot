// Word-timestamped transcription on Microsoft's signed ONNX Runtime (transformers.js).
// Fallback for when Windows Smart App Control blocks faster-whisper's native libraries
// (ctranslate2 / PyAV) -- it did on 2026-10-23. Same words.json format as transcribe.py.
//   node transcribe.js <audio.f32le (16 kHz mono float32)> <words.json> [model]
const fs = require("fs");

(async () => {
  const [, , audioPath, outPath, modelArg] = process.argv;
  const model = modelArg || "onnx-community/whisper-large-v3-turbo_timestamped";
  const { pipeline } = await import("@huggingface/transformers");
  const buf = fs.readFileSync(audioPath);
  const audio = new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4);
  const t0 = Date.now();
  const asr = await pipeline("automatic-speech-recognition", model, { dtype: { encoder_model: "fp32", decoder_model_merged: "q8" } });
  const res = await asr(audio, { return_timestamps: "word", chunk_length_s: 30, stride_length_s: 5, language: "en", task: "transcribe" });
  const words = (res.chunks || []).map((c) => ({
    w: c.text.trim(),
    s: Math.round(c.timestamp[0] * 1000) / 1000,
    e: Math.round((c.timestamp[1] ?? c.timestamp[0]) * 1000) / 1000,
  })).filter((w) => w.w);
  fs.writeFileSync(outPath, JSON.stringify({ language: "en", model, words }, null, 1));
  console.log(`${words.length} words in ${((Date.now() - t0) / 1000).toFixed(0)}s with ${model}`);
})().catch((e) => { console.error(e); process.exit(1); });
