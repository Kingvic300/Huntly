import { Building2, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select, Textarea } from "@/components/ui/input";
import { Badge, Dot, Panel, PanelHeader, Skeleton, Switch, Tooltip } from "@/components/ui/misc";
import { api, type CompanyImport } from "@/lib/api";
import { qk, useAction, useCompanies, useSettings } from "@/lib/queries";
import { cn, relativeTime } from "@/lib/utils";

const PLATFORM: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  smartrecruiters: "SmartRecruiters",
  recruitee: "Recruitee",
  workable: "Workable",
  bamboohr: "BambooHR",
  breezy: "Breezy HR",
};
const BATCH_SIZES = [100, 300, 600, 1000, 2000];

/** Companies' own job boards, checked a batch per search. Lives under the Sources list. */
export function CompanyDirectory() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [text, setText] = useState("");
  const companies = useCompanies(debounced);
  const settings = useSettings();
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 200);
    return () => clearTimeout(t);
  }, [q]);

  const add = useAction(() => api<CompanyImport>("/companies/import", { method: "POST", json: { text } }), {
    invalidate: [["companies"]],
    success: (r) => `${r.added} compan${r.added === 1 ? "y" : "ies"} added${r.already_tracked ? `, ${r.already_tracked} already in the directory` : ""}${r.invalid_count ? `. ${r.invalid_count} not recognised: ${r.invalid.slice(0, 3).join(", ")}` : ""}`,
    onSuccess: () => setText(""),
  });
  const toggle = useAction((c: { id: number; enabled: boolean }) => api(`/companies/${c.id}`, { method: "PATCH", json: { enabled: !c.enabled } }), { invalidate: [["companies"]] });
  const batch = useAction((n: number) => api("/settings", { method: "PUT", json: { directory_batch_size: n } }), { invalidate: [qk.settings, ["companies"]], success: "Saved" });

  const d = companies.data;
  const interval = settings.data?.collection_interval_minutes ?? 60;
  const runs = d && d.batch_size ? Math.max(1, Math.ceil(d.tracked / d.batch_size)) : 1;
  const hours = (runs * interval) / 60;
  const cycle = hours < 1.5 ? "every search" : hours < 48 ? `about every ${Math.round(hours)} hours` : `about every ${Math.round(hours / 24)} days`;

  return (
    <Panel>
      <PanelHeader
        title="Company directory"
        description="Companies' own job boards on Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Workable, BambooHR and Breezy HR. Huntly keeps only jobs that match your target roles or skills."
        actions={
          <label className="flex items-center gap-2 text-[12.5px] text-muted">
            Check
            <Select value={String(d?.batch_size ?? 300)} onChange={(e) => batch.mutate(Number(e.target.value))} className="w-[84px]" aria-label="Companies checked per search">
              {BATCH_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
            per search
          </label>
        }
      />
      <div className="px-4 pb-4">
        {companies.isPending ? (
          <Skeleton className="h-24" />
        ) : d ? (
          <>
            <p className="text-[13px]">
              <span className="font-medium tabular-nums">{d.tracked.toLocaleString()}</span> companies
              <span className="text-muted">
                {" "}
                ({Object.entries(d.by_platform)
                  .sort((a, b) => b[1] - a[1])
                  .map(([p, n]) => `${n.toLocaleString()} ${PLATFORM[p] ?? p}`)
                  .join(", ")}
                ). {d.hiring.toLocaleString()} hiring now. Each company is checked {cycle}.
              </span>
            </p>
            <p className="mt-1 text-[12.5px] text-faint">New companies are added when your other sources find jobs at them and Huntly finds their board.</p>

            <div className="mt-4 grid gap-2">
              <Field label="Add companies" hint="Paste board links or platform:name entries, one per line. For example https://boards.greenhouse.io/moniepoint, https://apply.workable.com/kuda, chowdeck.bamboohr.com or ashby:lemfi.">
                <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={"https://jobs.ashbyhq.com/posthog\nsmartrecruiters:vendease"} className="min-h-20 font-mono text-[12.5px]" />
              </Field>
              <div>
                <Button onClick={() => add.mutate()} loading={add.isPending} disabled={!text.trim()}>
                  <Building2 /> Add to directory
                </Button>
              </div>
            </div>

            <div className="relative mt-5">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Find a company"
                aria-label="Find a company in the directory"
                className="h-8 w-64 rounded-[7px] bg-ink pl-8 pr-2 text-[13px] ring-1 ring-inset ring-line placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-act/60"
              />
            </div>
            <div className="mt-2 max-h-[420px] overflow-y-auto rounded-[8px] ring-1 ring-inset ring-line/60">
              {d.items.map((c) => (
                <div key={c.id} className={cn("grid grid-cols-[minmax(0,1fr)_120px_90px_110px_44px] items-center gap-3 border-b border-line/40 px-3 py-2 text-[13px] last:border-0", !c.enabled && "opacity-55")}>
                  <span className="flex min-w-0 items-center gap-2">
                    <Dot tone={!c.enabled ? "idle" : c.last_status === "error" ? "bad" : c.last_status === "ok" ? "ok" : "idle"} />
                    <span className="truncate">{c.name || c.slug}</span>
                    {c.origin === "discovered" ? <Badge tone="act">Found</Badge> : null}
                  </span>
                  <span className="truncate text-[12.5px] text-muted">{PLATFORM[c.platform] ?? c.platform}</span>
                  <Tooltip content={`${c.jobs_found} matched your profile`}>
                    <span className="text-right tabular-nums text-muted">{c.open_jobs} open</span>
                  </Tooltip>
                  <span className="truncate text-[12px] text-faint" title={c.last_error ?? undefined}>
                    {c.last_checked_at ? relativeTime(c.last_checked_at) : "Not yet"}
                  </span>
                  <Switch checked={c.enabled} onCheckedChange={() => toggle.mutate(c)} aria-label={`Check ${c.name || c.slug}`} />
                </div>
              ))}
              {!d.items.length ? <p className="px-3 py-4 text-[12.5px] text-muted">No companies match.</p> : null}
            </div>
            {d.total > d.items.length ? <p className="mt-1.5 text-[12px] text-faint">Showing {d.items.length} of {d.total.toLocaleString()}. Search to find others.</p> : null}
          </>
        ) : null}
      </div>
    </Panel>
  );
}
