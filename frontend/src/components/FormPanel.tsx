import { useRef, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Send, Sparkles, User } from "lucide-react";
import type { FormFields } from "../types/dispatch";
import { cn, formatPhone, incidentIcon } from "../lib/utils";
import { PriorityBadge } from "./PriorityBadge";

interface Props {
  form: FormFields;
  aiFilled: Set<string>;
  manualEdits: Set<string>;
  priority: FormFields["priority"];
  priorityReasoning: string | null;
  onEdit: (field: keyof FormFields, value: unknown) => void;
  onDispatch: () => void;
  canDispatch: boolean;
}

export function FormPanel({
  form,
  aiFilled,
  manualEdits,
  priority,
  priorityReasoning,
  onEdit,
  onDispatch,
  canDispatch,
}: Props) {
  return (
    <section className="flex flex-col h-full bg-[var(--color-bg-panel)] min-h-0">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] uppercase text-[var(--color-text-muted)]">
          <span className="text-lg leading-none">{incidentIcon(form.incident_type)}</span>
          Incident Form
        </div>
        <PriorityBadge priority={priority} reasoning={priorityReasoning} compact />
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <Row>
          <Field
            label="Incident Type"
            name="incident_type"
            type="select"
            options={[
              { v: "medical", l: "🚑 Medical" },
              { v: "fire", l: "🔥 Fire" },
              { v: "police", l: "🚔 Police" },
              { v: "traffic", l: "🚗 Traffic" },
              { v: "other", l: "🚨 Other" },
            ]}
            value={form.incident_type ?? ""}
            aiFilled={aiFilled.has("incident_type")}
            manualEdit={manualEdits.has("incident_type")}
            onChange={(v) => onEdit("incident_type", v || null)}
          />
          <Field
            label="Priority"
            name="priority"
            type="select"
            options={[
              { v: "P1", l: "P1 — Immediate life threat" },
              { v: "P2", l: "P2 — Serious" },
              { v: "P3", l: "P3 — Urgent" },
              { v: "P4", l: "P4 — Non-urgent" },
            ]}
            value={form.priority ?? ""}
            aiFilled={aiFilled.has("priority")}
            manualEdit={manualEdits.has("priority")}
            onChange={(v) => onEdit("priority", v || null)}
          />
        </Row>

        <Row>
          <Field
            label="Caller Name"
            name="caller_name"
            icon={<User size={12} />}
            value={form.caller_name ?? ""}
            aiFilled={aiFilled.has("caller_name")}
            manualEdit={manualEdits.has("caller_name")}
            onChange={(v) => onEdit("caller_name", v)}
          />
          <Field
            label="Callback #"
            name="callback_number"
            value={formatPhone(form.callback_number) || ""}
            aiFilled={aiFilled.has("callback_number")}
            manualEdit={manualEdits.has("callback_number")}
            onChange={(v) => onEdit("callback_number", v)}
          />
        </Row>

        <Field
          label="Location"
          name="location"
          type="textarea"
          value={form.location ?? ""}
          aiFilled={aiFilled.has("location")}
          manualEdit={manualEdits.has("location")}
          onChange={(v) => onEdit("location", v)}
          emphasise
        />

        <Row>
          <Field
            label="Cross Street"
            name="cross_street"
            value={form.cross_street ?? ""}
            aiFilled={aiFilled.has("cross_street")}
            manualEdit={manualEdits.has("cross_street")}
            onChange={(v) => onEdit("cross_street", v)}
          />
          <Field
            label="# Victims"
            name="num_victims"
            value={form.num_victims != null ? String(form.num_victims) : ""}
            aiFilled={aiFilled.has("num_victims")}
            manualEdit={manualEdits.has("num_victims")}
            onChange={(v) => onEdit("num_victims", v ? parseInt(v, 10) : null)}
          />
        </Row>

        <Field
          label="Description"
          name="description"
          type="textarea"
          value={form.description ?? ""}
          aiFilled={aiFilled.has("description")}
          manualEdit={manualEdits.has("description")}
          onChange={(v) => onEdit("description", v)}
        />

        <Row>
          <Field
            label="Victim Age"
            name="victim_age"
            value={form.victim_age ?? ""}
            aiFilled={aiFilled.has("victim_age")}
            manualEdit={manualEdits.has("victim_age")}
            onChange={(v) => onEdit("victim_age", v)}
          />
          <Field
            label="Victim Condition"
            name="victim_condition"
            value={form.victim_condition ?? ""}
            aiFilled={aiFilled.has("victim_condition")}
            manualEdit={manualEdits.has("victim_condition")}
            onChange={(v) => onEdit("victim_condition", v)}
          />
        </Row>

        <Row>
          <Field
            label="Injuries"
            name="injuries_reported"
            type="select"
            options={[
              { v: "yes", l: "Yes" },
              { v: "no", l: "No" },
              { v: "unknown", l: "Unknown" },
            ]}
            value={form.injuries_reported ?? ""}
            aiFilled={aiFilled.has("injuries_reported")}
            manualEdit={manualEdits.has("injuries_reported")}
            onChange={(v) => onEdit("injuries_reported", v || null)}
          />
          <Field
            label="Weapons"
            name="weapons_involved"
            type="select"
            options={[
              { v: "yes", l: "Yes" },
              { v: "no", l: "No" },
              { v: "unknown", l: "Unknown" },
            ]}
            value={form.weapons_involved ?? ""}
            aiFilled={aiFilled.has("weapons_involved")}
            manualEdit={manualEdits.has("weapons_involved")}
            onChange={(v) => onEdit("weapons_involved", v || null)}
          />
        </Row>

        <Field
          label="Hazards"
          name="hazards"
          type="textarea"
          value={form.hazards ?? ""}
          aiFilled={aiFilled.has("hazards")}
          manualEdit={manualEdits.has("hazards")}
          onChange={(v) => onEdit("hazards", v)}
        />

        <Field
          label="Suspect Description"
          name="suspect_description"
          type="textarea"
          value={form.suspect_description ?? ""}
          aiFilled={aiFilled.has("suspect_description")}
          manualEdit={manualEdits.has("suspect_description")}
          onChange={(v) => onEdit("suspect_description", v)}
        />

        <Field
          label="Vehicle Info"
          name="vehicle_info"
          type="textarea"
          value={form.vehicle_info ?? ""}
          aiFilled={aiFilled.has("vehicle_info")}
          manualEdit={manualEdits.has("vehicle_info")}
          onChange={(v) => onEdit("vehicle_info", v)}
        />

        <Field
          label="Notes"
          name="notes"
          type="textarea"
          value={form.notes ?? ""}
          aiFilled={aiFilled.has("notes")}
          manualEdit={manualEdits.has("notes")}
          onChange={(v) => onEdit("notes", v)}
        />
      </div>

      <div className="p-3 border-t border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
        <button
          onClick={onDispatch}
          disabled={!canDispatch}
          className={cn(
            "w-full rounded-lg py-2.5 font-semibold text-[13px] tracking-[0.1em] uppercase flex items-center justify-center gap-2",
            canDispatch
              ? "bg-[var(--color-critical)] text-white hover:brightness-110"
              : "bg-[var(--color-bg-panel)] text-[var(--color-text-dim)] border border-[var(--color-border)] cursor-not-allowed"
          )}
        >
          <Send size={15} />
          Send to CAD System
        </button>
      </div>
    </section>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-2">{children}</div>;
}

interface FieldProps {
  label: string;
  name: string;
  value: string;
  aiFilled: boolean;
  manualEdit: boolean;
  onChange: (v: string) => void;
  type?: "text" | "textarea" | "select";
  options?: { v: string; l: string }[];
  icon?: React.ReactNode;
  emphasise?: boolean;
}

function Field(props: FieldProps) {
  const {
    label,
    value,
    aiFilled,
    manualEdit,
    onChange,
    type = "text",
    options,
    icon,
    emphasise,
  } = props;

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = el.scrollHeight + "px";
  }, [value]);

  const inputCls = cn(
    "w-full rounded-md px-2.5 py-1.5 text-[13px] text-[var(--color-text)] outline-none transition-colors",
    "border",
    aiFilled
      ? "border-[var(--color-ai-border)] bg-[var(--color-ai-bg)] ai-flash"
      : manualEdit
      ? "border-[var(--color-border-strong)] bg-[var(--color-bg-elevated)]"
      : "border-[var(--color-border)] bg-[var(--color-bg-elevated)] focus:border-[var(--color-accent)]",
    emphasise && "text-[15px] font-medium"
  );

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <label className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-muted)] inline-flex items-center gap-1">
          {icon}
          {label}
        </label>
        <AnimatePresence>
          {aiFilled && !manualEdit && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              className="inline-flex items-center gap-0.5 text-[9px] font-bold tracking-[0.1em] uppercase text-blue-300"
            >
              <Sparkles size={9} />
              AI
            </motion.div>
          )}
          {manualEdit && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-[9px] font-bold tracking-[0.1em] uppercase text-[var(--color-text-muted)]"
            >
              EDITED
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      {type === "textarea" ? (
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={cn(inputCls, "resize-none overflow-hidden")}
          style={{ minHeight: "3rem" }}
        />
      ) : type === "select" ? (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={inputCls}
        >
          <option value="">—</option>
          {options?.map((o) => (
            <option key={o.v} value={o.v}>
              {o.l}
            </option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={inputCls}
        />
      )}
    </div>
  );
}
