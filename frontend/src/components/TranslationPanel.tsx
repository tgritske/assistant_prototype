import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, Send } from "lucide-react";
import { cn } from "../lib/utils";
import { useWebSpeechCapture } from "../hooks/useWebSpeechCapture";

interface Props {
  callerLanguage: string | null;
  callerLanguageName: string | null;
  onSpeak: (text: string, language: string, translate?: boolean) => void;
  lastTTSAudio: { language: string; text: string; audio_base64: string } | null;
}

export function TranslationPanel({
  callerLanguage,
  callerLanguageName,
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
      <div className="p-3 space-y-2">
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
