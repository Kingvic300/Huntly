/**
 * Client for the local core service. The base URL and per-launch token come
 * from the desktop shell over IPC; they are kept in memory only.
 */
import { isTauri } from "./platform";

export type Conn = { base_url: string; token: string; mode: string };

let connPromise: Promise<Conn> | null = null;

async function loadConnection(): Promise<Conn> {
  if (isTauri) {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<Conn>("core_connection");
  }
  const base = import.meta.env.VITE_CORE_URL as string | undefined;
  const token = import.meta.env.VITE_CORE_TOKEN as string | undefined;
  if (!base || !token) throw new ApiError(0, "Run Huntly inside the desktop app (or set VITE_CORE_URL / VITE_CORE_TOKEN for UI development).");
  return { base_url: base, token, mode: "browser-dev" };
}

export function connection() {
  connPromise ??= loadConnection().catch((e) => {
    connPromise = null;
    throw e instanceof ApiError ? e : new ApiError(0, String(e));
  });
  return connPromise;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const conn = await connection();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${conn.token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(`${conn.base_url}/api${path}`, { ...init, headers, body });
  } catch {
    throw new ApiError(0, "Cannot reach the local core service");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? data.detail.map((d: { msg: string }) => d.msg).join("; ") : detail;
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, detail);
  }
  const ctype = res.headers.get("content-type") || "";
  return (ctype.includes("application/json") ? res.json() : res.blob()) as Promise<T>;
}

export async function waitForCore(timeoutMs = 30000): Promise<Health> {
  const start = Date.now();
  let lastErr: unknown;
  while (Date.now() - start < timeoutMs) {
    try {
      return await api<Health>("/health");
    } catch (e) {
      lastErr = e;
      if (e instanceof ApiError && e.status === 401) throw e;
      await new Promise((r) => setTimeout(r, 300));
    }
  }
  throw lastErr instanceof Error ? lastErr : new ApiError(0, "Core service did not start");
}

// ---- types ------------------------------------------------------------------
export type Health = {
  status: string;
  version: string;
  database: string;
  vault: { initialized: boolean; unlocked: boolean };
  scheduler: SchedulerStatus;
  timezone: string;
  data_dir: string;
};

export type SchedulerStatus = { running: boolean; timezone?: string; collecting?: boolean; jobs?: { id: string; name: string; next_run: string | null }[] };

export type Credential = { name: string; label: string; help: string; configured: boolean; updated_at: string | null };

export type OnboardingStatus = {
  vault_initialized: boolean;
  vault_unlocked: boolean;
  keyring_available: boolean;
  keyring_enabled: boolean;
  onboarding_complete: boolean;
  credentials: Credential[];
  data_dir: string;
};

export type Level = "intern" | "entry" | "mid" | "senior" | "lead" | "manager";
export const LEVEL_LABEL: Record<Level, string> = {
  intern: "Internship",
  entry: "Entry level",
  mid: "Mid level",
  senior: "Senior",
  lead: "Lead / Staff",
  manager: "Manager / Director",
};

export type Job = {
  id: number;
  title: string;
  company: string | null;
  location: string | null;
  remote: boolean;
  seniority: Level | null;
  url: string | null;
  apply_email: string | null;
  posted_at: string | null;
  discovered_at: string;
  score: number;
  status: "new" | "saved" | "dismissed" | "applied";
  source_id: number | null;
  source_name: string | null;
  source_kind: string | null;
  llm_summary: string | null;
  flagged_injection: boolean;
  matched_skills: string[];
  snippet?: string;
  description?: string;
  score_breakdown?: {
    parts: Record<string, number>;
    weights: Record<string, number>;
    reasons: string[];
    matched_skills: string[];
    excluded: string[];
    deterministic: number;
    llm?: { fit: number; summary: string; matching_skills: string[]; missing_skills: string[] };
  };
  application_id?: number | null;
};

export type Source = {
  id: number;
  kind: string;
  name: string;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  last_found: number;
  total_found: number;
};

export type Company = {
  id: number;
  platform: string;
  slug: string;
  name: string | null;
  origin: "seed" | "discovered" | "imported";
  enabled: boolean;
  last_checked_at: string | null;
  last_status: string | null;
  last_error: string | null;
  open_jobs: number;
  jobs_found: number;
};
export type CompanyPage = { total: number; items: Company[]; tracked: number; turned_off: number; by_platform: Record<string, number>; checked: number; hiring: number; batch_size: number };
export type CompanyImport = { added: number; already_tracked: number; invalid: string[]; invalid_count: number };

export type SourceKind = {
  kind: string;
  label: string;
  needs_secret: string | null;
  fields: { key: string; label: string; required?: boolean; placeholder?: string; type?: "number" | "boolean" }[];
};

export type Doc = {
  id: number;
  kind: "base_cv" | "tailored_cv" | "cover_letter";
  title: string;
  job_id: number | null;
  format: "pdf" | "docx";
  path: string;
  sha256: string;
  size: number;
  meta: Record<string, unknown> & { warnings?: string[]; source?: string; ats?: AtsReport; pages?: number | null };
  created_at: string;
};

export type Approval = {
  id: number;
  application_id: number;
  to: string;
  subject: string;
  body: string;
  attachment_ids: number[];
  status: "pending" | "approved" | "rejected" | "sent" | "failed";
  content_hash: string;
  approved_at: string | null;
  gmail_draft_id: string | null;
  gmail_message_id: string | null;
  sent_at: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  job: { id: number; title: string; company: string | null; url: string | null } | null;
  attachments?: Doc[];
  kind: "application" | "follow_up";
  parent_id: number | null;
  replied_at: string | null;
  reply_subject: string | null;
  reply_checked_at: string | null;
  follow_up_dismissed: boolean;
};

export type FollowUp = { approval_id: number; application_id: number; job_title: string; company: string | null; to: string; sent_at: string; days_waiting: number; follow_ups_sent: number };

export type AtsReport = {
  keywords: string[];
  covered: string[];
  unused_from_profile: string[];
  gaps: string[];
  coverage: number | null;
  title_match: boolean;
  checks: { id: string; label: string; ok: boolean }[];
  score: number;
};

export type ParsedCv = { fields: Partial<Profile>; sections_found: string[]; warnings: string[] };

export type AppStatus = "preparing" | "awaiting_approval" | "applied" | "interviewing" | "offer" | "rejected" | "withdrawn";
export const APP_STATUSES: AppStatus[] = ["preparing", "awaiting_approval", "applied", "interviewing", "offer", "rejected", "withdrawn"];

export type Application = {
  id: number;
  status: AppStatus;
  job: Job;
  cv_document_id: number | null;
  cover_letter_document_id: number | null;
  contact_email: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
  applied_at: string | null;
  replied_at: string | null;
  reply_subject: string | null;
  reply_hint: "interview" | "declined" | "offer" | null;
  approvals: Approval[] | null;
};

export type Experience = { title: string; company: string; location: string; start: string; end: string; highlights: string[] };
export type Education = { institution: string; qualification: string; start: string; end: string; details: string };
export type Project = { name: string; description: string; url: string; technologies: string[] };
export type Profile = {
  full_name: string;
  headline: string;
  email: string;
  phone: string;
  location: string;
  linkedin_url: string;
  github_url: string;
  portfolio_url: string;
  links: string[];
  summary: string;
  skills: string[];
  experience: Experience[];
  education: Education[];
  projects: Project[];
  certifications: string[];
  languages: string[];
  target_roles: string[];
  preferred_locations: string[];
  remote_only: boolean;
  seniority: string[];
  exclude_keywords: string[];
};
export type ProfileResponse = { profile: Profile; completeness: { score: number; checks: Record<string, boolean> } };

export type Settings = {
  collection_interval_minutes: number;
  collection_enabled: boolean;
  digest_enabled: boolean;
  digest_time: string;
  digest_min_score: number;
  min_score_to_show: number;
  groq_model: string;
  groq_enabled: boolean;
  onboarding_complete: boolean;
  approval_window_minutes: number;
  reply_tracking_enabled: boolean;
  follow_up_after_days: number;
  reply_body_analysis: boolean;
  auto_update: boolean;
  directory_batch_size: number;
  gmail_address?: string | null;
  timezone: string;
};

export type GmailStatus = { client_configured: boolean; connected: boolean; email: string | null; flow_running: boolean; flow_error: string | null; reply_tracking_permission: boolean | null; reply_reading_permission: boolean | null };
export type Notification = { id: number; ts: string; level: string; title: string; body: string; read: boolean };
export type AuditEntry = { id: number; ts: string; actor: string; action: string; entity: string; entity_id: string | null; detail: Record<string, unknown> };
export type Run = { id: number; kind: string; trigger: string; started_at: string; finished_at: string | null; status: string; stats: Record<string, number>; error: string | null };

export type Analytics = {
  days: number;
  totals: { jobs: number; jobs_in_period: number; new_jobs: number; applications: number; emails_sent: number; pending_approvals: number; avg_score: number | null; remote_share: number | null };
  timeline: { date: string; discovered: number; applied: number }[];
  score_distribution: { bucket: string; count: number }[];
  by_source: { source: string; count: number }[];
  top_skills: { skill: string; count: number }[];
  funnel: { status: string; count: number }[];
};
