import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  Ambulance,
  Flame,
  Siren,
  Car,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPhone(v: string | null | undefined): string {
  if (!v) return "";
  const digits = v.replace(/\D/g, "");
  if (digits.length === 10) {
    return `${digits.slice(0, 3)}-${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  return v;
}

export function priorityTone(p: string | null | undefined) {
  switch (p) {
    case "P1":
      return { color: "var(--color-p1)", label: "IMMEDIATE LIFE THREAT", bg: "rgba(239,68,68,0.14)" };
    case "P2":
      return { color: "var(--color-p2)", label: "SERIOUS", bg: "rgba(245,158,11,0.14)" };
    case "P3":
      return { color: "var(--color-p3)", label: "URGENT", bg: "rgba(234,179,8,0.14)" };
    case "P4":
      return { color: "var(--color-p4)", label: "NON-URGENT", bg: "rgba(16,185,129,0.14)" };
    default:
      return { color: "var(--color-text-muted)", label: "Classifying…", bg: "rgba(138,146,168,0.08)" };
  }
}

export function incidentIcon(t: string | null | undefined): LucideIcon {
  switch (t) {
    case "medical":
      return Ambulance;
    case "fire":
      return Flame;
    case "police":
      return Siren;
    case "traffic":
      return Car;
    default:
      return ShieldAlert;
  }
}
