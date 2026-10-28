import { Bookmark, Briefcase, ExternalLink, EyeOff, Play, RotateCcw, Search, ShieldAlert, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { JobRow } from "@/components/JobRow";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { Badge, EmptyState, ErrorState, MatchRing, Segmented, Skeleton } from "@/components/ui/misc";
import { api, type Application, type Job } from "@/lib/api";
import { announceDocuments, type Generated } from "@/pages/Applications";
import { openUrl } from "@/lib/platform";
import { qk, useAction, useJob, useJobs, useSources } from "@/lib/queries";
import { formatDate, relativeTime, titleCase } from "@/lib/utils";

const PART_LABEL: Record<string, string> = { skills: "Skills overlap", title: "Title vs target roles", location: "Location and remote", recency: "How recent", seniority: "Seniority" };

function useJobActions(id: number) {
  const navigate = useNavigate();
  const setStatus = useAction((status: Job["status"]) => api(`/jobs/${id}`, { method: "PATCH", json: { status } }), {
    invalidate: [["jobs"], qk.job(id)],
    success: (_r) => "Updated",
  });
  const apply = useAction(() => api<Application>("/applications", { method: "POST", json: { job_id: id } }), {
    invalidate: [qk.applications, ["jobs"], qk.job(id)],
    onSuccess: (app) => navigate(`/applications?id=${app.id}`),
  });
  // One click: start the application and make the tailored CV and cover letter.
  const tailor = useAction(
    async () => {
      const app = await api<Application>("/applications", { method: "POST", json: { job_id: id } });
      const docs = await api<Generated>(`/applications/${app.id}/documents`, { method: "POST", json: { format: "pdf", use_llm: true } }).catch((e: Error) => e);
      return { app, docs };
    },
    {
      invalidate: [qk.applications, qk.documents, ["jobs"], qk.job(id)],
      onSuccess: ({ app, docs }) => {
        if (docs instanceof Error) toast.error(docs.message);
        else announceDocuments(docs);
        navigate(`/applications?id=${app.id}`);
      },
    },
  );
  return { setStatus, apply, tailor };
}

function JobDetail({ id }: { id: number }) {
  const job = useJob(id);
  const navigate = useNavigate();
  const { setStatus, apply, tailor } = useJobActions(id);

  if (job.isPending)
    return (
      <div className="space-y-4 px-10 py-9">
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-48" />
      </div>
    );
  if (job.isError) return <ErrorState error={job.error} onRetry={() => job.refetch()} />;
  const j = job.data;
  const b = j.score_breakdown;
  const where = j.remote && !/remote/i.test(j.location ?? "") ? [j.location, "Remote"].filter(Boolean).join(", ") : j.location ?? "";

  return (
    <article className="px-10 py-9">
      <div className="flex items-start gap-6">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] text-muted">
            {j.company ?? "Company not listed"}
            {where ? <span className="text-faint">, {where}</span> : null}
          </p>
          <h1 className="mt-1 text-[24px] font-semibold leading-tight tracking-[-0.015em] selectable">{j.title}</h1>
          <p className="mt-2 text-[12.5px] text-faint">
            Posted {formatDate(j.posted_at)}, found {relativeTime(j.discovered_at)} via {j.source_name ?? "a removed source"}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-center gap-1.5 pt-1">
          <MatchRing score={j.score} size="lg" />
          <span className="text-[11.5px] text-muted">CV match</span>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {j.application_id ? (
          <Button variant="primary" onClick={() => navigate(`/applications?id=${j.application_id}`)}>
            <Briefcase /> Open application
          </Button>
        ) : (
          <>
            <Button variant="primary" onClick={() => tailor.mutate()} loading={tailor.isPending} disabled={apply.isPending}>
              <Sparkles /> Tailor for this job
            </Button>
            <Button onClick={() => apply.mutate()} loading={apply.isPending} disabled={tailor.isPending}>
              <Briefcase /> Start application
            </Button>
          </>
        )}
        {j.url ? (
          <Button onClick={() => openUrl(j.url!)}>
            <ExternalLink /> Open posting
          </Button>
        ) : null}
        {j.status === "new" ? (
          <Button onClick={() => setStatus.mutate("saved")}>
            <Bookmark /> Shortlist
          </Button>
        ) : null}
        {j.status === "dismissed" ? (
          <Button variant="ghost" onClick={() => setStatus.mutate("new")}>
            <RotateCcw /> Restore
          </Button>
        ) : (
          <Button variant="ghost" onClick={() => setStatus.mutate("dismissed")}>
            <EyeOff /> Not for me
          </Button>
        )}
        <Badge className="ml-auto">{j.status === "saved" ? "Shortlisted" : titleCase(j.status)}</Badge>
      </div>

      {j.flagged_injection ? (
        <div className="mt-6 flex gap-3 rounded-[8px] bg-warn/8 px-4 py-3 text-[13px] ring-1 ring-inset ring-warn/25">
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-warn" />
          <p className="text-muted">
            <span className="font-medium text-fg">This posting tries to give instructions to AI tools.</span> Huntly ignores them and treats the text as plain data. Read it with care.
          </p>
        </div>
      ) : null}

      {b ? (
        <section className="mt-8">
          <h2 className="section-title">Why it scored {Math.round(j.score)}</h2>
          <div className="mt-3 space-y-2.5">
            {Object.entries(b.parts).map(([k, v]) => {
              const max = b.weights[k] || 1;
              return (
                <div key={k} className="grid grid-cols-[150px_1fr_52px] items-center gap-4 text-[13px]">
                  <span className="text-muted">{PART_LABEL[k] ?? titleCase(k)}</span>
                  <span className="h-[6px] rounded-full bg-raised">
                    <span className="block h-full rounded-full bg-heat/80" style={{ width: `${Math.min(100, (v / max) * 100)}%` }} />
                  </span>
                  <span className="text-right tabular-nums text-muted">
                    <span className="text-fg">{Math.round(v)}</span>/{max}
                  </span>
                </div>
              );
            })}
          </div>
          {b.reasons.length ? (
            <ul className="mt-4 space-y-1 text-[13px] text-muted">
              {b.reasons.map((r) => (
                <li key={r} className="flex gap-2">
                  <span className="text-faint">–</span>
                  {r}
                </li>
              ))}
            </ul>
          ) : null}
          {b.llm ? (
            <div className="mt-5 rounded-[8px] bg-act/7 px-4 py-3 text-[13px] ring-1 ring-inset ring-act/20">
              <p className="font-medium">
                Groq's read: fit {b.llm.fit} <span className="font-normal text-muted">(30% of the score; rule-based part is {b.deterministic})</span>
              </p>
              <p className="mt-1 text-muted selectable">{b.llm.summary}</p>
              {b.llm.missing_skills.length ? <p className="mt-1.5 text-faint">Gaps: {b.llm.missing_skills.join(", ")}</p> : null}
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="mt-9">
        <h2 className="section-title">The posting</h2>
        {j.apply_email ? <p className="mt-1 text-[12.5px] text-muted selectable">Apply by email: {j.apply_email}</p> : null}
        <div className="mt-3 max-w-[72ch] whitespace-pre-wrap text-[14px] leading-[1.65] text-fg/88 selectable">{j.description || "The source didn't include a description. Open the posting to read it."}</div>
      </section>
    </article>
  );
}

type StatusFilter = "new,saved" | "new" | "saved" | "applied" | "dismissed" | "";

export default function Jobs() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("id") ? Number(params.get("id")) : null;
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState<StatusFilter>((params.get("status") as StatusFilter) ?? "new,saved");
  const [minScore, setMinScore] = useState(0);
  const [remote, setRemote] = useState<"" | "true" | "false">("");
  const [sort, setSort] = useState<"score" | "recent" | "posted">("score");
  const [sourceId, setSourceId] = useState("");
  const [limit, setLimit] = useState(60);
  const sources = useSources();
  const listRef = useRef<HTMLDivElement>(null);
  const collect = useAction(() => api("/collect", { method: "POST", json: {} }), { success: "Searching your sources now", invalidate: [qk.scheduler] });

  useEffect(() => {
    const s = params.get("status");
    if (s !== null) setStatus(s as StatusFilter);
  }, [params]);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 200);
    return () => clearTimeout(t);
  }, [q]);

  const jobs = useJobs({ q: debounced, status, min_score: minScore, remote: remote || undefined, sort, source_id: sourceId || undefined, limit });
  const items = jobs.data?.items ?? [];
  const select = useCallback((id: number) => setParams((p) => ({ ...Object.fromEntries(p), id: String(id) })), [setParams]);
  const { setStatus: setJobStatus, apply } = useJobActions(selected ?? 0);

  // Keyboard triage: J/K move, S shortlist, D dismiss, A start application, O open posting.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable]") || e.ctrlKey || e.metaKey || e.altKey) return;
      const idx = items.findIndex((j) => j.id === selected);
      const cur = idx >= 0 ? items[idx] : undefined;
      const k = e.key.toLowerCase();
      if (k === "j" || e.key === "ArrowDown") {
        const next = items[Math.min(idx + 1, items.length - 1)];
        if (next) select(next.id);
      } else if (k === "k" || e.key === "ArrowUp") {
        const prev = items[Math.max(idx - 1, 0)];
        if (prev) select(prev.id);
      } else if (cur && k === "s") setJobStatus.mutate("saved");
      else if (cur && k === "d") setJobStatus.mutate("dismissed");
      else if (cur && k === "a") apply.mutate();
      else if (cur && k === "o" && cur.url) openUrl(cur.url);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, selected, select, setJobStatus, apply]);

  useEffect(() => {
    listRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 overflow-x-auto border-b border-line/70 px-5 py-3">
        <Segmented
          value={status}
          onChange={(v) => {
            setStatus(v);
            setParams({});
          }}
          options={[
            { value: "new,saved", label: "Open" },
            { value: "new", label: "New" },
            { value: "saved", label: "Shortlisted" },
            { value: "applied", label: "Applied" },
            { value: "dismissed", label: "Dismissed" },
            { value: "", label: "All" },
          ]}
        />
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter by keyword"
            aria-label="Filter jobs by keyword"
            className="h-8 w-44 rounded-[7px] bg-ink pl-8 pr-2 text-[13px] ring-1 ring-inset ring-line placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-act/60"
          />
        </div>
        <Select value={String(minScore)} onChange={(e) => setMinScore(Number(e.target.value))} className="w-[112px] shrink-0" aria-label="Minimum match">
          {[0, 30, 50, 70, 85].map((s) => (
            <option key={s} value={s}>
              {s === 0 ? "Any match" : `Match ${s}+`}
            </option>
          ))}
        </Select>
        <Select value={remote} onChange={(e) => setRemote(e.target.value as typeof remote)} className="w-[138px] shrink-0" aria-label="Work location">
          <option value="">Anywhere</option>
          <option value="true">Remote</option>
          <option value="false">On-site or hybrid</option>
        </Select>
        <Select value={sourceId} onChange={(e) => setSourceId(e.target.value)} className="w-[136px] shrink-0" aria-label="Source">
          <option value="">All sources</option>
          {sources.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <Select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} className="w-[146px] shrink-0" aria-label="Sort">
          <option value="score">Best match first</option>
          <option value="recent">Newest found</option>
          <option value="posted">Newest posted</option>
        </Select>
        <Button className="ml-auto shrink-0" onClick={() => collect.mutate()} loading={collect.isPending}>
          <Play /> Search now
        </Button>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="flex w-[42%] min-w-[400px] max-w-[560px] flex-col border-r border-line/70">
          <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto">
            {jobs.isPending ? (
              <div className="space-y-2 p-5">
                {Array.from({ length: 9 }).map((_, i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : jobs.isError ? (
              <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />
            ) : items.length ? (
              <div className="divide-y divide-line/40">
                {items.map((j) => (
                  <JobRow key={j.id} job={j} active={j.id === selected} onClick={() => select(j.id)} />
                ))}
                {jobs.data.total > items.length ? (
                  <div className="p-4">
                    <Button size="sm" variant="ghost" onClick={() => setLimit(limit + 60)}>
                      Show {Math.min(60, jobs.data.total - items.length)} more of {jobs.data.total - items.length}
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : (
              <EmptyState title="No jobs match these filters" description="Loosen a filter, or run a search to pull in new jobs from your sources." />
            )}
          </div>
          <div className="flex items-center gap-3 border-t border-line/70 px-5 py-2 text-[11.5px] text-faint">
            <span>{jobs.data ? `${jobs.data.total} jobs` : ""}</span>
            <span className="ml-auto flex items-center gap-1">
              <span className="key">J</span>
              <span className="key">K</span> move
            </span>
            <span className="flex items-center gap-1">
              <span className="key">S</span> shortlist
            </span>
            <span className="flex items-center gap-1">
              <span className="key">D</span> dismiss
            </span>
            <span className="flex items-center gap-1">
              <span className="key">A</span> apply
            </span>
          </div>
        </div>
        <div className="min-w-0 flex-1 overflow-y-auto">
          {selected ? <JobDetail key={selected} id={selected} /> : <EmptyState className="h-full" title="Pick a job to read it" description="Use J and K to move through the list without the mouse." />}
        </div>
      </div>
    </div>
  );
}
