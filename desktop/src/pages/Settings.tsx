import { useQueryClient } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { useEffect, useState } from "react";
import { CredentialList, EncryptedNote, GmailConnect } from "@/components/Credentials";
import { useUpdater } from "@/components/Updater";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Badge, Skeleton, Switch } from "@/components/ui/misc";
import { api, type Settings } from "@/lib/api";
import { qk, useAction, useAudit, useCredentials, useGmail, useHealth, useOnboarding, useSettings } from "@/lib/queries";
import { cn, formatDateTime } from "@/lib/utils";

const SECTIONS = [
  { id: "search", label: "Search and digest" },
  { id: "accounts", label: "Accounts and keys" },
  { id: "ai", label: "AI assistance" },
  { id: "security", label: "Security" },
  { id: "privacy", label: "Privacy" },
  { id: "updates", label: "Updates" },
  { id: "audit", label: "Activity log" },
] as const;
type SectionId = (typeof SECTIONS)[number]["id"];

function Row({ title, description, children }: { title: string; description?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-8 py-4">
      <div className="min-w-0">
        <p className="text-[13.5px]">{title}</p>
        {description ? <p className="mt-0.5 max-w-[58ch] text-[12.5px] leading-relaxed text-muted">{description}</p> : null}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h3 className="section-title">{title}</h3>
      <div className="mt-1 divide-y divide-line/60">{children}</div>
    </section>
  );
}

function useSettingsForm() {
  const settings = useSettings();
  const [s, setS] = useState<Settings | null>(null);
  useEffect(() => {
    if (settings.data) setS(settings.data);
  }, [settings.data]);
  const save = useAction(
    () =>
      api("/settings", {
        method: "PUT",
        json: {
          collection_enabled: s!.collection_enabled,
          collection_interval_minutes: Number(s!.collection_interval_minutes),
          digest_enabled: s!.digest_enabled,
          digest_time: s!.digest_time,
          digest_min_score: Number(s!.digest_min_score),
          groq_enabled: s!.groq_enabled,
          groq_model: s!.groq_model,
          approval_window_minutes: Number(s!.approval_window_minutes),
          reply_tracking_enabled: s!.reply_tracking_enabled,
          follow_up_after_days: Number(s!.follow_up_after_days),
          reply_body_analysis: s!.reply_body_analysis,
          auto_update: s!.auto_update,
        },
      }),
    { success: "Settings saved", invalidate: [qk.settings, qk.scheduler, qk.health] },
  );
  const dirty = !!s && JSON.stringify(s) !== JSON.stringify(settings.data);
  return { s, setS, save, dirty, reset: () => setS(settings.data ?? null) };
}

function SaveBar({ dirty, save, reset }: { dirty: boolean; save: ReturnType<typeof useSettingsForm>["save"]; reset: () => void }) {
  if (!dirty) return null;
  return (
    <div className="sticky bottom-4 mt-2 flex items-center gap-2 rounded-[10px] bg-raised px-4 py-2.5 ring-1 ring-line-strong">
      <span className="mr-auto text-[13px] text-muted">You have unsaved changes</span>
      <Button variant="ghost" onClick={reset}>
        Discard
      </Button>
      <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
        Save settings
      </Button>
    </div>
  );
}

function SearchSettings() {
  const { s, setS, save, dirty, reset } = useSettingsForm();
  const gmail = useGmail();
  const rescore = useAction(() => api<{ rescored: number }>("/jobs/rescore", { method: "POST" }), { success: (r) => `Rescored ${r.rescored} jobs`, invalidate: [["jobs"]] });
  const preview = useAction(() => api<{ subject: string; text: string }>("/digest/preview"), {});
  if (!s) return <Skeleton className="h-80" />;
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setS({ ...s, [k]: v });
  return (
    <>
      <Group title="Automatic search">
        <Row title="Search for new jobs automatically" description="Runs while Huntly is open. Times follow Africa/Lagos.">
          <Switch checked={s.collection_enabled} onCheckedChange={(v) => set("collection_enabled", v)} />
        </Row>
        <Row title="How often" description="Minutes between searches, from 15 to 1440">
          <Input type="number" min={15} max={1440} value={s.collection_interval_minutes} onChange={(e) => set("collection_interval_minutes", Number(e.target.value))} className="w-24" />
        </Row>
        <Row title="Rescore every job" description="Use after changing your profile a lot">
          <Button size="sm" onClick={() => rescore.mutate()} loading={rescore.isPending}>
            Rescore
          </Button>
        </Row>
      </Group>
      <Group title="Daily digest">
        <Row title="Email me a daily digest" description="Sent from your Gmail to your own address, never to anyone else">
          <Switch checked={s.digest_enabled} onCheckedChange={(v) => set("digest_enabled", v)} />
        </Row>
        <Row title="Send at" description="Africa/Lagos time">
          <Input type="time" value={s.digest_time} onChange={(e) => set("digest_time", e.target.value)} className="w-28" />
        </Row>
        <Row title="Only include matches of at least">
          <Input type="number" min={0} max={100} value={s.digest_min_score} onChange={(e) => set("digest_min_score", Number(e.target.value))} className="w-24" />
        </Row>
        <Row title="See the next digest">
          <Button size="sm" onClick={() => preview.mutate()} loading={preview.isPending}>
            Preview
          </Button>
        </Row>
      </Group>
      <Group title="Replies and follow-ups">
        <Row title="Watch for replies" description="Every two hours, Huntly checks who has written in the Gmail threads of applications you sent. It reads senders only, never message content.">
          <Switch checked={s.reply_tracking_enabled} onCheckedChange={(v) => set("reply_tracking_enabled", v)} />
        </Row>
        <Row
          title="Read replies to sort them (optional)"
          description={
            <>
              Huntly opens only replies in your application threads and checks them on this computer for words like “interview”, “unfortunately” or “offer”, then suggests the stage. The text is never
              saved or sent anywhere. Needs read access to Gmail, so you'll be asked to reconnect.
              {s.reply_body_analysis && gmail.data?.connected && gmail.data.reply_reading_permission === false ? (
                <span className="mt-1 block text-warn">Saved, but Gmail hasn't granted read access yet. In Accounts and keys, disconnect Gmail and connect again.</span>
              ) : null}
            </>
          }
        >
          <Switch checked={s.reply_body_analysis} onCheckedChange={(v) => set("reply_body_analysis", v)} />
        </Row>
        <Row title="Suggest a follow-up after" description="Days without a reply, from 2 to 60">
          <Input type="number" min={2} max={60} value={s.follow_up_after_days} onChange={(e) => set("follow_up_after_days", Number(e.target.value))} className="w-24" />
        </Row>
      </Group>
      <Group title="Sending">
        <Row title="Approval expires after" description="Minutes you have to send an approved email before approving again (1 to 120)">
          <Input type="number" min={1} max={120} value={s.approval_window_minutes} onChange={(e) => set("approval_window_minutes", Number(e.target.value))} className="w-24" />
        </Row>
      </Group>
      <SaveBar dirty={dirty} save={save} reset={reset} />
      <Dialog open={!!preview.data} onOpenChange={(o) => !o && preview.reset()}>
        {preview.data ? (
          <DialogContent title={preview.data.subject} className="w-[min(720px,92vw)]">
            <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-muted selectable">{preview.data.text}</pre>
          </DialogContent>
        ) : null}
      </Dialog>
    </>
  );
}

function AiSettings() {
  const { s, setS, save, dirty, reset } = useSettingsForm();
  const creds = useCredentials();
  if (!s) return <Skeleton className="h-40" />;
  const key = creds.data?.find((c) => c.name === "groq_api_key")?.configured;
  return (
    <>
      <p className="mb-4 max-w-[64ch] text-[13px] leading-relaxed text-muted">
        When on, job text is sent to Groq, marked as untrusted, so it can add a short fit note and suggest cover-letter wording. Suggestions that mention anything not in your profile are thrown away.
      </p>
      <Group title="Groq">
        <Row title="Use Groq" description={key ? "Your key is saved and encrypted." : "Add your Groq API key in Accounts and keys first."}>
          <Switch checked={s.groq_enabled} disabled={!key} onCheckedChange={(v) => setS({ ...s, groq_enabled: v })} />
        </Row>
        <Row title="Model">
          <Input value={s.groq_model} onChange={(e) => setS({ ...s, groq_model: e.target.value })} className="w-72" />
        </Row>
      </Group>
      <SaveBar dirty={dirty} save={save} reset={reset} />
    </>
  );
}

function Security() {
  const ob = useOnboarding();
  const qc = useQueryClient();
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const change = useAction(() => api("/vault/change-password", { method: "POST", json: { old_password: oldPw, new_password: newPw } }), {
    success: "Master password changed",
    onSuccess: () => {
      setOldPw("");
      setNewPw("");
      setConfirm("");
    },
  });
  const keyring = useAction((enabled: boolean) => api("/vault/keyring", { method: "POST", json: { enabled } }), { success: "Saved", invalidate: [qk.onboarding] });
  const lock = useAction(() => api("/vault/lock", { method: "POST" }), { onSuccess: () => qc.invalidateQueries() });
  return (
    <>
      <EncryptedNote className="mb-6" />
      <Group title="Your vault">
        <Row title="Unlock automatically on this computer" description={ob.data?.keyring_available ? "Keeps the unlock key in your system keychain" : "No system keychain found"}>
          <Switch checked={!!ob.data?.keyring_enabled} disabled={!ob.data?.keyring_available || keyring.isPending} onCheckedChange={(v) => keyring.mutate(v)} />
        </Row>
        <Row title="Lock Huntly now" description="Forgets the key until you enter your password. Searches that need keys pause.">
          <Button size="sm" onClick={() => lock.mutate()}>
            <Lock /> Lock
          </Button>
        </Row>
      </Group>
      <Group title="Change master password">
        <form
          className="grid grid-cols-3 gap-3 py-4"
          onSubmit={(e) => {
            e.preventDefault();
            change.mutate();
          }}
        >
          <Field label="Current password">
            <Input type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} autoComplete="current-password" />
          </Field>
          <Field label="New password">
            <Input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} autoComplete="new-password" />
          </Field>
          <Field label="New password again" error={confirm && confirm !== newPw ? "Doesn't match" : null}>
            <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
          </Field>
          <div className="col-span-3">
            <Button type="submit" disabled={!oldPw || newPw.length < 10 || newPw !== confirm} loading={change.isPending}>
              Change password
            </Button>
          </div>
        </form>
      </Group>
    </>
  );
}

function Privacy() {
  const health = useHealth();
  const facts = [
    ["Your data", <>Everything is in <code className="font-mono text-[12px] text-fg selectable">{health.data?.data_dir}</code>. Delete that folder to erase it all.</>],
    ["Telemetry", "None. No analytics or crash reports. The only call Huntly makes on its own is the update check to GitHub, which you can turn off under Updates."],
    ["The app's local connection", "Listens only on this computer (127.0.0.1) and needs a new secret token each launch."],
    ["Who Huntly talks to", "Only the job sources you add, Google for Gmail, X and Groq, using your own keys. Private and local network addresses are blocked."],
    ["Job text", "Treated as untrusted. Postings that try to instruct AI tools are flagged and ignored."],
  ] as const;
  return (
    <>
      <dl className="divide-y divide-line/60">
        {facts.map(([k, v]) => (
          <div key={k} className="grid grid-cols-[220px_1fr] gap-6 py-4 text-[13.5px]">
            <dt className="font-medium">{k}</dt>
            <dd className="leading-relaxed text-muted">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-6 text-[12.5px] text-faint">
        Huntly {health.data?.version}, Apache-2.0. Database {health.data?.database}. Timezone {health.data?.timezone}.
      </p>
    </>
  );
}

function Updates() {
  const { s, setS, save, dirty, reset } = useSettingsForm();
  const health = useHealth();
  const { state, check, restart } = useUpdater();
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  if (!s) return <Skeleton className="h-40" />;
  return (
    <>
      <Group title="Automatic updates">
        <Row
          title="Download and install updates automatically"
          description="Like a messaging app: new versions download quietly in the background and you choose when to restart. Updates come from the project's GitHub releases and are verified with the maintainers' signing key before installing. No personal data is sent."
        >
          <Switch checked={s.auto_update} onCheckedChange={(v) => setS({ ...s, auto_update: v })} />
        </Row>
        <Row title={`You have Huntly ${health.data?.version ?? ""}`} description={result ?? (state.kind === "downloading" ? `Downloading ${state.version}${state.progress != null ? `, ${state.progress}%` : ""}` : state.kind === "error" ? state.message : undefined)}>
          {state.kind === "ready" ? (
            <Button size="sm" variant="primary" onClick={() => restart()}>
              Restart to update to {state.version}
            </Button>
          ) : (
            <Button
              size="sm"
              loading={checking || state.kind === "downloading"}
              onClick={async () => {
                setChecking(true);
                setResult(null);
                const v = await check(true);
                setChecking(false);
                if (!v) setResult("You're on the latest version.");
              }}
            >
              Check for updates
            </Button>
          )}
        </Row>
      </Group>
      <SaveBar dirty={dirty} save={save} reset={reset} />
    </>
  );
}

function AuditLog() {
  const audit = useAudit();
  const nice = (a: string) => a.replace(/[._]/g, " ");
  return (
    <>
      <p className="mb-4 text-[13px] text-muted">Every approval, send and status change, recorded only on this computer.</p>
      <div className="divide-y divide-line/60">
        {(audit.data ?? []).map((a) => (
          <div key={a.id} className="grid grid-cols-[160px_90px_1fr] items-baseline gap-4 py-2.5 text-[13px]">
            <span className="text-[12.5px] text-muted">{formatDateTime(a.ts)}</span>
            <Badge className="justify-self-start">{a.actor === "user" ? "You" : a.actor === "scheduler" ? "Schedule" : "Huntly"}</Badge>
            <span className="min-w-0">
              <span className="capitalize">{nice(a.action)}</span>
              {Object.keys(a.detail).length ? <span className="ml-2 truncate text-[12px] text-faint selectable">{Object.entries(a.detail).map(([k, v]) => `${k} ${String(v)}`).join(", ")}</span> : null}
            </span>
          </div>
        ))}
      </div>
      {audit.data && !audit.data.length ? <p className="py-6 text-[13px] text-muted">Nothing recorded yet.</p> : null}
    </>
  );
}

export default function SettingsPage() {
  const [section, setSection] = useState<SectionId>("search");
  return (
    <div className="flex h-full">
      <nav className="w-[232px] shrink-0 border-r border-line/70 px-4 pt-6" aria-label="Settings sections">
        <h1 className="page-title px-2">Settings</h1>
        <ul className="mt-5 space-y-0.5">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => setSection(s.id)}
                className={cn("w-full rounded-[7px] px-2 py-1.5 text-left text-[13px]", section === s.id ? "bg-raised text-fg" : "text-muted hover:bg-panel hover:text-fg")}
              >
                {s.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="px-9 py-7">
          <h2 className="mb-5 text-[18px] font-semibold tracking-tight">{SECTIONS.find((s) => s.id === section)?.label}</h2>
          {section === "search" && <SearchSettings />}
          {section === "accounts" && (
            <div className="space-y-5">
              <GmailConnect />
              <EncryptedNote />
              <CredentialList />
            </div>
          )}
          {section === "ai" && <AiSettings />}
          {section === "security" && <Security />}
          {section === "privacy" && <Privacy />}
          {section === "updates" && <Updates />}
          {section === "audit" && <AuditLog />}
        </div>
      </div>
    </div>
  );
}
