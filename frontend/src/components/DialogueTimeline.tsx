import { useEffect, useRef } from "react";
import type { DialogueTurn } from "../types/dispatch";

interface Props {
  turns: DialogueTurn[];
  callerInterim?: string;
  workerInterim?: string;
  highlights?: string[];
}

export function DialogueTimeline({
  turns,
  callerInterim,
  workerInterim,
  highlights = [],
}: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turns, callerInterim, workerInterim]);

  const finalTurns = turns.filter((t) => t.is_final);

  return (
    <div ref={scrollRef} className="space-y-2.5">
      {finalTurns.map((t) => (
        <TurnRow key={t.id} turn={t} highlights={highlights} />
      ))}
      {callerInterim && (
        <TurnRow
          turn={{
            id: "caller-interim",
            seq: -1,
            speaker: "caller",
            channel: "interim",
            source: "whisper",
            text: callerInterim,
            start: 0,
            end: 0,
            is_final: false,
            language: null,
          }}
          highlights={highlights}
        />
      )}
      {workerInterim && (
        <TurnRow
          turn={{
            id: "worker-interim",
            seq: -1,
            speaker: "worker",
            channel: "interim",
            source: "whisper",
            text: workerInterim,
            start: 0,
            end: 0,
            is_final: false,
            language: null,
          }}
          highlights={highlights}
        />
      )}
    </div>
  );
}

function TurnRow({ turn, highlights }: { turn: DialogueTurn; highlights: string[] }) {
  const isCaller = turn.speaker === "caller";
  const align = isCaller ? "items-start" : "items-end";
  const bubbleColor = isCaller
    ? "bg-blue-950/30 border-blue-900/60 text-blue-50"
    : "bg-emerald-950/30 border-emerald-900/60 text-emerald-50";
  const labelColor = isCaller ? "text-blue-300" : "text-emerald-300";
  const label = isCaller ? "Caller" : "Worker";

  return (
    <div className={`flex flex-col ${align}`}>
      <div className={`text-[10px] uppercase tracking-[0.12em] font-semibold mb-0.5 ${labelColor}`}>
        {label}
      </div>
      <div
        className={`max-w-[85%] rounded-xl border px-3.5 py-2 text-[14px] leading-relaxed whitespace-pre-wrap ${bubbleColor} ${
          turn.is_final ? "" : "italic opacity-80"
        }`}
      >
        {highlightText(turn.text, highlights)}
      </div>
    </div>
  );
}

function highlightText(text: string, keywords: string[]): React.ReactNode {
  if (!keywords.length || !text) return text;
  const unique = Array.from(
    new Set(keywords.map((k) => k.trim()).filter(Boolean))
  ).sort((a, b) => b.length - a.length);
  if (!unique.length) return text;
  const pattern = new RegExp(
    "(" + unique.map(escapeRegex).join("|") + ")",
    "gi",
  );
  const parts = text.split(pattern);
  return parts.map((p, i) =>
    pattern.test(p) && i % 2 === 1 ? (
      <mark key={i} className="kw-highlight">
        {p}
      </mark>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
