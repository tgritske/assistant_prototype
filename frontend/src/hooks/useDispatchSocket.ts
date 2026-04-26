import { useCallback, useEffect, useRef, useState } from "react";
import { ServerMessageSchema, type ServerMessage } from "../types/dispatch";
import type { Speaker } from "../types/dispatch";

type Status = "idle" | "connecting" | "open" | "closed" | "error";

export interface UseDispatchSocketOptions {
  url?: string;
  onMessage?: (msg: ServerMessage) => void;
}

export function useDispatchSocket(opts: UseDispatchSocketOptions = {}) {
  const url =
    opts.url ??
    `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`;
  const [status, setStatus] = useState<Status>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<number>(0);
  const audioSeqRef = useRef<number>(0);
  const onMessageRef = useRef(opts.onMessage);
  onMessageRef.current = opts.onMessage;

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= 1) return;
    setStatus("connecting");
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("open");
      retryRef.current = 0;
    };
    ws.onclose = () => {
      setStatus("closed");
      // light backoff: 1s, 2s, 4s, capped at 4s
      const delay = Math.min(1000 * 2 ** retryRef.current, 4000);
      retryRef.current += 1;
      setTimeout(() => connect(), delay);
    };
    ws.onerror = () => {
      setStatus("error");
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return; // binary from server not expected
      let parsed: unknown;
      try {
        parsed = JSON.parse(ev.data);
      } catch {
        return;
      }
      const result = ServerMessageSchema.safeParse(parsed);
      if (!result.success) {
        console.warn("WS schema mismatch", result.error, parsed);
        return;
      }
      onMessageRef.current?.(result.data);
    };
  }, [url]);

  useEffect(() => {
    // Delay the connect so React StrictMode's synchronous
    // mount→unmount→remount doesn't open then tear down a real socket.
    // The cleanup cancels the timer on the throwaway mount.
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (!cancelled) connect();
    }, 50);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      const ws = wsRef.current;
      wsRef.current = null;
      // Prevent the auto-reconnect handler from firing on intentional unmount
      if (ws) {
        ws.onclose = null;
        ws.onerror = null;
        if (ws.readyState <= 1) ws.close();
      }
    };
  }, [connect]);

  const send = useCallback((payload: object) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== 1) return false;
    ws.send(JSON.stringify(payload));
    return true;
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== 1) return false;
    ws.send(data);
    return true;
  }, []);

  const sendAudioChunk = useCallback((speaker: Speaker, data: ArrayBuffer) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== 1) return false;
    ws.send(JSON.stringify({
      type: "audio_chunk_meta",
      speaker,
      sample_rate: 16000,
      seq: audioSeqRef.current++,
    }));
    ws.send(data);
    return true;
  }, []);

  return { status, send, sendBinary, sendAudioChunk };
}
