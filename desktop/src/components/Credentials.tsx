import { Check, Loader2, Lock, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type Credential } from "@/lib/api";
import { qk, useAction, useCredentials, useGmail } from "@/lib/queries";
import { cn, relativeTime } from "@/lib/utils";
import { Button } from "./ui/button";
import { Input, Textarea } from "./ui/input";
import { Badge } from "./ui/misc";

const EDITABLE = ["google_oauth_client", "groq_api_key"];
const FRIENDLY: Record<string, { name: string; use: string }> = {
  google_oauth_client: { name: "Google sign-in file", use: "Lets Huntly ask Google for access to your Gmail. Create a “Desktop app” OAuth client in your own Google Cloud project and load the JSON file it gives you." },
  groq_api_key: { name: "Groq API key", use: "Optional. Lets Groq add fit notes to jobs and suggest cover-letter wording." },
};

export function EncryptedNote({ className }: { className?: string }) {
  return (
    <p className={cn("flex gap-2.5 text-[12.5px] leading-relaxed text-muted", className)}>
      <Lock className="mt-0.5 size-3.5 shrink-0 text-act" />
      <span>
        Each key is encrypted (AES-256-GCM) with a key made from your master password, and stored only on this computer. Huntly's maintainers never receive it and cannot decrypt it.
      </span>
    </p>
  );
}

function CredentialRow({ c }: { c: Credential }) {
  const [value, setValue] = useState("");
  const [editing, setEditing] = useState(!c.configured);
  const fileRef = useRef<HTMLInputElement>(null);
  const f = FRIENDLY[c.name] ?? { name: c.label, use: c.help };
  const save = useAction(() => api(`/credentials/${c.name}`, { method: "PUT", json: { value } }), {
    success: `${f.name} saved and encrypted`,
    invalidate: [qk.credentials, qk.onboarding, qk.gmail],
    onSuccess: () => {
      setValue("");
      setEditing(false);
    },
  });
  const remove = useAction(() => api(`/credentials/${c.name}`, { method: "DELETE" }), { success: `${f.name} removed`, invalidate: [qk.credentials, qk.onboarding, qk.gmail] });
  const isJson = c.name === "google_oauth_client";
  useEffect(() => setEditing(!c.configured), [c.configured]);

  return (
    <div className="py-4">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[13.5px] font-medium">{f.name}</span>
            {c.configured ? (
              <Badge tone="ok">
                <Lock /> Saved
              </Badge>
            ) : null}
          </div>
          <p className="mt-0.5 max-w-[62ch] text-[12.5px] leading-relaxed text-muted">{f.use}</p>
          {c.configured && c.updated_at ? <p className="mt-0.5 text-[12px] text-faint">Updated {relativeTime(c.updated_at)}</p> : null}
        </div>
        {c.configured && !editing ? (
          <div className="flex gap-1">
            <Button size="sm" onClick={() => setEditing(true)}>
              Replace
            </Button>
            <Button size="icon-sm" variant="ghost" aria-label={`Remove ${f.name}`} onClick={() => remove.mutate()} loading={remove.isPending}>
              <Trash2 />
            </Button>
          </div>
        ) : null}
      </div>
      {editing ? (
        <form
          className="mt-3 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (value.trim()) save.mutate();
          }}
        >
          {isJson ? (
            <>
              <Textarea value={value} onChange={(e) => setValue(e.target.value)} placeholder="Paste the JSON, or load the file" className="min-h-20 font-mono text-[12px]" spellCheck={false} autoComplete="off" aria-label={f.name} />
              <input
                ref={fileRef}
                type="file"
                accept="application/json,.json"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (file && file.size < 20000) setValue(await file.text());
                }}
              />
            </>
          ) : (
            <Input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Paste here" autoComplete="off" spellCheck={false} aria-label={f.name} />
          )}
          <div className="flex gap-2">
            <Button type="submit" variant="primary" size="sm" disabled={!value.trim()} loading={save.isPending}>
              Encrypt and save
            </Button>
            {isJson ? (
              <Button type="button" size="sm" onClick={() => fileRef.current?.click()}>
                <Upload /> Load file
              </Button>
            ) : null}
            {c.configured ? (
              <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            ) : null}
          </div>
        </form>
      ) : null}
    </div>
  );
}

export function CredentialList() {
  const creds = useCredentials();
  if (creds.isPending) return <Loader2 className="size-4 animate-spin text-muted" />;
  return (
    <div className="divide-y divide-line/60">
      {(creds.data ?? [])
        .filter((c) => EDITABLE.includes(c.name))
        .map((c) => (
          <CredentialRow key={c.name} c={c} />
        ))}
    </div>
  );
}

export function GmailConnect() {
  const [polling, setPolling] = useState(false);
  const gmail = useGmail(polling);
  const connect = useAction(() => api("/gmail/connect", { method: "POST" }), {
    success: "Finish signing in with Google in your browser",
    invalidate: [qk.gmail],
    onSuccess: () => setPolling(true),
  });
  const disconnect = useAction(() => api("/gmail/disconnect", { method: "POST" }), { success: "Gmail disconnected", invalidate: [qk.gmail, qk.credentials] });
  const test = useAction(() => api<{ email: string }>("/gmail/test", { method: "POST" }), { success: (r) => `Connected as ${r.email}`, invalidate: [qk.gmail] });
  const g = gmail.data;
  useEffect(() => {
    if (polling && g && !g.flow_running) setPolling(false);
  }, [polling, g]);

  return (
    <div className="rounded-[10px] bg-panel p-4 ring-1 ring-inset ring-line/70">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-[14px] font-semibold">
            Gmail
            {g?.connected ? (
              <Badge tone="ok">
                <Check /> {g.email ?? "Connected"}
              </Badge>
            ) : g?.flow_running ? (
              <Badge tone="act">
                <Loader2 className="animate-spin" /> Waiting for Google
              </Badge>
            ) : null}
          </p>
          <p className="mt-1 max-w-[62ch] text-[12.5px] leading-relaxed text-muted">
            Huntly asks Google for two permissions: write drafts and send the emails you approve, and see who sent each message in your application threads so it can notice replies. It cannot read what any email says. The sign-in happens in your browser.
          </p>
          {g?.flow_error ? (
            <p className="mt-1.5 text-[12.5px] text-bad selectable">
              {g.flow_error}
              {/access_denied|403/i.test(g.flow_error) ? (
                <span className="mt-1 block text-muted">
                  Google blocked the sign-in because your address isn't a test user of your OAuth app. In Google Cloud Console, open Google Auth Platform → Audience, add your Gmail address under Test users (or click Publish app), then connect again.
                </span>
              ) : null}
            </p>
          ) : null}
          {g && !g.client_configured ? <p className="mt-1.5 text-[12.5px] text-warn">Add your Google sign-in file below first.</p> : null}
          {g?.connected && g.reply_tracking_permission === false ? (
            <p className="mt-1.5 text-[12.5px] text-warn">Connected before reply tracking existed. Disconnect and connect again to allow it.</p>
          ) : null}
        </div>
        <div className="flex shrink-0 gap-1">
          {g?.connected ? (
            <>
              <Button size="sm" onClick={() => test.mutate()} loading={test.isPending}>
                Check connection
              </Button>
              <Button size="sm" variant="ghost" onClick={() => disconnect.mutate()}>
                Disconnect
              </Button>
            </>
          ) : (
            <Button variant="primary" disabled={!g?.client_configured || g?.flow_running} loading={connect.isPending || g?.flow_running} onClick={() => connect.mutate()}>
              Connect Gmail
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
