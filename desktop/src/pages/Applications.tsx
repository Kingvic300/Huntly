import { Check, CornerUpLeft, ExternalLink, FileText, Mail, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { DocActions } from "@/components/DocActions";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Badge, EmptyState, ErrorState, HeatMeter, PageHeader, Skeleton, Switch } from "@/components/ui/misc";
import { Sheet } from "@/components/ui/sheet";
import { api, APP_STATUSES, type AppStatus, type Application, type Approval, type AtsReport, type Doc } from "@/lib/api";
import { openUrl } from "@/lib/platform";
import { qk, useAction, useApplication, useApplications, useDocuments, useSettings } from "@/lib/queries";
import { cn, formatDateTime, relativeTime, titleCase } from "@/lib/utils";

const LABEL: Record<AppStatus, string> = {
  preparing: "Applying",
  awaiting_approval: "Awaiting approval",
  applied: "Sent",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};
const BOARD: AppStatus[] = ["preparing", "awaiting_approval", "applied", "interviewing", "offer"];

export function StatusBadge({ status }: { status: AppStatus }) {
  const tone = status === "awaiting_approval" ? "act" : status === "offer" ? "ok" : status === "interviewing" ? "heat" : status === "rejected" ? "bad" : "neutral";
  return <Badge tone={tone}>{LABEL[status]}</Badge>;
}

function Step({ n, title, done, children }: { n: number; title: string; done: boolean; children: React.ReactNode }) {
  return (
    <section className="relative pl-10">
      <span className={cn("absolute left-0 top-0 flex size-6 items-center justify-center rounded-full text-[12px] font-semibold", done ? "bg-ok/15 text-ok" : "bg-raised text-muted ring-1 ring-line")}>{n}</span>
      <h3 className="section-title leading-6">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function AtsPanel({ ats }: { ats: AtsReport }) {
  const tone = ats.score >= 80 ? "text-ok" : ats.score >= 60 ? "text-heat" : "text-bad";
  return (
    <div className="mt-4 rounded-[10px] bg-ink/60 p-4 ring-1 ring-inset ring-line/70">
      <div className="flex items-baseline gap-3">
        <span className={cn("text-[24px] font-semibold leading-none tabular-nums", tone)}>{ats.score}</span>
        <span className="text-[13px] font-medium">ATS readiness</span>
        <span className="ml-auto text-[12.5px] text-muted">
          {ats.coverage != null ? `${ats.covered.length} of ${ats.keywords.length} job keywords in your CV` : "No recognisable keywords in this posting"}
        </span>
      </div>
      {ats.keywords.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {ats.covered.map((k) => (
            <Badge key={k} tone="ok">
              {k}
            </Badge>
          ))}
          {ats.gaps.map((k) => (
            <Badge key={k} className="line-through decoration-faint">
              {k}
            </Badge>
          ))}
        </div>
      ) : null}
      {ats.gaps.length ? (
        <p className="mt-2.5 text-[12.5px] leading-relaxed text-muted">
          The job also asks for {ats.gaps.join(", ")}. These aren't in your profile, so they were left out. If you genuinely have them, add them to your profile and make the CV again.
        </p>
      ) : null}
      <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5">
        {ats.checks.map((c) => (
          <li key={c.id} className="flex items-start gap-2 text-[12.5px]">
            {c.ok ? <Check className="mt-0.5 size-3.5 shrink-0 text-ok" /> : <X className="mt-0.5 size-3.5 shrink-0 text-bad" />}
            <span className={c.ok ? "text-muted" : "text-fg"}>{c.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ApplicationDetail({ id, onDeleted }: { id: number; onDeleted: () => void }) {
  const app = useApplication(id);
  const docs = useDocuments();
  const settings = useSettings();
  const navigate = useNavigate();
  const [notes, setNotes] = useState<string | null>(null);
  const [contact, setContact] = useState<string | null>(null);
  const [fmt, setFmt] = useState<"pdf" | "docx">("pdf");
  const [useLlm, setUseLlm] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const inv = [qk.application(id), qk.applications, qk.documents, qk.approvals];

  useEffect(() => {
    if (app.data) {
      setNotes(app.data.notes);
      setContact(app.data.contact_email ?? "");
    }
  }, [app.data?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const patch = useAction((body: Partial<Pick<Application, "status" | "notes" | "contact_email">>) => api(`/applications/${id}`, { method: "PATCH", json: body }), { invalidate: inv, success: "Saved" });
  const generate = useAction(() => api<{ warnings: string[]; source: string }>(`/applications/${id}/documents`, { method: "POST", json: { format: fmt, use_llm: useLlm } }), {
    invalidate: inv,
    onSuccess: (r) => {
      toast.success(r.source === "groq" ? "CV and cover letter ready, with AI-suggested wording" : "CV and cover letter ready");
      r.warnings.forEach((w) => toast.warning(w));
    },
  });
  const prepare = useAction(() => api<Approval>(`/applications/${id}/email`, { method: "POST", json: { to: contact || null } }), {
    invalidate: inv,
    onSuccess: (a) => navigate(`/approvals?id=${a.id}`),
  });
  const del = useAction(() => api(`/applications/${id}`, { method: "DELETE" }), { invalidate: [qk.applications, ["jobs"]], success: "Application deleted", onSuccess: onDeleted });
  const docById = useMemo(() => new Map((docs.data ?? []).map((d) => [d.id, d])), [docs.data]);

  if (app.isPending)
    return (
      <div className="space-y-3 p-8">
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-40" />
      </div>
    );
  if (app.isError) return <ErrorState error={app.error} onRetry={() => app.refetch()} />;
  const a = app.data;
  const cv = a.cv_document_id ? docById.get(a.cv_document_id) : undefined;
  const cl = a.cover_letter_document_id ? docById.get(a.cover_letter_document_id) : undefined;
  const openApproval = a.approvals?.find((x) => ["pending", "approved", "failed"].includes(x.status));
  const sent = a.approvals?.some((x) => x.status === "sent");

  const DocLine = ({ d, label }: { d?: Doc; label: string }) => (
    <div className="flex items-center gap-3 py-1.5">
      <FileText className={cn("size-4", d ? "text-fg" : "text-faint")} strokeWidth={1.8} />
      <span className="min-w-0 flex-1">
        <span className="block text-[13.5px]">{label}</span>
        <span className="block truncate text-[12px] text-muted">{d ? `${d.format.toUpperCase()}, made ${relativeTime(d.created_at)}${d.meta?.source === "groq" ? ", AI-suggested wording" : ""}` : "Not made yet"}</span>
      </span>
      {d ? <DocActions doc={d} /> : null}
    </div>
  );

  return (
    <div className="px-8 pb-10 pt-7">
      <div className="pr-10">
        <p className="text-[13px] text-muted">{a.job.company ?? "Company not listed"}</p>
        <h2 className="mt-1 text-[22px] font-semibold leading-tight tracking-[-0.015em] selectable">{a.job.title}</h2>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <HeatMeter score={a.job.score} />
        <Select value={a.status} onChange={(e) => patch.mutate({ status: e.target.value as AppStatus })} className="w-[180px]" aria-label="Application stage">
          {APP_STATUSES.map((s) => (
            <option key={s} value={s}>
              {LABEL[s]}
            </option>
          ))}
        </Select>
        {a.job.url ? (
          <Button size="sm" variant="ghost" onClick={() => openUrl(a.job.url!)}>
            <ExternalLink /> Posting
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" onClick={() => navigate(`/jobs?id=${a.job.id}`)}>
          Job details
        </Button>
      </div>

      {a.replied_at && ["applied", "awaiting_approval", "preparing"].includes(a.status) ? (
        <div className="mt-6 rounded-[10px] bg-ok/8 p-4 ring-1 ring-inset ring-ok/25">
          <p className="flex items-center gap-2 text-[13.5px] font-semibold text-ok">
            <CornerUpLeft className="size-4" />
            {a.reply_hint === "interview"
              ? `${a.job.company ?? "The employer"} may want to interview you`
              : a.reply_hint === "offer"
                ? `${a.job.company ?? "The employer"} may be making you an offer`
                : a.reply_hint === "declined"
                  ? `${a.job.company ?? "The employer"} replied, and it may be a rejection`
                  : `${a.job.company ?? "The employer"} replied ${relativeTime(a.replied_at)}`}
          </p>
          {a.reply_subject ? <p className="mt-1 text-[13px] text-fg selectable">“{a.reply_subject}”</p> : null}
          <p className="mt-1 text-[12.5px] text-muted">
            {a.reply_hint ? "This is Huntly's guess. " : ""}Read the email in Gmail, then tell Huntly where this stands.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant={a.reply_hint === "interview" ? "primary" : "secondary"} onClick={() => patch.mutate({ status: "interviewing" })}>
              Move to Interviewing
            </Button>
            <Button size="sm" variant={a.reply_hint === "offer" ? "primary" : "secondary"} onClick={() => patch.mutate({ status: "offer" })}>
              Job offer
            </Button>
            <Button size="sm" variant={a.reply_hint === "declined" ? "primary" : "secondary"} onClick={() => patch.mutate({ status: "rejected" })}>
              Not successful
            </Button>
          </div>
        </div>
      ) : null}

      <div className="mt-8 space-y-8">
        <Step n={1} title="Tailor your documents" done={!!cv}>
          <p className="mb-2 max-w-[62ch] text-[12.5px] text-muted">
            An ATS-friendly CV built only from your profile: one column, standard headings, real text, and the skills and achievements this job asks for moved to the top.
          </p>
          <DocLine d={cv} label="CV" />
          <DocLine d={cl} label="Cover letter" />
          {cv?.meta?.ats ? <AtsPanel ats={cv.meta.ats} /> : null}
          {(cl?.meta?.warnings ?? []).map((w) => (
            <p key={w} className="mt-1 text-[12.5px] text-warn">
              {w}
            </p>
          ))}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Select value={fmt} onChange={(e) => setFmt(e.target.value as "pdf" | "docx")} className="w-[92px]" aria-label="File format">
              <option value="pdf">PDF</option>
              <option value="docx">Word</option>
            </Select>
            <Button variant={cv ? "secondary" : "primary"} onClick={() => generate.mutate()} loading={generate.isPending}>
              <Sparkles /> {cv ? "Make again" : "Make CV and letter"}
            </Button>
            {settings.data?.groq_enabled ? (
              <label className="flex items-center gap-2 text-[12.5px] text-muted">
                <Switch checked={useLlm} onCheckedChange={setUseLlm} /> Let Groq suggest wording
              </label>
            ) : null}
          </div>
        </Step>

        <Step n={2} title="Prepare the email" done={!!openApproval || !!sent}>
          <Field label="Send to" hint={a.job.apply_email ? `The posting lists ${a.job.apply_email}` : "No address in the posting. Many jobs only accept applications on their website."}>
            <div className="flex gap-2">
              <Input type="email" value={contact ?? ""} onChange={(e) => setContact(e.target.value)} placeholder="recruiter@company.com" />
              <Button onClick={() => patch.mutate({ contact_email: contact ?? "" })} disabled={(contact ?? "") === (a.contact_email ?? "")}>
                Save
              </Button>
            </div>
          </Field>
          <div className="mt-3">
            {openApproval ? (
              <Button variant="primary" onClick={() => navigate(`/approvals?id=${openApproval.id}`)}>
                <Mail /> Review the email
              </Button>
            ) : (
              <Button variant={cv ? "primary" : "secondary"} onClick={() => prepare.mutate()} loading={prepare.isPending} disabled={!cv}>
                <Mail /> Write email for my approval
              </Button>
            )}
            {!cv ? <p className="mt-2 text-[12.5px] text-faint">Make your documents first so they can be attached.</p> : null}
          </div>
        </Step>

        <Step n={3} title="Approve and send" done={!!sent}>
          {a.approvals?.length ? (
            <ul className="space-y-1">
              {a.approvals.map((x) => (
                <li key={x.id}>
                  <button onClick={() => navigate(`/approvals?id=${x.id}`)} className="flex w-full items-center gap-3 rounded-[7px] px-2 py-1.5 text-left text-[13px] hover:bg-raised">
                    {x.kind === "follow_up" ? <CornerUpLeft className="size-3.5 shrink-0 text-muted" /> : null}
                    <span className="flex-1 truncate">{x.subject}</span>
                    {x.replied_at ? <Badge tone="ok">Replied</Badge> : null}
                    <Badge tone={x.status === "sent" ? "neutral" : x.status === "failed" ? "bad" : x.status === "rejected" ? "neutral" : "act"}>{titleCase(x.status)}</Badge>
                    <span className="text-[12px] text-faint">{relativeTime(x.updated_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[12.5px] text-muted">Huntly never sends without you. Emails appear here once written.</p>
          )}
        </Step>

        <section>
          <h3 className="section-title">Notes</h3>
          <Textarea value={notes ?? ""} onChange={(e) => setNotes(e.target.value)} placeholder="Interview dates, who you spoke to, follow-ups" className="mt-2 min-h-28" />
          <div className="mt-2 flex items-center gap-3">
            <Button size="sm" disabled={notes === a.notes} onClick={() => patch.mutate({ notes: notes ?? "" })}>
              Save notes
            </Button>
            <span className="text-[12px] text-faint">
              Started {formatDateTime(a.created_at)}
              {a.applied_at ? `, sent ${formatDateTime(a.applied_at)}` : ""}
            </span>
          </div>
        </section>

        <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
          <Trash2 /> Delete application
        </Button>
      </div>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this application?"
        description="Its notes and unsent emails are removed from your history. Documents stay in your CV library."
        confirmLabel="Delete application"
        tone="danger"
        loading={del.isPending}
        onConfirm={() => del.mutate()}
      />
    </div>
  );
}

export default function Applications() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("id") ? Number(params.get("id")) : null;
  const apps = useApplications();
  const [showClosed, setShowClosed] = useState(false);
  const columns = showClosed ? [...BOARD, "rejected" as AppStatus, "withdrawn" as AppStatus] : BOARD;
  const by = useMemo(() => {
    const m = new Map<AppStatus, Application[]>();
    apps.data?.forEach((a) => m.set(a.status, [...(m.get(a.status) ?? []), a]));
    return m;
  }, [apps.data]);
  const closedCount = (by.get("rejected")?.length ?? 0) + (by.get("withdrawn")?.length ?? 0);

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Applications"
        description="Every job you're pursuing, by stage. When an employer replies, the card tells you and you choose the next stage."
        actions={
          <label className="flex items-center gap-2 text-[12.5px] text-muted">
            <Switch checked={showClosed} onCheckedChange={setShowClosed} /> Show closed ({closedCount})
          </label>
        }
      />
      {apps.isPending ? (
        <div className="flex gap-4 px-7">
          {BOARD.map((s) => (
            <Skeleton key={s} className="h-64 w-64" />
          ))}
        </div>
      ) : apps.isError ? (
        <ErrorState error={apps.error} onRetry={() => apps.refetch()} />
      ) : !apps.data.length ? (
        <EmptyState className="px-7" title="No applications yet" description="Find a job you like in Discover and choose Start application. It will show up here." />
      ) : (
        <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto px-7 pb-6">
          {columns.map((col) => {
            const list = by.get(col) ?? [];
            return (
              <div key={col} className="flex min-w-[220px] flex-1 flex-col rounded-[10px] bg-panel/60">
                <div className="flex items-center gap-2 px-3.5 pb-2 pt-3">
                  <span className={cn("text-[13px] font-semibold", col === "awaiting_approval" && "text-act")}>{LABEL[col]}</span>
                  <span className="text-[12.5px] tabular-nums text-faint">{list.length}</span>
                </div>
                <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-2 pb-2">
                  {list.map((a) => (
                    <button
                      key={a.id}
                      onClick={() => setParams({ id: String(a.id) })}
                      className={cn("block w-full rounded-[8px] bg-raised p-3 text-left ring-1 ring-inset ring-line/60 transition-colors hover:ring-line-strong", a.id === selected && "ring-2 ring-act/70")}
                    >
                      <span className="block text-[13.5px] font-medium leading-snug">{a.job.title}</span>
                      <span className="mt-0.5 block truncate text-[12.5px] text-muted">{a.job.company}</span>
                      {a.replied_at ? (
                        <span className={cn("mt-2 inline-flex items-center gap-1 text-[12px] font-medium", a.status === "applied" && a.reply_hint === "declined" ? "text-bad" : a.status === "applied" && a.reply_hint ? "text-heat" : "text-ok")}>
                          <CornerUpLeft className="size-3" />
                          {a.status !== "applied"
                            ? `Replied ${relativeTime(a.replied_at)}`
                            : a.reply_hint === "interview"
                              ? "Possible interview, open to confirm"
                              : a.reply_hint === "offer"
                                ? "Possible offer, open to confirm"
                                : a.reply_hint === "declined"
                                  ? "Possible rejection, open to confirm"
                                  : `Replied ${relativeTime(a.replied_at)}`}
                        </span>
                      ) : null}
                      <span className="mt-2.5 flex items-center justify-between">
                        <HeatMeter score={a.job.score} size="sm" />
                        <span className="text-[11.5px] text-faint">{relativeTime(a.updated_at)}</span>
                      </span>
                    </button>
                  ))}
                  {!list.length ? <p className="px-1.5 py-2 text-[12px] text-faint">Nothing here.</p> : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <Sheet open={!!selected} onOpenChange={(o) => !o && setParams({})} title="Application">
        {selected ? <ApplicationDetail key={selected} id={selected} onDeleted={() => setParams({})} /> : null}
      </Sheet>
    </div>
  );
}
