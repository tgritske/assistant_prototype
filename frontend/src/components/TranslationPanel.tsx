import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Languages, Mic, PlayCircle, Send, Wand2 } from "lucide-react";
import type { Suggestion } from "../types/dispatch";
import { cn } from "../lib/utils";
import { useWebSpeechCapture } from "../hooks/useWebSpeechCapture";

interface Props {
  callerLanguage: string | null;
  callerLanguageName: string | null;
  translatedPhrases: { en: string; translated: string }[];
  suggestions: Suggestion[];
  onSpeak: (text: string, language: string, translate?: boolean) => void;
  lastTTSAudio: { language: string; text: string; audio_base64: string } | null;
}

export function TranslationPanel({
  callerLanguage,
  callerLanguageName,
  translatedPhrases,
  suggestions,
  onSpeak,
  lastTTSAudio,
}: Props) {
  const [custom, setCustom] = useState("");
  const [draftInterim, setDraftInterim] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const { isRecording, start, stop } = useWebSpeechCapture((text, isFinal) => {
    if (isFinal) {
      setCustom((prev) => [prev.trim(), text].filter(Boolean).join(" ").trim());
      setDraftInterim("");
      stop();
      return;
    }
    setDraftInterim(text);
  });

  useEffect(() => {
    if (!lastTTSAudio || !audioRef.current) return;
    audioRef.current.src = `data:audio/mpeg;base64,${lastTTSAudio.audio_base64}`;
    audioRef.current.play().catch(() => {});
  }, [lastTTSAudio]);

  const isNonEnglish = callerLanguage && !callerLanguage.toLowerCase().startsWith("en");
  const autoPrompts = useMemo(
    () =>
      suggestions.slice(0, 4).map((suggestion) => ({
        id: suggestion.id,
        en: suggestion.question,
        translated: translatedPhrases.find((phrase) => phrase.en === suggestion.question)?.translated ?? null,
        type: suggestion.suggestion_type,
        category: suggestion.category,
      })),
    [suggestions, translatedPhrases]
  );

  if (!isNonEnglish) return null;

  const submit = () => {
    const text = custom.trim();
    if (!text || !callerLanguage) return;
    onSpeak(text, callerLanguage, true);
    setCustom("");
    setDraftInterim("");
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-[var(--color-bg-panel)] border-t border-[var(--color-border)]"
    >
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] uppercase text-[var(--color-text-muted)]">
          <Languages size={13} />
          Caller Communication
        </div>
        <div className="text-[10px] text-[var(--color-text-dim)]">
          English first · Plays in {callerLanguageName}
        </div>
      </div>

      <div className="p-3 space-y-3 max-h-[360px] overflow-y-auto">
        <div className="rounded-xl border border-[var(--color-ai-border)] bg-[var(--color-ai-bg)] px-3 py-3">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-blue-300 font-semibold mb-2">
            <Wand2 size={12} />
            Auto-Generated Questions & Instructions
          </div>
          <div className="space-y-2">
            {autoPrompts.length === 0 ? (
              <div className="text-[12px] text-[var(--color-text-dim)] italic">
                Follow-up prompts will appear here as the call develops.
              </div>
            ) : (
              autoPrompts.map((prompt) => (
                <button
                  key={prompt.id}
                  onClick={() => callerLanguage && onSpeak(prompt.en, callerLanguage, true)}
                  className={cn(
                    "w-full text-left rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-2 hover:border-[var(--color-ai-border)] transition-colors"
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[12px] font-medium text-[var(--color-text)] leading-snug">
                        {prompt.en}
                      </div>
                      {prompt.translated && (
                        <div className="text-[11px] text-[var(--color-text-dim)] mt-1 leading-snug">
                          Plays as: {prompt.translated}
                        </div>
                      )}
                    </div>
                    <PlayCircle size={18} className="text-blue-300 shrink-0 mt-0.5" />
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-muted)] font-semibold mb-2">
            Quick Ready Phrases
          </div>
          <div className="space-y-2">
            <AnimatePresence>
              {translatedPhrases.length === 0 ? (
                <div className="text-[12px] text-[var(--color-text-dim)] italic">
                  Translating common phrases…
                </div>
              ) : (
                translatedPhrases.map((p, i) => (
                  <motion.button
                    key={i}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.02 }}
                    onClick={() => onSpeak(p.en, callerLanguage!, true)}
                    className="w-full text-left rounded-md border border-[var(--color-border)] bg-[var(--color-bg-panel)] px-3 py-2 hover:border-[var(--color-ai-border)] transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-[12px] font-medium text-[var(--color-text)]">{p.en}</div>
                        <div className="text-[11px] text-[var(--color-text-dim)] mt-0.5">{p.translated}</div>
                      </div>
                      <PlayCircle size={17} className="text-[var(--color-text-dim)] shrink-0" />
                    </div>
                  </motion.button>
                ))
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      <div className="p-3 border-t border-[var(--color-border)] space-y-2">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-muted)] font-semibold">
          Compose In English
        </div>
        <div className="flex gap-2">
          <textarea
            value={draftInterim ? `${custom}${custom ? " " : ""}${draftInterim}` : custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder={`Type or dictate in English. It will be translated and spoken in ${callerLanguageName}.`}
            rows={3}
            className="flex-1 rounded-md px-2.5 py-2 text-[13px] bg-[var(--color-bg-elevated)] border border-[var(--color-border)] outline-none focus:border-[var(--color-accent)] resize-none"
          />
          <button
            onClick={() => (isRecording ? stop() : start("en-US"))}
            className={cn(
              "self-start rounded-md px-3 py-2 border inline-flex items-center gap-1.5 text-[12px]",
              isRecording
                ? "border-red-700 bg-red-950/40 text-red-300"
                : "border-[var(--color-border-strong)] bg-[var(--color-bg-panel)] hover:border-[var(--color-accent)]"
            )}
            title="Use worker microphone"
          >
            <Mic size={14} className={isRecording ? "animate-pulse" : undefined} />
            {isRecording ? "Listening" : "Worker Mic"}
          </button>
        </div>
        <div className="flex justify-end">
          <button
            onClick={submit}
            className="rounded-md px-3 py-2 bg-[var(--color-accent)] text-white hover:brightness-110 inline-flex items-center gap-1"
          >
            <Send size={13} />
            Translate & Play
          </button>
        </div>
      </div>

      <audio ref={audioRef} className="hidden" />
    </motion.section>
  );
}
