import { useCallback, useEffect, useRef, useState } from "react";

const TARGET_SR = 16_000;
// Send 0.5s chunks so the socket stays responsive while the backend decides
// how much audio context to batch for Whisper.
const SEND_EVERY_SEC = 0.5;
// RMS below this level is treated as silence and not sent to the backend.
// Prevents Whisper from hallucinating on quiet periods / end of speech.
// ~0.005 ≈ -46 dBFS — well below any real speech, above digital silence.
const SILENCE_RMS_THRESHOLD = 0.005;

function computeRMS(buf: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
  return Math.sqrt(sum / buf.length);
}

function downsample(buf: Float32Array, fromSR: number): Float32Array {
  if (fromSR === TARGET_SR) return buf;
  const ratio = fromSR / TARGET_SR;
  const len = Math.floor(buf.length / ratio);
  const out = new Float32Array(len);
  for (let i = 0; i < len; i++) {
    const idx = i * ratio;
    const lo = Math.floor(idx);
    const hi = Math.min(lo + 1, buf.length - 1);
    out[i] = buf[lo] + (buf[hi] - buf[lo]) * (idx - lo);
  }
  return out;
}

function toInt16(buf: Float32Array): ArrayBuffer {
  const out = new Int16Array(buf.length);
  for (let i = 0; i < buf.length; i++) {
    const s = Math.max(-1, Math.min(1, buf[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out.buffer;
}

function mergeChunks(chunks: Float32Array[], totalLen: number): Float32Array {
  const merged = new Float32Array(totalLen);
  let offset = 0;
  for (const c of chunks) {
    merged.set(c, offset);
    offset += c.length;
  }
  return merged;
}

export function useAudioCapture(sendBinary: (data: ArrayBuffer) => boolean) {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ctxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const accRef = useRef<Float32Array[]>([]);
  const accLenRef = useRef(0);
  // Keep sendBinary stable across renders without re-registering the processor
  const sendRef = useRef(sendBinary);
  sendRef.current = sendBinary;

  const stop = useCallback(() => {
    processorRef.current?.disconnect();
    processorRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    ctxRef.current?.close().catch(() => {});
    ctxRef.current = null;
    accRef.current = [];
    accLenRef.current = 0;
    setIsRecording(false);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, sampleRate: { ideal: TARGET_SR } },
        video: false,
      });
      streamRef.current = stream;

      const ctx = new AudioContext();
      ctxRef.current = ctx;

      const samplesNeeded = Math.floor(ctx.sampleRate * SEND_EVERY_SEC);
      const source = ctx.createMediaStreamSource(stream);
      // ScriptProcessor is deprecated but universally supported in browsers
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        const data = e.inputBuffer.getChannelData(0);
        accRef.current.push(new Float32Array(data));
        accLenRef.current += data.length;

        if (accLenRef.current >= samplesNeeded) {
          const merged = mergeChunks(accRef.current, accLenRef.current);
          accRef.current = [];
          accLenRef.current = 0;
          // Skip silent chunks — Whisper hallucinates language/text on silence
          if (computeRMS(merged) >= SILENCE_RMS_THRESHOLD) {
            const downsampled = downsample(merged, ctx.sampleRate);
            sendRef.current(toInt16(downsampled));
          }
        }
      };

      // Mute gain node to avoid mic feedback while keeping the audio graph alive
      const mute = ctx.createGain();
      mute.gain.value = 0;
      source.connect(processor);
      processor.connect(mute);
      mute.connect(ctx.destination);

      setIsRecording(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    }
  }, []);

  // Flush any remaining audio when recording stops
  const flush = useCallback(() => {
    if (accRef.current.length === 0 || !ctxRef.current) return;
    const merged = mergeChunks(accRef.current, accLenRef.current);
    accRef.current = [];
    accLenRef.current = 0;
    if (merged.length > TARGET_SR * 0.2) {
      // only send if there's at least 200ms of audio worth sending
      const downsampled = downsample(merged, ctxRef.current.sampleRate);
      sendRef.current(toInt16(downsampled));
    }
  }, []);

  useEffect(() => () => stop(), [stop]);

  return { isRecording, error, start, stop, flush };
}
