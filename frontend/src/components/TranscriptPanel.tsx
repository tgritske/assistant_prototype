import { useEffect, useMemo, useRef } from "react";
import { motion } from "framer-motion";
import { Languages, Mic, MicOff } from "lucide-react";
import type { DialogueTurn } from "../types/dispatch";
import type { AudioInputDevice } from "../hooks/useAudioDevices";

interface Props {
  transcript: string;
  interimText: string;
  originalTranscript: string;
  originalInterimText: string;
  dialogueTurns: DialogueTurn[];
  highlights: string[];
  inCall: boolean;
  callerLanguage: string | null;
  callerLanguageName: string | null;
  playbackAudioUrl: string | null;
  workerMicActive?: boolean;
  onToggleWorkerMic?: () => void;
  audioDevices?: AudioInputDevice[];
  workerDeviceId?: string;
  onWorkerDeviceChange?: (deviceId: string) => void;
}

export function TranscriptPanel({
  transcript,
  interimText,
  originalTranscript,
  originalInterimText,
  dialogueTurns,
  highlights,
  inCall,
  callerLanguage,
  callerLanguageName,
  playbackAudioUrl,
  workerMicActive = false,
  onToggleWorkerMic,
  audioDevices = [],
  workerDeviceId = "",
  onWorkerDeviceChange,
}: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [transcript, interimText, dialogueTurns.length]);

  useEffect(() => {
    if (playbackAudioUrl && audioRef.current) {
      audioRef.current.src = playbackAudioUrl;
      audioRef.current.play().catch(() => {});
    }
  }, [playbackAudioUrl]);

  const highlighted = useMemo(
    () => highlightTranscript(transcript, highlights),
    [transcript, highlights]
  );
  const highlightedInterim = useMemo(
    () => highlightTranscript(interimText, highlights),
    [interimText, highlights]
  );
  const originalHighlighted = useMemo(
    () => highlightTranscript(originalTranscript, highlights),
    [originalTranscript, highlights]
  );
  const originalHighlightedInterim = useMemo(
    () => highlightTranscript(originalInterimText, highlights),
    [originalInterimText, highlights]
  );

  const nonEnglish = callerLanguage && !callerLanguage.toLowerCase().startsWith("en");
  const hasDialogue = dialogueTurns.length > 0;

  return (
    <section className="flex flex-col h-full bg-[var(--color-bg-panel)] border-r border-[var(--color-border)] min-h-0">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] uppercase text-[var(--color-text-muted)]">
          <Mic size={13} />
          Dispatcher Feed
        </div>
        <div className="flex items-center gap-2">
          {onWorkerDeviceChange && inCall && audioDevices.length > 0 && (
            <select
              value={workerDeviceId}
              onChange={(e) => onWorkerDeviceChange(e.target.value)}
              disabled={workerMicActive}
              className="max-w-[150px] rounded-md px-2 py-1 text-[10px] bg-[var(--color-bg-elevated)] border border-[var(--color-border)] text-[var(--color-text-muted)] outline-none focus:border-[var(--color-accent)] disabled:opacity-50"
              title="Worker audio input"
            >
              <option value="">Default worker input</option>
              {audioDevices.map((device) => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label}
                </option>
              ))}
            </select>
          )}
          {onToggleWorkerMic && inCall && (
            <button
              onClick={onToggleWorkerMic}
              className={[
                "inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.1em] uppercase px-2 py-1 rounded-md border transition-colors",
                workerMicActive
                  ? "border-red-700 bg-red-950/40 text-red-300"
                  : "border-[var(--color-border-strong)] bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] hover:border-[var(--color-accent)]",
              ].join(" ")}
              title={workerMicActive ? "Stop worker microphone" : "Start worker microphone"}
            >
              {workerMicActive ? (
                <MicOff size={12} className="animate-pulse" />
              ) : (
                <Mic size={12} />
              )}
              Worker Mic
            </button>
          )}
          {callerLanguageName && (
            <div
              className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.1em] uppercase px-2 py-0.5 rounded-full border"
              style={{
                color: nonEnglish ? "#fbbf24" : "var(--color-text-muted)",
                borderColor: nonEnglish ? "rgba(245,158,11,0.4)" : "var(--color-border-strong)",
                background: nonEnglish ? "rgba(245,158,11,0.08)" : "transparent",
              }}
            >
              <Languages size={11} />
              {callerLanguageName}
            </div>
          )}
        </div>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-5 py-4 text-[15px] leading-relaxed"
      >
        {!hasDialogue && !transcript && !interimText && !originalTranscript && !originalInterimText ? (
          <div className="h-full flex items-center justify-center text-center">
            <div className="text-[var(--color-text-dim)]">
              <div className="text-sm mb-1">
                {inCall ? "Listening…" : "No call in progress"}
              </div>
              <div className="text-xs">
                {inCall
                  ? "Transcript will appear as the caller speaks."
                  : "Start a demo scenario or connect a live microphone."}
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {hasDialogue ? (
              <DialogueTimeline turns={dialogueTurns} highlights={highlights} />
            ) : (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="rounded-xl border border-[var(--color-ai-border)] bg-[var(--color-ai-bg)] px-4 py-3"
              >
                <div className="text-[10px] uppercase tracking-[0.12em] text-blue-300 font-semibold mb-2">
                  English For Dispatcher
                </div>
                <div className="whitespace-pre-wrap text-[var(--color-text)]">
                  {highlighted}
                  {interimText && (
                    <span className="text-blue-200/80 italic">
                      {transcript ? " " : ""}
                      {highlightedInterim}
                    </span>
                  )}
                </div>
              </motion.div>
            )}

            {nonEnglish && !hasDialogue && (
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-4 py-3">
                <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-dim)] font-semibold mb-2">
                  Original Caller Wording
                </div>
                <div className="whitespace-pre-wrap text-[13px] text-[var(--color-text-muted)]">
                  {originalHighlighted}
                  {originalInterimText && (
                    <span className="italic opacity-80">
                      {originalTranscript ? " " : ""}
                      {originalHighlightedInterim}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <audio ref={audioRef} controls className="w-full border-t border-[var(--color-border)] bg-[var(--color-bg-elevated)]" />
    </section>
  );
}

function DialogueTimeline({
  turns,
  highlights,
}: {
  turns: DialogueTurn[];
  highlights: string[];
}) {
  return (
    <div className="space-y-2">
      {turns.map((turn) => {
        const isWorker = turn.speaker === "worker";
        return (
          <motion.div
            key={turn.id}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className={[
              "flex",
              isWorker ? "justify-end" : "justify-start",
            ].join(" ")}
          >
            <div
              className={[
                "max-w-[86%] rounded-lg border px-3 py-2",
                isWorker
                  ? "border-emerald-700/40 bg-emerald-950/20"
                  : "border-[var(--color-ai-border)] bg-[var(--color-ai-bg)]",
                !turn.is_final ? "opacity-75 italic" : "",
              ].join(" ")}
            >
              <div
                className={[
                  "text-[10px] uppercase tracking-[0.12em] font-semibold mb-1",
                  isWorker ? "text-emerald-300" : "text-blue-300",
                ].join(" ")}
              >
                {isWorker ? "Worker" : "Caller"}
              </div>
              <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-[var(--color-text)]">
                {highlightTranscript(turn.text, highlights)}
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

function highlightTranscript(text: string, keywords: string[]): React.ReactNode {
  if (!keywords.length || !text) return text;
  const unique = Array.from(
    new Set(keywords.map((k) => k.trim()).filter(Boolean))
  ).sort((a, b) => b.length - a.length);
  if (!unique.length) return text;
  const pattern = new RegExp(
    "(" + unique.map(escapeRegex).join("|") + ")",
    "gi"
  );
  const parts = text.split(pattern);
  return parts.map((p, i) =>
    pattern.test(p) && i % 2 === 1 ? (
      <mark key={i} className="kw-highlight">
        {p}
      </mark>
    ) : (
      <span key={i}>{p}</span>
    )
  );
}

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
