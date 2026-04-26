import { useEffect, useMemo, useRef } from "react";
import { motion } from "framer-motion";
import { Headphones, Languages, Mic, MicOff } from "lucide-react";
import type { DialogueTurn } from "../types/dispatch";
import { DialogueTimeline } from "./DialogueTimeline";

interface Props {
  transcript: string;
  interimText: string;
  originalTranscript: string;
  originalInterimText: string;
  highlights: string[];
  inCall: boolean;
  callerLanguage: string | null;
  callerLanguageName: string | null;
  playbackAudioUrl: string | null;
  dialogueTurns: DialogueTurn[];
  callerInterimText: string;
  workerInterimText: string;
  workerMicActive: boolean;
  onToggleWorkerMic: () => void;
}

export function TranscriptPanel({
  transcript,
  interimText,
  originalTranscript,
  originalInterimText,
  highlights,
  inCall,
  callerLanguage,
  callerLanguageName,
  playbackAudioUrl,
  dialogueTurns,
  callerInterimText,
  workerInterimText,
  workerMicActive,
  onToggleWorkerMic,
}: Props) {
  const hasDialogue = dialogueTurns.length > 0 || !!workerInterimText || !!callerInterimText;
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [transcript, interimText]);

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

  return (
    <section className="flex flex-col h-full bg-[var(--color-bg-panel)] border-r border-[var(--color-border)] min-h-0">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] uppercase text-[var(--color-text-muted)]">
          <Mic size={13} />
          Dispatcher Feed
        </div>
        <div className="flex items-center gap-2">
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
          <button
            type="button"
            onClick={onToggleWorkerMic}
            className={`inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.1em] uppercase px-2 py-1 rounded-md border transition-colors ${
              workerMicActive
                ? "bg-emerald-900/40 border-emerald-700 text-emerald-200"
                : "border-[var(--color-border-strong)] text-[var(--color-text-muted)] hover:bg-[var(--color-bg-elevated)]"
            }`}
            title={workerMicActive ? "Stop worker mic" : "Start worker mic"}
          >
            {workerMicActive ? <MicOff size={11} /> : <Headphones size={11} />}
            Worker Mic
          </button>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-5 py-4 text-[15px] leading-relaxed"
      >
        {!transcript && !interimText && !originalTranscript && !originalInterimText && !hasDialogue ? (
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
            {hasDialogue && (
              <DialogueTimeline
                turns={dialogueTurns}
                callerInterim={callerInterimText}
                workerInterim={workerInterimText}
                highlights={highlights}
              />
            )}
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

            {nonEnglish && (
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
