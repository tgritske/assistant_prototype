import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ArrowRight, CheckCircle2, HelpCircle, Lightbulb, PlayCircle, X } from "lucide-react";
import type { Suggestion } from "../types/dispatch";
import { cn } from "../lib/utils";

const URGENCY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

const urgencyStyles = {
  high: {
    ring: "border-[rgba(239,68,68,0.45)]",
    bg: "bg-[rgba(239,68,68,0.07)]",
    icon: <AlertTriangle size={14} className="text-red-400 shrink-0" />,
  },
  medium: {
    ring: "border-[rgba(245,158,11,0.4)]",
    bg: "bg-[rgba(245,158,11,0.07)]",
    icon: <HelpCircle size={14} className="text-amber-400 shrink-0" />,
  },
  low: {
    ring: "border-[var(--color-border)]",
    bg: "bg-[var(--color-bg-elevated)]",
    icon: <Lightbulb size={14} className="text-slate-400 shrink-0" />,
  },
};

const categoryLabels: Record<string, string> = {
  safety: "Safety",
  pre_arrival: "Pre-arrival",
  medical: "Medical",
  info: "Info",
};

interface Props {
  suggestions: Suggestion[];
  onDismiss: (id: string) => void;
  onDone?: (id: string) => void;
  callerLanguage?: string | null;
  callerLanguageName?: string | null;
  onSpeak?: (text: string, language: string, translate?: boolean) => void;
}

export function SuggestionsPanel({ suggestions, onDismiss, onDone, callerLanguage, callerLanguageName, onSpeak }: Props) {
  const [playingId, setPlayingId] = useState<string | null>(null);
  const isNonEnglish = callerLanguage && !callerLanguage.toLowerCase().startsWith("en");

  const playInCallerLanguage = (s: Suggestion) => {
    if (!callerLanguage || !onSpeak || playingId) return;
    onSpeak(s.question, callerLanguage, true);
    setPlayingId(s.id);
    setTimeout(() => setPlayingId(null), 2500);
  };

  const sorted = [...suggestions].sort(
    (a, b) => (URGENCY_ORDER[a.urgency] ?? 1) - (URGENCY_ORDER[b.urgency] ?? 1)
  );

  return (
    <section className="flex flex-col flex-1 min-h-0 bg-[var(--color-bg-panel)] border-t border-[var(--color-border)]">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] uppercase text-[var(--color-text-muted)]">
          <Lightbulb size={13} />
          Suggested Actions
        </div>
        {suggestions.length > 0 && (
          <span className="text-[10px] text-[var(--color-text-dim)]">
            {suggestions.length} pending
          </span>
        )}
      </div>

      <div className="p-3 space-y-2 flex-1 min-h-0 overflow-y-auto">
        {sorted.length === 0 ? (
          <div className="text-[12px] text-[var(--color-text-dim)] py-6 text-center">
            Actions will appear as the call progresses.
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {sorted.map((s) => {
              const style = urgencyStyles[s.urgency] ?? urgencyStyles.medium;
              const isInstruct = s.suggestion_type === "instruct";
              return (
                <motion.div
                  key={s.id}
                  layout
                  initial={{ opacity: 0, y: -4, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, x: 40 }}
                  transition={{ duration: 0.18 }}
                  className={cn(
                    "relative rounded-lg border p-2.5 pr-7",
                    style.ring,
                    style.bg
                  )}
                >
                  {onDone && (
                    <button
                      onClick={() => onDone(s.id)}
                      className="absolute top-1.5 right-6 p-0.5 rounded opacity-60 hover:opacity-100 text-emerald-400"
                      title={isInstruct ? "Done" : "Asked"}
                    >
                      <CheckCircle2 size={12} />
                    </button>
                  )}
                  <button
                    onClick={() => onDismiss(s.id)}
                    className="absolute top-1.5 right-1.5 p-0.5 rounded opacity-50 hover:opacity-100"
                    title={isInstruct ? "Hide" : "Dismiss"}
                  >
                    <X size={12} />
                  </button>

                  <div className="flex items-start gap-2">
                    <div className="mt-0.5">{style.icon}</div>
                    <div className="flex-1 min-w-0">
                      {/* Type + category badges */}
                      <div className="flex items-center gap-1.5 mb-1.5">
                        {isInstruct ? (
                          <span className="inline-flex items-center gap-0.5 text-[9px] font-bold tracking-[0.12em] uppercase px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-400 border border-emerald-700/40">
                            <ArrowRight size={8} />
                            Tell caller
                          </span>
                        ) : (
                          <span className="text-[9px] font-bold tracking-[0.12em] uppercase px-1.5 py-0.5 rounded bg-blue-900/30 text-blue-400 border border-blue-700/40">
                            Ask
                          </span>
                        )}
                        {s.category && categoryLabels[s.category] && (
                          <span className="text-[9px] text-[var(--color-text-dim)] uppercase tracking-wide">
                            · {categoryLabels[s.category]}
                          </span>
                        )}
                      </div>

                      {/* Main question or instruction */}
                      <div className="text-[13.5px] font-medium text-[var(--color-text)] leading-snug">
                        {s.question}
                      </div>

                      {/* Trigger context */}
                      {s.trigger && (
                        <div className="text-[10.5px] text-[var(--color-text-dim)] mt-1.5 italic leading-snug">
                          ❝ {s.trigger}
                        </div>
                      )}

                      {/* Rationale */}
                      {s.rationale && (
                        <div className="text-[11px] text-[var(--color-text-muted)] mt-1 leading-snug">
                          {s.rationale}
                        </div>
                      )}

                      {isNonEnglish && onSpeak && (
                        <button
                          onClick={() => playInCallerLanguage(s)}
                          disabled={playingId !== null}
                          className={cn(
                            "mt-2 inline-flex items-center gap-1.5 text-[11px] font-medium rounded-md px-2 py-1 border transition-colors",
                            playingId === s.id
                              ? "border-blue-700/40 bg-blue-900/20 text-blue-300 opacity-70 cursor-wait"
                              : "border-blue-700/40 bg-blue-900/20 text-blue-300 hover:bg-blue-900/40"
                          )}
                        >
                          <PlayCircle size={12} />
                          {playingId === s.id ? "Playing…" : `Play in ${callerLanguageName}`}
                        </button>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        )}
      </div>
    </section>
  );
}
