import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState, ErrorState, PageHeader, Panel, PanelHeader, Segmented, Skeleton } from "@/components/ui/misc";
import { useAnalytics } from "@/lib/queries";
import { titleCase } from "@/lib/utils";

const AXIS = { stroke: "#6c7383", fontSize: 11.5, tickLine: false, axisLine: false } as const;
const TIP = {
  contentStyle: { background: "#252a33", border: "1px solid #434a5a", borderRadius: 8, fontSize: 12.5, color: "#eceef2" },
  labelStyle: { color: "#9aa1af" },
  cursor: { fill: "rgba(143,164,255,0.06)" },
};
const FUNNEL_LABEL: Record<string, string> = { preparing: "Applying", awaiting_approval: "Awaiting approval", applied: "Sent", interviewing: "Interviewing", offer: "Offer", rejected: "Rejected", withdrawn: "Withdrawn" };

function Figure({ value, label }: { value: React.ReactNode; label: string }) {
  return (
    <div>
      <div className="text-[30px] font-semibold leading-none tracking-[-0.02em]">{value}</div>
      <div className="mt-1.5 text-[12.5px] text-muted">{label}</div>
    </div>
  );
}

export default function Analytics() {
  const [days, setDays] = useState<"7" | "30" | "90" | "365">("30");
  const a = useAnalytics(Number(days));
  const t = a.data?.totals;
  const rate = t && t.jobs_in_period ? Math.round((100 * t.applications) / t.jobs_in_period) : null;

  return (
    <div>
      <PageHeader
        title="Insights"
        description="Worked out from your own history on this computer."
        actions={
          <Segmented
            value={days}
            onChange={setDays}
            options={[
              { value: "7", label: "7 days" },
              { value: "30", label: "30 days" },
              { value: "90", label: "90 days" },
              { value: "365", label: "Year" },
            ]}
          />
        }
      />
      <div className="space-y-6 px-7 pb-8">
        {a.isPending ? (
          <Skeleton className="h-96" />
        ) : a.isError ? (
          <ErrorState error={a.error} onRetry={() => a.refetch()} />
        ) : a.data.totals.jobs === 0 && a.data.totals.applications === 0 ? (
          <EmptyState className="px-0" title="Nothing to chart yet" description="Charts fill in once Huntly has found jobs or you've started an application." />
        ) : (
          <>
            <div className="grid grid-cols-5 gap-6 border-y border-line/60 py-5">
              <Figure value={a.data.totals.jobs_in_period} label="jobs found" />
              <Figure value={a.data.totals.avg_score != null ? Math.round(a.data.totals.avg_score) : "–"} label="average match" />
              <Figure value={a.data.totals.applications} label="applications" />
              <Figure value={rate != null ? `${rate}%` : "–"} label="of jobs applied to" />
              <Figure value={a.data.totals.emails_sent} label="emails sent" />
            </div>
            <Panel>
              <PanelHeader
                title="Found and applied, by day"
                description={
                  <span className="flex gap-4">
                    <span className="flex items-center gap-1.5">
                      <span className="h-[3px] w-3 rounded bg-act" /> Found
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="h-[3px] w-3 rounded bg-heat" /> Applied
                    </span>
                  </span>
                }
              />
              <div className="h-64 px-3 pb-3">
                <ResponsiveContainer>
                  <AreaChart data={a.data.timeline} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="found" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#8fa4ff" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="#8fa4ff" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#323845" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="date" {...AXIS} tickFormatter={(d: string) => d.slice(5)} minTickGap={28} />
                    <YAxis {...AXIS} allowDecimals={false} width={30} />
                    <Tooltip {...TIP} />
                    <Area type="monotone" dataKey="discovered" name="Found" stroke="#8fa4ff" fill="url(#found)" strokeWidth={1.8} isAnimationActive={false} />
                    <Area type="monotone" dataKey="applied" name="Applied" stroke="#f2b84b" fill="transparent" strokeWidth={1.8} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <div className="grid grid-cols-2 gap-6">
              <Panel>
                <PanelHeader title="How well jobs match you" description="Number of jobs at each match score" />
                <div className="h-56 px-3 pb-3">
                  <ResponsiveContainer>
                    <BarChart data={a.data.score_distribution} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="#323845" strokeDasharray="2 4" vertical={false} />
                      <XAxis dataKey="bucket" {...AXIS} />
                      <YAxis {...AXIS} allowDecimals={false} width={30} />
                      <Tooltip {...TIP} />
                      <Bar dataKey="count" name="Jobs" fill="#f2b84b" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Panel>
              <Panel>
                <PanelHeader title="Where your applications are" />
                <div className="h-56 px-3 pb-3">
                  <ResponsiveContainer>
                    <BarChart data={a.data.funnel.map((f) => ({ ...f, label: FUNNEL_LABEL[f.status] ?? titleCase(f.status) }))} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <XAxis type="number" {...AXIS} allowDecimals={false} />
                      <YAxis type="category" dataKey="label" {...AXIS} width={124} />
                      <Tooltip {...TIP} />
                      <Bar dataKey="count" name="Applications" fill="#8fa4ff" radius={[0, 3, 3, 0]} barSize={14} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Panel>
              <Panel>
                <PanelHeader title="Jobs by source" />
                <div className="h-56 px-3 pb-3">
                  <ResponsiveContainer>
                    <BarChart data={a.data.by_source} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <XAxis type="number" {...AXIS} allowDecimals={false} />
                      <YAxis type="category" dataKey="source" {...AXIS} width={124} />
                      <Tooltip {...TIP} />
                      <Bar dataKey="count" name="Jobs" fill="#8fa4ff" radius={[0, 3, 3, 0]} barSize={14} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Panel>
              <Panel>
                <PanelHeader title="Your skills employers ask for" description="How many jobs mention each of your skills" />
                <div className="h-56 px-3 pb-3">
                  <ResponsiveContainer>
                    <BarChart data={a.data.top_skills} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <XAxis type="number" {...AXIS} allowDecimals={false} />
                      <YAxis type="category" dataKey="skill" {...AXIS} width={124} />
                      <Tooltip {...TIP} />
                      <Bar dataKey="count" name="Jobs" fill="#f2b84b" radius={[0, 3, 3, 0]} barSize={14} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Panel>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
