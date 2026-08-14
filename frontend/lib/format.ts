// Formatting helpers. Deliberately deterministic (no locale, no timezone) so
// that SSR and client produce identical output and never mismatch on hydration.

import type { Grade } from "./types";

const PLACEHOLDER = "—";

// R value: two decimals with an explicit sign (+/-).
export function fmtR(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return PLACEHOLDER;
  }
  const sign = value >= 0 ? "+" : "-";
  return `${sign}${Math.abs(value).toFixed(2)}`;
}

// Win rate: takes a fraction (0..1), prints a percentage with one decimal.
export function fmtPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return PLACEHOLDER;
  }
  return `${(value * 100).toFixed(1)}%`;
}

// Generic number with a configurable number of decimals (default 2).
export function fmtNum(
  value: number | null | undefined,
  decimals = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return PLACEHOLDER;
  }
  return value.toFixed(decimals);
}

// Integer (e.g. trade counts), no decimals.
export function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return PLACEHOLDER;
  }
  return Math.round(value).toString();
}

// Splits an ISO-8601 string (no timezone) into its parts without touching
// Date or locale, which keeps it deterministic for SSR.
function parseIsoParts(iso: string): {
  date: string;
  time: string;
} | null {
  const m = iso.match(
    /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/,
  );
  if (!m) return null;
  const [, y, mo, d, hh, mm] = m;
  return {
    date: `${y}-${mo}-${d}`,
    time: hh !== undefined && mm !== undefined ? `${hh}:${mm}` : "",
  };
}

// Nur Datum: YYYY-MM-DD.
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return PLACEHOLDER;
  const parts = parseIsoParts(iso);
  return parts ? parts.date : PLACEHOLDER;
}

// Date and time: YYYY-MM-DD HH:mm, falling back to the date alone.
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return PLACEHOLDER;
  const parts = parseIsoParts(iso);
  if (!parts) return PLACEHOLDER;
  return parts.time ? `${parts.date} ${parts.time}` : parts.date;
}

// Tailwind class pair (background + text) per grade, for badges.
// Dunkles Terminal-Design (zinc-950-Basis).
export function gradeColor(grade: Grade | null | undefined): string {
  switch (grade) {
    case "A+":
    case "A":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "B":
      return "bg-cyan-500/15 text-cyan-400 border-cyan-500/30";
    case "C":
      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    case "D":
      return "bg-orange-500/15 text-orange-400 border-orange-500/30";
    case "F":
      return "bg-red-500/15 text-red-400 border-red-500/30";
    default:
      return "bg-zinc-500/15 text-zinc-400 border-zinc-500/30";
  }
}
