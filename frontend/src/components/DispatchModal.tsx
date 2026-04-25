import { useEffect, useMemo } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import type { FormFields } from "../types/dispatch";
import { PriorityBadge } from "./PriorityBadge";

interface Props {
  form: FormFields;
  priority: FormFields["priority"];
  priorityReasoning: string | null;
  callId: string | null;
  elapsed: number;
  onConfirm: () => void;
  onCancel: () => void;
}

const FIELD_LABELS: Record<keyof FormFields, string> = {
  incident_type: "Incident Type",
  priority: "Priority",
  caller_name: "Caller Name",
  callback_number: "Callback #",
  location: "Location",
  cross_street: "Cross Street",
  description: "Description",
  injuries_reported: "Injuries",
  num_victims: "# Victims",
  victim_age: "Victim Age",
  victim_condition: "Victim Condition",
  hazards: "Hazards",
  weapons_involved: "Weapons",
  suspect_description: "Suspect Description",
  vehicle_info: "Vehicle Info",
  notes: "Notes",
};

export function DispatchModal({
  form,
  priority,
  priorityReasoning,
  callId,
  elapsed,
  onConfirm,
  onCancel,
}: Props) {
  const rows = useMemo(
    () =>
      Object.entries(form).filter(([, value]) => value !== null && value !== undefined && value !== ""),
    [form]
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
      if (event.key === "Enter") onConfirm();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onCancel, onConfirm]);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-[var(--color-border-strong)] bg-[var(--color-bg-panel)] shadow-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-[var(--color-border)] flex items-start justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold tracking-[0.14em] uppercase text-[var(--color-text-muted)]">
              Dispatch Confirmation
            </div>
            <div className="mt-1 text-xl font-semibold text-[var(--color-text)] flex items-center gap-2">
              <AlertTriangle size={18} className="text-red-400" />
              {callId ? `INC-${callId.toUpperCase()}` : "Incident Ready"}
            </div>
          </div>
          <PriorityBadge priority={priority} reasoning={priorityReasoning} />
        </div>

        <div className="px-5 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-3 text-[12px] text-[var(--color-text-muted)]">
            <div>Elapsed: {Math.floor(elapsed)}s</div>
            <div className="text-right">{new Date().toLocaleString()}</div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {rows.map(([key, value]) => (
              <div key={key} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-2">
                <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                  {FIELD_LABELS[key as keyof FormFields]}
                </div>
                <div className="mt-1 text-[13px] text-[var(--color-text)] break-words">
                  {String(value)}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="px-5 py-4 border-t border-[var(--color-border)] flex justify-end gap-3 bg-[var(--color-bg-elevated)]">
          <button
            onClick={onCancel}
            className="rounded-lg px-4 py-2 border border-[var(--color-border-strong)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="rounded-lg px-4 py-2 bg-[var(--color-critical)] text-white inline-flex items-center gap-2 hover:brightness-110"
          >
            <CheckCircle2 size={16} />
            Confirm Dispatch
          </button>
        </div>
      </div>
    </div>
  );
}
