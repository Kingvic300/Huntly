import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const TZ = "Africa/Lagos";

export function formatDate(iso?: string | null, opts: Intl.DateTimeFormatOptions = { dateStyle: "medium" }) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, ...opts }).format(new Date(iso));
}

export function formatDateTime(iso?: string | null) {
  return formatDate(iso, { dateStyle: "medium", timeStyle: "short" });
}

export function relativeTime(iso?: string | null) {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  const abs = Math.abs(diff);
  const fmt = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const sign = diff > 0 ? -1 : 1;
  if (abs < 60) return fmt.format(sign * Math.round(abs), "second");
  if (abs < 3600) return fmt.format(sign * Math.round(abs / 60), "minute");
  if (abs < 86400) return fmt.format(sign * Math.round(abs / 3600), "hour");
  if (abs < 86400 * 30) return fmt.format(sign * Math.round(abs / 86400), "day");
  return formatDate(iso);
}

export function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function titleCase(s: string) {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
