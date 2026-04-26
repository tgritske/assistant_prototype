import { Cpu, Lock, Radio, ShieldAlert } from "lucide-react";
import { cn } from "../lib/utils";

interface Props {
  connected: boolean;
  inCall: boolean;
  callId: string | null;
  elapsed: number;
  priorityBadge?: React.ReactNode;
  llmBackend?: string | null;
  llmModel?: string | null;
  llmMode?: "live" | "local_rules" | null;
}

export function StatusBar({
  connected,
  inCall,
  callId,
  elapsed,
  priorityBadge,
  llmBackend,
  llmModel,
  llmMode,
}: Props) {
  return (
    <header className="flex items-center justify-between gap-4 px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="text-[var(--color-critical)]" size={22} strokeWidth={2.5} />
          <div className="flex flex-col leading-tight">
            <div className="text-[15px] font-semibold tracking-wide">
              E.D.A.I.A.
            </div>
            <div className="text-[10px] tracking-[0.14em] text-[var(--color-text-dim)]">
              Emergency Dispatcher AI Assistant
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {priorityBadge}
        <Pill tone={connected ? "good" : "bad"}>
          <span className={cn("w-1.5 h-1.5 rounded-full", connected ? "bg-[var(--color-live)] pulse-ring" : "bg-red-500")} />
          {connected ? "CONNECTED" : "OFFLINE"}
        </Pill>
        <Pill tone={inCall ? "live" : "dim"}>
          <Radio size={13} />
          {inCall ? `LIVE · ${fmtElapsed(elapsed)}` : "STANDBY"}
        </Pill>
        {/* <Pill tone="info" title="Audio never leaves this machine. Whisper runs locally; only structured text reaches the LLM.">
          <Lock size={13} />
          AUDIO LOCAL
        </Pill>
        {llmMode && (
          <Pill
            tone={llmMode === "live" ? (llmBackend?.toLowerCase().includes("ollama") ? "good" : "info") : "dim"}
            title={
              llmMode === "live"
                ? `Structured extraction: ${llmBackend}${llmModel ? ` · ${llmModel}` : ""}`
                : "No LLM available; using local evidence-based extraction rules"
            }
          >
            <Cpu size={13} />
            {llmMode === "live" ? (llmBackend ?? "LLM") : "LOCAL RULES"}
          </Pill>
        )} */}
        {/* {callId && (
          <div className="text-[10px] font-mono text-[var(--color-text-dim)]">#{callId}</div>
        )} */}
      </div>
    </header>
  );
}

function fmtElapsed(sec: number) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function Pill({
  children,
  tone,
  title,
}: {
  children: React.ReactNode;
  tone: "good" | "bad" | "live" | "dim" | "info";
  title?: string;
}) {
  const styles = {
    good: "text-[var(--color-live)] border-[rgba(16,185,129,0.35)] bg-[rgba(16,185,129,0.08)]",
    bad: "text-red-400 border-red-900/50 bg-red-900/10",
    live: "text-[var(--color-live)] border-[rgba(16,185,129,0.35)] bg-[rgba(16,185,129,0.08)]",
    dim: "text-[var(--color-text-muted)] border-[var(--color-border-strong)] bg-[var(--color-bg-panel)]",
    info: "text-blue-300 border-blue-900/40 bg-blue-950/30",
  }[tone];
  return (
    <div
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.1em] uppercase px-2.5 py-1 rounded-full border",
        styles
      )}
    >
      {children}
    </div>
  );
}
