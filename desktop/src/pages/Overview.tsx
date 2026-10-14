import { AlertTriangle, CornerUpLeft, KeyRound, MailCheck, Play, Rss, Send, UserRound } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { JobRow } from "@/components/JobRow";
import { STAGE_LINK } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Panel, PanelHeader, Skeleton } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { qk, useAction, useAnalytics, useApplications, useApprovals, useFollowUps, useGmail, useJobs, usePipeline, useProfile, useScheduler, useSources } from "@/lib/queries";
import { formatDate, relativeTime } from "@/lib/utils";

function greeting() {
  const h = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Africa/Lagos", hour: "numeric", hour12: false }).format(new Date()));
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

export default function Overview() {
  const navigate = useNavigate();
  const pipeline = usePipeline();
  const analytics = useAnalytics(14);
  const top = useJobs({ status: "new,saved", sort: "score", limit: 7 });
  const approvals = useApprovals();
  const sched = useScheduler();
  const profile = useProfile();
  const sources = useSources();
  const gmail = useGmail();
  const collect = useAction(() => api("/collect", { method: "POST", json: {} }), { success: "Searching your sources now", invalidate: [qk.scheduler] });
  const digest = useAction(() => api<{ jobs: number }>("/digest/send", { method: "POST" }), { success: (r) => `Digest sent with ${plural(r.jobs, "job")}`, invalidate: [qk.scheduler] });

  const first = profile.data?.profile.full_name?.split(" ")[0];
  const p = pipeline.data;
  const pending = approvals.data?.filter((a) => a.status === "pending" || a.status === "approved") ?? [];
  const completeness = profile.data?.completeness.score ?? 100;
  const noSources = sources.data && sources.data.length === 0;
  const failing = sources.data?.filter((s) => s.enabled && s.last_status === "error") ?? [];
  const followUps = useFollowUps();
  const apps = useApplications();
  const replied = (apps.data ?? []).filter((a) => a.replied_at && ["applied", "awaiting_approval", "preparing"].includes(a.status));
  const nextDigest = sched.data?.jobs?.find((j) => j.id === "digest")?.next_run;

  const sentence = !p ? null : (
    <>
      {p.new_last_24h ? `${plural(p.new_last_24h, "new job")} in the last day` : "No new jobs in the last day"}
      {p.hot_new ? `, ${p.hot_new} of them strong ${p.hot_new === 1 ? "match" : "matches"}` : ""}.{" "}
      {pending.length ? `${plural(pending.length, "email")} ${pending.length === 1 ? "is" : "are"} waiting for your approval.` : "Nothing is waiting for your approval."}
    </>
  );

  const todo = [
    ...pending.slice(0, 4).map((a) => ({
      key: `a${a.id}`,
      icon: MailCheck,
      tone: "text-act",
      title: `Review the email for ${a.job?.title ?? "an application"}`,
      sub: a.to ? `To ${a.to}` : "Recipient missing",
      href: `/approvals?id=${a.id}`,
    })),
    ...replied.map((a) => ({
      key: `r${a.id}`,
      icon: CornerUpLeft,
      tone: "text-ok",
      title: a.reply_hint === "interview" ? `${a.job.company ?? "An employer"} may want to interview you` : `${a.job.company ?? "An employer"} replied`,
      sub: a.reply_subject ? `“${a.reply_subject}”, update the stage` : `About ${a.job.title}, update the stage`,
      href: `/applications?id=${a.id}`,
    })),
    ...(followUps.data ?? []).slice(0, 4).map((f) => ({
      key: `f${f.approval_id}`,
      icon: CornerUpLeft,
      tone: "text-heat",
      title: `No reply from ${f.company ?? "the employer"} after ${f.days_waiting} days`,
      sub: `Follow up on ${f.job_title}`,
      href: `/approvals?id=${f.approval_id}`,
    })),
    ...(gmail.data?.connected && gmail.data.reply_tracking_permission === false
      ? [{ key: "perm", icon: KeyRound, tone: "text-muted", title: "Reconnect Gmail to track replies", sub: "Huntly needs permission to see who replied in your application threads", href: "/settings" }]
      : []),
    ...failing.map((s) => ({ key: `s${s.id}`, icon: AlertTriangle, tone: "text-warn", title: `${s.name} failed to load`, sub: s.last_error ?? "", href: "/sources" })),
    ...(completeness < 100 ? [{ key: "profile", icon: UserRound, tone: "text-muted", title: `Finish your profile (${completeness}%)`, sub: "Scores and documents only use what is in your profile", href: "/cv" }] : []),
    ...(noSources ? [{ key: "src", icon: Rss, tone: "text-muted", title: "Add a job source", sub: "Feeds, company boards or an X search", href: "/sources" }] : []),
  ];

  return (
    <div className="px-8 py-7">
      <div className="flex items-end justify-between gap-6">
        <div>
          <p className="text-[13px] text-muted">
            {greeting()}
            {first ? `, ${first}` : ""}
          </p>
          <h1 className="mt-1 max-w-[30ch] text-[28px] font-semibold leading-[1.15] tracking-[-0.02em]">{sentence ?? <Skeleton className="h-8 w-96" />}</h1>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button onClick={() => digest.mutate()} loading={digest.isPending} disabled={!gmail.data?.connected} title={gmail.data?.connected ? "Email today's digest to yourself" : "Connect Gmail in Settings first"}>
            <Send /> Send digest now
          </Button>
          <Button variant="primary" onClick={() => collect.mutate()} loading={collect.isPending || sched.data?.collecting}>
            <Play /> Search now
          </Button>
        </div>
      </div>

      {p ? (
        <nav aria-label="Your pipeline" className="mt-7 grid grid-cols-7 overflow-hidden rounded-[10px] ring-1 ring-inset ring-line/70">
          {p.stages.map((st, i) => (
            <Link
              key={st.id}
              to={STAGE_LINK[st.id]}
              className={`group px-4 py-3 transition-colors hover:bg-panel ${i ? "border-l border-line/60" : ""}`}
            >
              <span className={`block text-[22px] font-semibold leading-none tabular-nums ${st.count ? (st.id === "awaiting_approval" ? "text-act" : "text-fg") : "text-faint"}`}>{st.count}</span>
              <span className="mt-1.5 block truncate text-[12.5px] text-muted group-hover:text-fg">{st.label}</span>
            </Link>
          ))}
        </nav>
      ) : (
        <Skeleton className="mt-7 h-[70px]" />
      )}

      <div className="mt-6 grid grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)] gap-6">
        <Panel className="overflow-hidden">
          <PanelHeader
            title="Strongest leads"
            description="Open jobs ranked by how well they fit your profile"
            actions={
              <Button size="sm" variant="ghost" onClick={() => navigate("/jobs")}>
                See all
              </Button>
            }
          />
          {top.isPending ? (
            <div className="space-y-2 px-5 pb-5">
              {[0, 1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-11" />
              ))}
            </div>
          ) : top.isError ? (
            <ErrorState error={top.error} onRetry={() => top.refetch()} />
          ) : top.data.items.length ? (
            <div className="divide-y divide-line/50 pb-1">
              {top.data.items.map((j) => (
                <JobRow key={j.id} job={j} onClick={() => navigate(`/jobs?id=${j.id}`)} />
              ))}
            </div>
          ) : (
            <EmptyState
              title="No leads yet"
              description="Add a source and run a search. Each job is scored against your profile as it arrives."
              action={
                <Button variant="primary" onClick={() => navigate("/sources")}>
                  Add a source
                </Button>
              }
            />
          )}
        </Panel>

        <div className="flex flex-col gap-6">
          <Panel>
            <PanelHeader title="Needs you" description={todo.length ? undefined : "You're up to date."} />
            {todo.length ? (
              <ul className="pb-2">
                {todo.map((t) => (
                  <li key={t.key}>
                    <Link to={t.href} className="flex items-start gap-3 px-4 py-2.5 hover:bg-raised">
                      <t.icon className={`mt-0.5 size-4 shrink-0 ${t.tone}`} strokeWidth={1.9} />
                      <span className="min-w-0">
                        <span className="block text-[13.5px]">{t.title}</span>
                        {t.sub ? <span className="block truncate text-[12.5px] text-muted">{t.sub}</span> : null}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="h-3" />
            )}
          </Panel>

          <Panel>
            <PanelHeader title="Last two weeks" description={analytics.data ? `${analytics.data.totals.jobs_in_period} found, ${analytics.data.totals.applications} applications, ${analytics.data.totals.emails_sent} sent` : undefined} />
            <div className="h-28 px-2 pb-3">
              {analytics.data ? (
                <ResponsiveContainer>
                  <AreaChart data={analytics.data.timeline} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
                    <defs>
                      <linearGradient id="wk" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#8fa4ff" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#8fa4ff" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <Area type="monotone" dataKey="discovered" stroke="#8fa4ff" strokeWidth={1.6} fill="url(#wk)" isAnimationActive={false} />
                    <Area type="monotone" dataKey="applied" stroke="#f2b84b" strokeWidth={1.6} fill="transparent" isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <Skeleton className="h-full" />
              )}
            </div>
          </Panel>

          <p className="px-1 text-[12.5px] leading-relaxed text-muted">
            {nextDigest ? <>Your next digest goes to your inbox on {formatDate(nextDigest, { weekday: "long", hour: "2-digit", minute: "2-digit" })}. </> : "The daily digest is off. "}
            {sched.data?.runs?.[0] ? <>Last background run {relativeTime(sched.data.runs[0].started_at)}.</> : null}
          </p>
        </div>
      </div>
    </div>
  );
}
