import { motion } from "framer-motion";
import { Play, Square, Mic } from "lucide-react";
import type { ScenarioSummary } from "../types/dispatch";
import { cn } from "../lib/utils";

interface Props {
  scenarios: ScenarioSummary[];
  inCall: boolean;
  activeId: string | null;
  onPlay: (id: string) => void;
  onStop: () => void;
  onLiveMic?: () => void;
  micActive?: boolean;
}

const catColors: Record<string, string> = {
  medical: "rgba(239,68,68,0.4)",
  fire: "rgba(245,158,11,0.5)",
  police: "rgba(59,130,246,0.5)",
  traffic: "rgba(234,179,8,0.5)",
  multilingual: "rgba(168,85,247,0.5)",
};

const catLabel: Record<string, string> = {
  medical: "Medical",
  fire: "Fire",
  police: "Police",
  traffic: "Traffic",
  multilingual: "Multilingual",
};

const catEmoji: Record<string, string> = {
  medical: "🚑",
  fire: "🔥",
  police: "🚔",
  traffic: "🚗",
  multilingual: "🌐",
};

export function ScenarioPicker({
  scenarios,
  inCall,
  activeId,
  onPlay,
  onStop,
  onLiveMic,
  micActive,
}: Props) {
  const liveMicMode = inCall && !activeId;

  return (
    <aside className="flex flex-col h-full bg-[var(--color-bg-elevated)] border-r border-[var(--color-border)] min-h-0">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border)]">
        <div className="text-[11px] font-semibold tracking-[0.14em] uppercase text-[var(--color-text-muted)]">
          {liveMicMode ? (
            <span className="flex items-center gap-1.5 text-red-400">
              <Mic size={11} className="animate-pulse" />
              Live Mic
            </span>
          ) : (
            "Demo Scenarios"
          )}
        </div>
        {inCall && (
          <button
            onClick={onStop}
            className="text-[10px] font-bold tracking-[0.1em] uppercase text-red-300 inline-flex items-center gap-1 px-2 py-0.5 rounded border border-red-900/50 hover:bg-red-950/30"
          >
            <Square size={10} fill="currentColor" />
            End Call
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {scenarios.map((s) => {
          const active = s.id === activeId && inCall;
          const border = catColors[s.category] ?? "var(--color-border)";
          return (
            <motion.button
              key={s.id}
              whileHover={{ x: 2 }}
              onClick={() => onPlay(s.id)}
              disabled={inCall && !active}
              className={cn(
                "w-full text-left rounded-lg border p-2.5 transition-colors",
                "bg-[var(--color-bg-panel)] hover:bg-[var(--color-bg)] disabled:opacity-40",
                active && "ring-2 ring-offset-0"
              )}
              style={{
                borderColor: border,
                boxShadow: active
                  ? `0 0 0 1px ${border}`
                  : undefined,
              }}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-base leading-none">
                      {catEmoji[s.category] ?? "🚨"}
                    </span>
                    <span className="text-[9px] font-bold tracking-[0.12em] uppercase px-1.5 py-0.5 rounded border"
                      style={{ color: border, borderColor: border }}>
                      {catLabel[s.category] ?? s.category}
                    </span>
                    {s.language !== "en-US" && (
                      <span className="text-[9px] font-mono text-[var(--color-text-dim)]">
                        {s.language}
                      </span>
                    )}
                  </div>
                  <div className="text-[13px] font-medium leading-tight">
                    {s.title}
                  </div>
                  <div className="text-[11px] text-[var(--color-text-muted)] leading-snug mt-1">
                    {s.description}
                  </div>
                </div>
                <div
                  className={cn(
                    "rounded-full p-1.5 shrink-0 border",
                    active
                      ? "bg-[var(--color-live)] border-[var(--color-live)] text-black pulse-ring"
                      : "border-[var(--color-border-strong)] text-[var(--color-text-dim)]"
                  )}
                >
                  <Play size={12} fill="currentColor" />
                </div>
              </div>
            </motion.button>
          );
        })}
      </div>

      {onLiveMic && (
        <div className="p-3 border-t border-[var(--color-border)]">
          <button
            onClick={onLiveMic}
            disabled={inCall}
            className={cn(
              "w-full rounded-md py-2 text-[12px] font-semibold tracking-[0.1em] uppercase border inline-flex items-center justify-center gap-2 disabled:opacity-40 transition-colors",
              micActive
                ? "bg-red-950/40 border-red-700 text-red-300"
                : "bg-[var(--color-bg-panel)] border-[var(--color-border-strong)] hover:border-[var(--color-accent)]"
            )}
          >
            <Mic size={13} className={micActive ? "animate-pulse" : undefined} />
            {micActive ? "Recording…" : "Use Live Microphone"}
          </button>
        </div>
      )}
    </aside>
  );
}
