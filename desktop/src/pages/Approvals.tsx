import { Check, CornerUpLeft, Inbox, MailCheck, Paperclip, Pencil, RefreshCw, Send, ShieldCheck, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Badge, EmptyState, ErrorState, Segmented, Skeleton } from "@/components/ui/misc";
import { api, type Approval } from "@/lib/api";
import { qk, useAction, useApproval, useApprovals, useDocuments, useGmail, useSettings } from "@/lib/queries";
import { cn, formatBytes, formatDateTime, relativeTime, titleCase } from "@/lib/utils";

const TONE: Record<Approval["status"], "neutral" | "act" | "ok" | "bad" | "warn"> = { pending: "act", approved: "warn", sent: "ok", rejected: "neutral", failed: "bad" };
const STATUS_TEXT: Record<Approval["status"], string> = { pending: "Needs review", approved: "Approved", sent: "Sent", rejected: "Rejected", failed: "Failed" };
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function Review({ id }: { id: number }) {
  const approval = useApproval(id);
  const docs = useDocuments();
  const gmail = useGmail();
  const settings = useSettings();
  const [editing, setEditing] = useState(false);
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [attachments, setAttachments] = useState<number[]>([]);
  const [checks, setChecks] = useState({ recipient: false, facts: false, files: false });
  const [confirmSend, setConfirmSend] = useState(false);
  const [now, setNow] = useState(Date.now());
  const inv = [qk.approval(id), qk.approvals, qk.applications];

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const a = approval.data;
  useEffect(() => {
    if (a) {
      setTo(a.to);
      setSubject(a.subject);
      setBody(a.body);
      setAttachments(a.attachment_ids);
      setChecks({ recipient: false, facts: false, files: false });
    }
  }, [a?.id, a?.content_hash]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = !!a && (to !== a.to || subject !== a.subject || body !== a.body || attachments.join() !== a.attachment_ids.join());
  const save = useAction(() => api<Approval>(`/approvals/${id}`, { method: "PATCH", json: { to, subject, body, attachment_ids: attachments } }), {
    invalidate: inv,
    success: "Changes saved. Approve again before sending.",
    onSuccess: () => setEditing(false),
  });
  const draft = useAction(() => api(`/approvals/${id}/draft`, { method: "POST" }), { invalidate: inv, success: "Saved to your Gmail drafts. Nothing was sent." });
  const approve = useAction(() => api(`/approvals/${id}/approve`, { method: "POST", json: { confirm: true, content_hash: a!.content_hash } }), { invalidate: inv, success: "Approved. You can send it now." });
  const reject = useAction(() => api(`/approvals/${id}/reject`, { method: "POST" }), { invalidate: inv, success: "Email rejected" });
  const send = useAction(() => api<{ message_id: string }>(`/approvals/${id}/send`, { method: "POST" }), {
    invalidate: [...inv, ["jobs"], qk.audit],
    onSuccess: () => {
      setConfirmSend(false);
      toast.success(`Sent to ${a?.to}`);
    },
  });
  const navigate = useNavigate();
  const followUp = useAction(() => api<Approval>(`/approvals/${id}/follow-up`, { method: "POST" }), {
    invalidate: [qk.approvals, qk.followUps],
    success: "Follow-up written. Review it before sending.",
    onSuccess: (f) => navigate(`/approvals?id=${f.id}`),
  });
  const skip = useAction(() => api(`/approvals/${id}/dismiss-follow-up`, { method: "POST" }), { invalidate: [qk.approval(id), qk.followUps], success: "You won't be reminded about this one" });
  const check = useAction(() => api<{ status: string; replies: number }>("/replies/check", { method: "POST" }), {
    invalidate: [qk.approval(id), qk.approvals, qk.followUps],
    success: (r) => (r.status === "needs_permission" ? "Reconnect Gmail in Settings to allow reply tracking" : r.replies ? "New reply found" : "No new replies"),
  });
  const candidates = useMemo(() => (docs.data ?? []).filter((d) => d.kind === "base_cv" || (a?.job && d.job_id === a.job.id)), [docs.data, a?.job]);

  if (approval.isPending)
    return (
      <div className="flex gap-6 p-8">
        <Skeleton className="h-[480px] flex-1" />
        <Skeleton className="h-80 w-72" />
      </div>
    );
  if (approval.isError) return <ErrorState error={approval.error} onRetry={() => approval.refetch()} />;
  if (!a) return null;

  const locked = a.status === "sent" || a.status === "rejected";
  const windowMs = (settings.data?.approval_window_minutes ?? 15) * 60000;
  const remaining = a.approved_at ? Math.max(0, new Date(a.approved_at).getTime() + windowMs - now) : 0;
  const approvedLive = a.status === "approved" && remaining > 0;
  const attached = (a.attachments ?? []).filter((d) => a.attachment_ids.includes(d.id));
  const allChecked = checks.recipient && checks.facts && checks.files;
  const mmss = `${Math.floor(remaining / 60000)}:${String(Math.floor((remaining % 60000) / 1000)).padStart(2, "0")}`;

  return (
    <div className="flex min-h-full gap-7 px-8 py-7">
      {/* The email as the recipient will see it */}
      <div className="min-w-0 flex-1">
        <div className="mb-3 flex items-center gap-3">
          <Badge tone={TONE[a.status]}>{STATUS_TEXT[a.status]}</Badge>
          {a.kind === "follow_up" ? <Badge>Follow-up</Badge> : null}
          {a.replied_at ? <Badge tone="ok">Replied</Badge> : null}
          <span className="truncate text-[13px] text-muted">
            {a.job?.title}
            {a.job?.company ? `, ${a.job.company}` : ""}
          </span>
          {!locked && !editing ? (
            <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setEditing(true)}>
              <Pencil /> Edit
            </Button>
          ) : null}
        </div>

        {editing ? (
          <div className="space-y-4 rounded-[10px] bg-panel p-5 ring-1 ring-inset ring-line">
            <Field label="To">
              <Input type="email" value={to} onChange={(e) => setTo(e.target.value)} aria-invalid={!!to && !EMAIL_RE.test(to)} />
            </Field>
            <Field label="Subject">
              <Input value={subject} onChange={(e) => setSubject(e.target.value)} />
            </Field>
            <Field label="Message">
              <Textarea value={body} onChange={(e) => setBody(e.target.value)} className="min-h-80 text-[14px]" />
            </Field>
            <Field label="Attachments">
              <div className="space-y-1">
                {candidates.map((d) => (
                  <label key={d.id} className="flex items-center gap-3 rounded-[7px] px-2 py-1.5 text-[13px] hover:bg-raised">
                    <input
                      type="checkbox"
                      checked={attachments.includes(d.id)}
                      onChange={(e) => setAttachments(e.target.checked ? [...attachments, d.id] : attachments.filter((x) => x !== d.id))}
                      className="size-4 accent-[#8fa4ff]"
                    />
                    <span className="flex-1 truncate">{d.title}</span>
                    <span className="text-[12px] text-faint">
                      {d.format.toUpperCase()}, {formatBytes(d.size)}
                    </span>
                  </label>
                ))}
                {!candidates.length ? <p className="text-[12.5px] text-faint">No documents yet.</p> : null}
              </div>
            </Field>
            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                onClick={() => {
                  setTo(a.to);
                  setSubject(a.subject);
                  setBody(a.body);
                  setAttachments(a.attachment_ids);
                  setEditing(false);
                }}
              >
                Cancel
              </Button>
              <Button variant="primary" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
                Save changes
              </Button>
            </div>
          </div>
        ) : (
          <div className="rounded-[6px] bg-paper text-paper-ink shadow-[0_1px_0_rgba(255,255,255,0.04),0_18px_40px_-18px_rgba(0,0,0,0.6)]">
            <dl className="grid grid-cols-[72px_1fr] gap-y-1.5 border-b border-[#e7e4dc] px-8 py-5 text-[13px]">
              <dt className="text-[#7a7f8a]">From</dt>
              <dd>{gmail.data?.email ?? "Your Gmail account"}</dd>
              <dt className="text-[#7a7f8a]">To</dt>
              <dd className={cn("selectable", !a.to && "text-[#b4232c]")}>{a.to || "No recipient yet"}</dd>
              <dt className="text-[#7a7f8a]">Subject</dt>
              <dd className="font-semibold selectable">{a.subject}</dd>
            </dl>
            <div className="max-w-[68ch] whitespace-pre-wrap px-8 py-6 font-[Georgia,serif] text-[15px] leading-[1.7] selectable">{a.body}</div>
            {attached.length ? (
              <div className="flex flex-wrap gap-2 border-t border-[#e7e4dc] px-8 py-4">
                {attached.map((d) => (
                  <span key={d.id} className="inline-flex items-center gap-2 rounded-[6px] bg-[#efece5] px-2.5 py-1.5 text-[12.5px]">
                    <Paperclip className="size-3.5 text-[#7a7f8a]" />
                    {d.title}
                    <span className="text-[#7a7f8a]">{formatBytes(d.size)}</span>
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* Decision panel */}
      <aside className="w-[290px] shrink-0">
        <div className="sticky top-0 space-y-5">
          {a.status === "sent" ? (
            <>
              <div className="rounded-[10px] bg-panel p-4 text-[13px] ring-1 ring-inset ring-line">
                <p className="flex items-center gap-2 font-semibold">
                  <Check className="size-4 text-ok" /> Sent {formatDateTime(a.sent_at)}
                </p>
                {a.replied_at ? (
                  <p className="mt-2 flex items-center gap-2 font-medium text-ok">
                    <CornerUpLeft className="size-4" /> They replied {relativeTime(a.replied_at)}. Open Gmail to read it.
                  </p>
                ) : (
                  <p className="mt-2 text-muted">
                    No reply yet{a.reply_checked_at ? `, last checked ${relativeTime(a.reply_checked_at)}` : ""}.
                  </p>
                )}
                {!a.replied_at ? (
                  <Button size="sm" variant="ghost" className="mt-2 -ml-2" onClick={() => check.mutate()} loading={check.isPending}>
                    <RefreshCw /> Check for a reply
                  </Button>
                ) : null}
              </div>
              {!a.replied_at && !a.follow_up_dismissed ? (
                <div className="rounded-[10px] bg-panel p-4 ring-1 ring-inset ring-line">
                  <p className="text-[13.5px] font-semibold">Follow up</p>
                  <p className="mt-1 text-[12.5px] leading-relaxed text-muted">
                    A short, polite reply in the same thread. You'll review and approve it like any other email.
                  </p>
                  <Button className="mt-3 w-full" variant={settings.data && a.sent_at && now - new Date(a.sent_at).getTime() > settings.data.follow_up_after_days * 86400000 ? "primary" : "secondary"} onClick={() => followUp.mutate()} loading={followUp.isPending}>
                    <CornerUpLeft /> Write a follow-up
                  </Button>
                  <Button size="sm" variant="ghost" className="mt-1 w-full" onClick={() => skip.mutate()}>
                    Don't remind me
                  </Button>
                </div>
              ) : null}
            </>
          ) : a.status === "rejected" ? (
            <p className="text-[13px] text-muted">You rejected this email. Write a new one from the application if you change your mind.</p>
          ) : (
            <>
              {a.status === "failed" ? <p className="rounded-[8px] bg-bad/8 p-3 text-[12.5px] text-bad ring-1 ring-inset ring-bad/25 selectable">{a.error}</p> : null}
              {approvedLive ? (
                <div className="rounded-[10px] bg-panel p-4 ring-1 ring-inset ring-act/40">
                  <p className="flex items-center gap-2 text-[13.5px] font-semibold">
                    <ShieldCheck className="size-4 text-act" /> Approved
                  </p>
                  <p className="mt-1 text-[12.5px] text-muted">
                    Send within <span className="tabular-nums text-fg">{mmss}</span> or approve again. Any edit cancels the approval.
                  </p>
                  <Button variant="primary" size="lg" className="mt-4 w-full" disabled={!gmail.data?.connected || editing} onClick={() => setConfirmSend(true)}>
                    <Send /> Send email
                  </Button>
                  {!gmail.data?.connected ? <p className="mt-2 text-[12px] text-warn">Connect Gmail in Settings to send.</p> : null}
                </div>
              ) : (
                <div className="rounded-[10px] bg-panel p-4 ring-1 ring-inset ring-line">
                  <p className="text-[13.5px] font-semibold">Before you approve</p>
                  <div className="mt-3 space-y-2.5">
                    {(
                      [
                        ["recipient", `It's going to the right person (${a.to || "no recipient"})`],
                        ["facts", "Everything it says about me is true"],
                        ["files", `The right files are attached (${attached.length})`],
                      ] as const
                    ).map(([k, label]) => (
                      <label key={k} className="flex items-start gap-2.5 text-[13px]">
                        <input type="checkbox" checked={checks[k]} onChange={(e) => setChecks({ ...checks, [k]: e.target.checked })} disabled={editing} className="mt-0.5 size-4 accent-[#8fa4ff]" />
                        <span className={checks[k] ? "text-fg" : "text-muted"}>{label}</span>
                      </label>
                    ))}
                  </div>
                  <Button variant="primary" size="lg" className="mt-4 w-full" disabled={!allChecked || editing || !EMAIL_RE.test(a.to)} loading={approve.isPending} onClick={() => approve.mutate()}>
                    <MailCheck /> Approve this email
                  </Button>
                  {a.status === "approved" ? <p className="mt-2 text-[12px] text-warn">The last approval expired.</p> : null}
                </div>
              )}
              <div className="space-y-1">
                <Button variant="ghost" className="w-full justify-start" onClick={() => draft.mutate()} loading={draft.isPending} disabled={editing || !gmail.data?.connected}>
                  <Inbox /> Save to Gmail drafts
                </Button>
                <Button variant="ghost" className="w-full justify-start text-bad hover:text-bad" onClick={() => reject.mutate()} loading={reject.isPending}>
                  <X /> Reject
                </Button>
              </div>
              {a.gmail_draft_id ? <p className="text-[12px] text-faint">A copy is in your Gmail drafts.</p> : null}
            </>
          )}
          <p className="text-[12px] leading-relaxed text-faint">Huntly sends only after your approval, and only the exact version you approved. Every step is recorded in the audit log.</p>
        </div>
      </aside>

      <ConfirmDialog
        open={confirmSend}
        onOpenChange={setConfirmSend}
        title="Send this application?"
        description={`From ${gmail.data?.email ?? "your Gmail"} to ${a.to}, with ${attached.length} attachment${attached.length === 1 ? "" : "s"}. You can't unsend it.`}
        confirmLabel="Send email"
        loading={send.isPending}
        onConfirm={() => send.mutate()}
      />
    </div>
  );
}

type Tab = "open" | "sent" | "rejected" | "all";

export default function Approvals() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("id") ? Number(params.get("id")) : null;
  const approvals = useApprovals();
  const [tab, setTab] = useState<Tab>("open");
  const list = (approvals.data ?? []).filter((a) => (tab === "all" ? true : tab === "open" ? ["pending", "approved", "failed"].includes(a.status) : a.status === tab));

  useEffect(() => {
    if (!selected && list[0]) setParams({ id: String(list[0].id) }, { replace: true });
  }, [selected, list, setParams]);

  return (
    <div className="flex h-full">
      <div className="flex w-[320px] shrink-0 flex-col border-r border-line/70">
        <div className="px-5 pb-3 pt-6">
          <h1 className="page-title">Approvals</h1>
          <p className="mt-1 text-[12.5px] text-muted">Application emails wait here until you approve them.</p>
          <Segmented
            className="mt-4"
            value={tab}
            onChange={setTab}
            options={[
              { value: "open", label: "To review" },
              { value: "sent", label: "Sent" },
              { value: "rejected", label: "Rejected" },
              { value: "all", label: "All" },
            ]}
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto pb-3">
          {approvals.isPending ? (
            <div className="space-y-2 px-5">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : approvals.isError ? (
            <ErrorState error={approvals.error} onRetry={() => approvals.refetch()} />
          ) : list.length ? (
            list.map((a) => (
              <button
                key={a.id}
                onClick={() => setParams({ id: String(a.id) })}
                className={cn("relative block w-full px-5 py-3 text-left", a.id === selected ? "bg-raised" : "hover:bg-panel")}
              >
                {a.id === selected ? <span className="absolute inset-y-2 left-0 w-[3px] rounded-r bg-act" /> : null}
                <span className="flex items-center gap-2">
                  <span className="flex-1 truncate text-[13.5px] font-medium">{a.job?.title ?? a.subject}</span>
                  <Badge tone={TONE[a.status]}>{STATUS_TEXT[a.status]}</Badge>
                </span>
                <span className="mt-0.5 block truncate text-[12.5px] text-muted">
                  {a.kind === "follow_up" ? "Follow-up to " : a.to ? "To " : ""}
                  {a.to || "No recipient yet"}
                  {a.replied_at ? <span className="text-ok">, replied</span> : null}
                </span>
                <span className="mt-0.5 block text-[11.5px] text-faint">{relativeTime(a.updated_at)}</span>
              </button>
            ))
          ) : (
            <EmptyState title={tab === "open" ? "Nothing to review" : `No ${titleCase(tab).toLowerCase()} emails`} description="Emails you write from an application appear here." />
          )}
        </div>
      </div>
      <div className="min-w-0 flex-1 overflow-y-auto">{selected ? <Review key={selected} id={selected} /> : <EmptyState className="h-full" icon={MailCheck} title="No email selected" />}</div>
    </div>
  );
}
