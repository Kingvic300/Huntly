import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  api,
  type Analytics,
  type Application,
  type Approval,
  type AuditEntry,
  type Credential,
  type Doc,
  type FollowUp,
  type GmailStatus,
  type Health,
  type Job,
  type Notification,
  type OnboardingStatus,
  type ProfileResponse,
  type Run,
  type SchedulerStatus,
  type Settings,
  type Source,
  type SourceKind,
} from "./api";

export const qk = {
  health: ["health"],
  onboarding: ["onboarding"],
  jobs: (params: Record<string, unknown>) => ["jobs", params],
  job: (id: number) => ["job", id],
  sources: ["sources"],
  catalog: ["sources", "catalog"],
  applications: ["applications"],
  application: (id: number) => ["application", id],
  approvals: ["approvals"],
  approval: (id: number) => ["approval", id],
  documents: ["documents"],
  profile: ["profile"],
  settings: ["settings"],
  credentials: ["credentials"],
  gmail: ["gmail"],
  notifications: ["notifications"],
  audit: ["audit"],
  scheduler: ["scheduler"],
  analytics: (days: number) => ["analytics", days],
  digest: ["digest"],
  pipeline: ["pipeline"],
  followUps: ["follow-ups"],
} as const;

export type Pipeline = { stages: { id: string; label: string; count: number }[]; new_last_24h: number; hot_new: number; failing_sources: number };
export const usePipeline = () => useQuery({ queryKey: qk.pipeline, queryFn: () => api<Pipeline>("/pipeline"), refetchInterval: 15000 });

export const useHealth = () => useQuery({ queryKey: qk.health, queryFn: () => api<Health>("/health"), refetchInterval: 15000 });
export const useOnboarding = () => useQuery({ queryKey: qk.onboarding, queryFn: () => api<OnboardingStatus>("/onboarding/status") });

export function useJobs(params: Record<string, string | number | boolean | undefined>) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && qs.set(k, String(v)));
  return useQuery({ queryKey: qk.jobs(params), queryFn: () => api<{ total: number; items: Job[] }>(`/jobs?${qs}`), placeholderData: (prev) => prev });
}
export const useJob = (id: number | null) => useQuery({ queryKey: qk.job(id ?? 0), queryFn: () => api<Job>(`/jobs/${id}`), enabled: !!id });
export const useSources = () => useQuery({ queryKey: qk.sources, queryFn: () => api<Source[]>("/sources") });
export const useCatalog = () => useQuery({ queryKey: qk.catalog, queryFn: () => api<SourceKind[]>("/sources/catalog"), staleTime: Infinity });
export const useApplications = () => useQuery({ queryKey: qk.applications, queryFn: () => api<Application[]>("/applications") });
export const useApplication = (id: number | null) => useQuery({ queryKey: qk.application(id ?? 0), queryFn: () => api<Application>(`/applications/${id}`), enabled: !!id });
export const useApprovals = () => useQuery({ queryKey: qk.approvals, queryFn: () => api<Approval[]>("/approvals") });
export const useApproval = (id: number | null) => useQuery({ queryKey: qk.approval(id ?? 0), queryFn: () => api<Approval>(`/approvals/${id}`), enabled: !!id });
export const useDocuments = () => useQuery({ queryKey: qk.documents, queryFn: () => api<Doc[]>("/documents") });
export const useProfile = () => useQuery({ queryKey: qk.profile, queryFn: () => api<ProfileResponse>("/profile") });
export const useSettings = () => useQuery({ queryKey: qk.settings, queryFn: () => api<Settings>("/settings") });
export const useCredentials = () => useQuery({ queryKey: qk.credentials, queryFn: () => api<Credential[]>("/credentials") });
export const useGmail = (poll = false) => useQuery({ queryKey: qk.gmail, queryFn: () => api<GmailStatus>("/gmail/status"), refetchInterval: poll ? 1500 : 30000 });
export const useNotifications = () => useQuery({ queryKey: qk.notifications, queryFn: () => api<{ items: Notification[]; unread: number }>("/notifications"), refetchInterval: 10000 });
export const useAudit = () => useQuery({ queryKey: qk.audit, queryFn: () => api<AuditEntry[]>("/audit") });
export const useScheduler = () => useQuery({ queryKey: qk.scheduler, queryFn: () => api<SchedulerStatus & { runs: Run[] }>("/scheduler"), refetchInterval: 5000 });
export const useAnalytics = (days: number) => useQuery({ queryKey: qk.analytics(days), queryFn: () => api<Analytics>(`/analytics?days=${days}`) });

/** Mutation with toast feedback and cache invalidation. */
export function useAction<TVars = void, TRes = unknown>(
  fn: (vars: TVars) => Promise<TRes>,
  opts: { success?: string | ((r: TRes) => string); invalidate?: QueryKey[]; onSuccess?: (r: TRes, v: TVars) => void; silent?: boolean } = {},
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r, v) => {
      if (opts.success) toast.success(typeof opts.success === "function" ? opts.success(r) : opts.success);
      [...(opts.invalidate ?? []), qk.pipeline].forEach((key) => qc.invalidateQueries({ queryKey: key }));
      opts.onSuccess?.(r, v);
    },
    onError: (e: Error) => {
      if (!opts.silent) toast.error(e.message);
    },
  });
}

export const useFollowUps = () => useQuery({ queryKey: qk.followUps, queryFn: () => api<FollowUp[]>("/follow-ups"), refetchInterval: 60000 });
