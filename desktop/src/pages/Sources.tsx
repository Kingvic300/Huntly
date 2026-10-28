import { KeyRound, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Dot, EmptyState, ErrorState, PageHeader, Skeleton, Switch, Tooltip } from "@/components/ui/misc";
import { api, type Source, type SourceKind } from "@/lib/api";
import { qk, useAction, useCatalog, useCredentials, useScheduler, useSources } from "@/lib/queries";
import { cn, relativeTime } from "@/lib/utils";

const BLURB: Record<string, string> = {
  rss: "Any RSS or Atom job feed",
  x_search: "Posts on X that match a search",
  greenhouse: "A company's Greenhouse job board",
  lever: "A company's Lever job board",
  ashby: "A company's Ashby job board",
  remotive: "Remote jobs from Remotive",
  remoteok: "Remote jobs from Remote OK",
  himalayas: "Remote jobs from Himalayas",
  jobicy: "Remote jobs from Jobicy",
  arbeitnow: "Jobs from the Arbeitnow board",
  career_page: "A careers page that publishes job data",
};
const CRED_NAME: Record<string, string> = { x_bearer_token: "X bearer token" };

function SourceDialog({ open, onOpenChange, editing, catalog }: { open: boolean; onOpenChange: (o: boolean) => void; editing: Source | null; catalog: SourceKind[] }) {
  const [kind, setKind] = useState<string | null>(editing?.kind ?? null);
  const [name, setName] = useState(editing?.name ?? "");
  const [config, setConfig] = useState<Record<string, unknown>>(editing?.config ?? {});
  const spec = catalog.find((c) => c.kind === kind);
  const save = useAction(
    () => (editing ? api(`/sources/${editing.id}`, { method: "PATCH", json: { name, config } }) : api("/sources", { method: "POST", json: { kind, name: name || spec?.label, config } })),
    { success: editing ? "Source saved" : "Source added", invalidate: [qk.sources], onSuccess: () => onOpenChange(false) },
  );
  const missing = spec?.fields.some((f) => f.required && !String(config[f.key] ?? "").trim());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={editing ? `Edit ${editing.name}` : spec ? spec.label : "Add a source"}
        description={!spec ? "Huntly only uses official APIs, feeds and job data that sites publish for search engines." : BLURB[spec.kind]}
        className="w-[min(600px,92vw)]"
        footer={
          spec ? (
            <>
              {!editing ? (
                <Button variant="ghost" className="mr-auto" onClick={() => setKind(null)}>
                  Back
                </Button>
              ) : null}
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={() => save.mutate()} loading={save.isPending} disabled={missing}>
                {editing ? "Save source" : "Add source"}
              </Button>
            </>
          ) : undefined
        }
      >
        {!spec ? (
          <div className="grid grid-cols-2 gap-2">
            {catalog.map((c) => (
              <button
                key={c.kind}
                onClick={() => {
                  setKind(c.kind);
                  setConfig({});
                }}
                className="rounded-[9px] bg-raised p-3.5 text-left ring-1 ring-inset ring-line/70 hover:ring-act/60"
              >
                <span className="block text-[13.5px] font-medium">{c.label}</span>
                <span className="mt-0.5 block text-[12.5px] text-muted">{BLURB[c.kind]}</span>
                {c.needs_secret ? <span className="mt-2 flex items-center gap-1 text-[11.5px] text-faint"><KeyRound className="size-3" /> Needs your {CRED_NAME[c.needs_secret] ?? c.needs_secret}</span> : null}
              </button>
            ))}
          </div>
        ) : (
          <form
            className="grid gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!missing) save.mutate();
            }}
          >
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={spec.label} autoFocus />
            </Field>
            {spec.fields.map((f) =>
              f.type === "boolean" ? (
                <label key={f.key} className="flex items-center gap-3 text-[13.5px]">
                  <Switch checked={!!config[f.key]} onCheckedChange={(v) => setConfig({ ...config, [f.key]: v })} /> {f.label}
                </label>
              ) : (
                <Field key={f.key} label={f.required ? f.label : `${f.label} (optional)`}>
                  <Input
                    type={f.type === "number" ? "number" : "text"}
                    value={String(config[f.key] ?? "")}
                    placeholder={f.placeholder}
                    onChange={(e) => setConfig({ ...config, [f.key]: f.type === "number" ? Number(e.target.value) : e.target.value })}
                  />
                </Field>
              ),
            )}
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function Sources() {
  const sources = useSources();
  const catalog = useCatalog();
  const creds = useCredentials();
  const sched = useScheduler();
  const [dialog, setDialog] = useState<{ open: boolean; editing: Source | null }>({ open: false, editing: null });
  const [toDelete, setToDelete] = useState<Source | null>(null);
  const toggle = useAction((s: Source) => api(`/sources/${s.id}`, { method: "PATCH", json: { enabled: !s.enabled } }), { invalidate: [qk.sources] });
  const run = useAction((ids: number[]) => api("/collect", { method: "POST", json: { source_ids: ids } }), { success: "Searching now", invalidate: [qk.scheduler] });
  const del = useAction((id: number) => api(`/sources/${id}`, { method: "DELETE" }), { success: "Source removed", invalidate: [qk.sources], onSuccess: () => setToDelete(null) });
  const configured = new Set(creds.data?.filter((c) => c.configured).map((c) => c.name));
  const label = (k: string) => catalog.data?.find((c) => c.kind === k)?.label ?? k;
  const next = sched.data?.jobs?.find((j) => j.id === "collect")?.next_run;

  return (
    <div>
      <PageHeader
        title="Sources"
        description={`Where Huntly looks for jobs. ${next ? `The next automatic search is ${relativeTime(next)}.` : "Automatic search is off."}`}
        actions={
          <Button variant="primary" onClick={() => setDialog({ open: true, editing: null })} disabled={!catalog.data}>
            <Plus /> Add source
          </Button>
        }
      />
      <div className="px-7 pb-8">
        {sources.isPending ? (
          <Skeleton className="h-48" />
        ) : sources.isError ? (
          <ErrorState error={sources.error} onRetry={() => sources.refetch()} />
        ) : sources.data.length ? (
          <div className="overflow-hidden rounded-[10px] ring-1 ring-inset ring-line/70">
            <div className="grid grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)_110px_96px_150px] gap-4 bg-panel px-4 py-2 text-[12px] font-medium text-faint">
              <span>Source</span>
              <span>Last search</span>
              <span className="text-right">Found</span>
              <span>On</span>
              <span />
            </div>
            {sources.data.map((s) => {
              const needs = catalog.data?.find((c) => c.kind === s.kind)?.needs_secret;
              const missingKey = needs && !configured.has(needs);
              const watching = Object.values(s.config).filter((v) => typeof v === "string" && v).join(", ");
              return (
                <div key={s.id} className={cn("grid grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)_110px_96px_150px] items-center gap-4 border-t border-line/60 px-4 py-3", !s.enabled && "opacity-55")}>
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="mt-[6px]">
                      <Dot tone={!s.enabled ? "idle" : s.last_status === "error" ? "bad" : s.last_status === "ok" ? "ok" : "idle"} />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-[13.5px] font-medium">{s.name}</span>
                      <span className="block truncate text-[12.5px] text-muted">
                        {label(s.kind)}
                        {watching ? <span className="text-faint">, {watching}</span> : null}
                      </span>
                      {missingKey ? (
                        <Link to="/settings" className="mt-1 flex items-center gap-1 text-[12px] text-warn hover:underline">
                          <KeyRound className="size-3" /> Add your {CRED_NAME[needs] ?? needs} to use this
                        </Link>
                      ) : s.last_status === "error" && s.last_error ? (
                        <span className="mt-1 block line-clamp-2 text-[12px] text-bad selectable">{s.last_error}</span>
                      ) : null}
                    </span>
                  </div>
                  <span className="text-[12.5px] text-muted">{s.last_run_at ? relativeTime(s.last_run_at) : "Never"}</span>
                  <Tooltip content={`${s.total_found} in total`}>
                    <span className="text-right text-[13px] tabular-nums">
                      {s.last_found ? `+${s.last_found}` : "0"} <span className="text-faint">new</span>
                    </span>
                  </Tooltip>
                  <Switch checked={s.enabled} onCheckedChange={() => toggle.mutate(s)} aria-label={`Use ${s.name}`} />
                  <div className="flex justify-end gap-0.5">
                    <Button size="icon-sm" variant="ghost" aria-label={`Search ${s.name} now`} title="Search now" onClick={() => run.mutate([s.id])} disabled={sched.data?.collecting || !s.enabled}>
                      <Play />
                    </Button>
                    <Button size="icon-sm" variant="ghost" aria-label={`Edit ${s.name}`} title="Edit" onClick={() => setDialog({ open: true, editing: s })}>
                      <Pencil />
                    </Button>
                    <Button size="icon-sm" variant="ghost" aria-label={`Remove ${s.name}`} title="Remove" onClick={() => setToDelete(s)}>
                      <Trash2 />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <EmptyState
            className="px-0"
            title="Huntly isn't watching anywhere yet"
            description="Add a job feed, a company's Greenhouse or Lever board, Remotive, Arbeitnow, a careers page, or an X search."
            action={
              <Button variant="primary" onClick={() => setDialog({ open: true, editing: null })}>
                <Plus /> Add your first source
              </Button>
            }
          />
        )}
      </div>
      {dialog.open && catalog.data ? (
        <SourceDialog key={dialog.editing?.id ?? "new"} open={dialog.open} onOpenChange={(o) => setDialog({ open: o, editing: o ? dialog.editing : null })} editing={dialog.editing} catalog={catalog.data} />
      ) : null}
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={`Remove ${toDelete?.name}?`}
        description="Jobs already found from this source stay in your history."
        confirmLabel="Remove source"
        tone="danger"
        loading={del.isPending}
        onConfirm={() => toDelete && del.mutate(toDelete.id)}
      />
    </div>
  );
}
