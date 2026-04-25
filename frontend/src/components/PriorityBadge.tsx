import { motion, AnimatePresence } from "framer-motion";
import { cn, priorityTone } from "../lib/utils";

interface Props {
  priority: "P1" | "P2" | "P3" | "P4" | null | undefined;
  reasoning?: string | null;
  compact?: boolean;
}

export function PriorityBadge({ priority, reasoning, compact }: Props) {
  if (!priority) return null;
  const tone = priorityTone(priority);
  if (compact) {
    return (
      <AnimatePresence mode="popLayout">
        <motion.div
          key={priority}
          initial={{ opacity: 0, y: -4, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 4, scale: 0.96 }}
          transition={{ duration: 0.2 }}
          title={reasoning ?? ""}
          className={cn(
            "inline-flex items-center gap-1.5 text-[10px] font-bold tracking-[0.12em] uppercase px-2.5 py-1 rounded-full border",
            priority === "P1" && "pulse-urgent"
          )}
          style={{
            color: tone.color,
            borderColor: tone.color,
            background: tone.bg,
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: tone.color }} />
          {priority} · {tone.label}
        </motion.div>
      </AnimatePresence>
    );
  }
  return (
    <div
      className="rounded-lg border p-3"
      style={{ borderColor: tone.color, background: tone.bg }}
    >
      <div className="text-[10px] font-bold tracking-[0.14em] uppercase" style={{ color: tone.color }}>
        Priority {priority}
      </div>
      <div className="text-sm mt-0.5 font-medium" style={{ color: tone.color }}>
        {tone.label}
      </div>
      {reasoning && (
        <div className="text-[11px] leading-snug text-[var(--color-text-muted)] mt-1.5">
          {reasoning}
        </div>
      )}
    </div>
  );
}
