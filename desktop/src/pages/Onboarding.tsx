import { useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useState } from "react";
import { CredentialList, EncryptedNote, GmailConnect } from "@/components/Credentials";
import { CvUploadButton } from "@/components/CvImport";
import { Logo } from "@/components/Logo";
import { TagInput } from "@/components/TagInput";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/misc";
import { api, type OnboardingStatus, type Profile, type ProfileResponse } from "@/lib/api";
import { qk, useAction, useProfile } from "@/lib/queries";
import { cn } from "@/lib/utils";

const STEPS = ["How Huntly works", "Master password", "Your keys", "Gmail", "About you"];

export const split = (s: string) =>
  s
    .split(/[,\n]/)
    .map((x) => x.trim())
    .filter(Boolean);

function strength(pw: string) {
  let s = 0;
  if (pw.length >= 10) s++;
  if (pw.length >= 14) s++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++;
  if (/\d/.test(pw) || /[^A-Za-z0-9]/.test(pw)) s++;
  return Math.min(s, 4);
}

function Intro({ dataDir }: { dataDir: string }) {
  const points = [
    ["It runs on your computer.", `Jobs, files and history are kept in ${dataDir}. There is no Huntly server.`],
    ["You bring your own keys.", "Google, X and Groq keys are yours, encrypted here with your master password."],
    ["Nothing phones home.", "No analytics or crash reports. Huntly only talks to the services you set up."],
    ["You approve every email.", "Applications wait as drafts. Nothing is sent until you check it and say yes."],
    ["The code is open.", "Apache-2.0 licensed, so you can read exactly what it does."],
  ];
  return (
    <>
      <Logo size={52} className="mb-6" />
      <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.02em]">Find work without handing your data to anyone.</h1>
      <p className="mt-3 text-[14px] leading-relaxed text-muted">Huntly searches the job sources you choose, ranks every job against your profile, and drafts tailored applications for you to approve. Setup takes about five minutes.</p>
      <dl className="mt-8 space-y-4">
        {points.map(([t, d]) => (
          <div key={t} className="grid grid-cols-[200px_1fr] gap-4 text-[13.5px]">
            <dt className="font-medium">{t}</dt>
            <dd className="text-muted selectable">{d}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

function VaultStep({ status, onDone }: { status: OnboardingStatus; onDone: () => void }) {
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [keyring, setKeyring] = useState(false);
  const qc = useQueryClient();
  const create = useAction(() => api<{ warning: string | null }>("/vault/create", { method: "POST", json: { password: pw, use_keyring: keyring } }), {
    success: (r) => r.warning ?? "Master password set",
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.onboarding });
      onDone();
    },
  });
  if (status.vault_initialized)
    return (
      <>
        <h1 className="text-[26px] font-semibold tracking-[-0.02em]">Master password</h1>
        <p className="mt-4 flex items-center gap-2 text-[14px] text-ok">
          <Check className="size-4" /> Set, and Huntly is unlocked.
        </p>
      </>
    );
  const s = strength(pw);
  const mismatch = confirm.length > 0 && pw !== confirm;
  const valid = pw.length >= 10 && pw === confirm;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) create.mutate();
      }}
    >
      <h1 className="text-[26px] font-semibold tracking-[-0.02em]">Choose a master password</h1>
      <p className="mt-2 text-[14px] leading-relaxed text-muted">It locks your keys. Huntly never stores it, so if you forget it you'll need to enter your keys again. A few unrelated words make a strong, memorable password.</p>
      <div className="mt-7 space-y-4">
        <Field label="Master password" hint="At least 10 characters">
          <Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus autoComplete="new-password" className="h-10" />
          <div className="mt-1 flex gap-1" aria-hidden>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className={cn("h-1 flex-1 rounded-full", i < s ? (s <= 1 ? "bg-bad" : s <= 2 ? "bg-warn" : "bg-ok") : "bg-raised")} />
            ))}
          </div>
        </Field>
        <Field label="Type it again" error={mismatch ? "The passwords don't match" : null}>
          <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-invalid={mismatch} autoComplete="new-password" className="h-10" />
        </Field>
        <label className={cn("flex items-start gap-3 pt-1", !status.keyring_available && "opacity-55")}>
          <Switch checked={keyring} onCheckedChange={setKeyring} disabled={!status.keyring_available} className="mt-0.5" />
          <span className="text-[13.5px]">
            Unlock automatically on this computer
            <span className="mt-0.5 block text-[12.5px] leading-relaxed text-muted">
              {status.keyring_available
                ? "Keeps the unlock key in your system keychain. Handy, but anyone signed in as you could then use your keys."
                : "No system keychain found. Install GNOME Keyring or KWallet to use this."}
            </span>
          </span>
        </label>
        <Button type="submit" variant="primary" size="lg" disabled={!valid} loading={create.isPending}>
          Set master password
        </Button>
      </div>
    </form>
  );
}

function ProfileStep() {
  const profile = useProfile();
  const [form, setForm] = useState<Profile | null>(null);
  const [seen, setSeen] = useState<string | null>(null);
  // Reload the form when the profile changes underneath (for example after a CV import).
  const stamp = profile.data ? JSON.stringify(profile.data.profile) : null;
  if (profile.data && stamp !== seen) {
    setSeen(stamp);
    setForm(structuredClone(profile.data.profile));
  }
  const save = useAction(() => api<ProfileResponse>("/profile", { method: "PUT", json: form }), { success: "Profile saved", invalidate: [qk.profile] });
  if (!form) return null;
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setForm({ ...form, [k]: v });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h1 className="text-[26px] font-semibold tracking-[-0.02em]">Tell Huntly about you</h1>
      <p className="mt-2 text-[14px] leading-relaxed text-muted">Jobs are scored against this, and your CVs are built only from it. The quickest way is to import the CV you already have.</p>
      <div className="mt-5 flex items-center gap-3">
        <CvUploadButton variant="primary" label="Import from my CV" />
        <span className="text-[12.5px] text-faint">PDF or Word. Read on this computer, and you review it first.</span>
      </div>
      <div className="mt-7 grid grid-cols-2 gap-x-4 gap-y-4">
        <Field label="Full name">
          <Input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} />
        </Field>
        <Field label="Headline">
          <Input value={form.headline} onChange={(e) => set("headline", e.target.value)} placeholder="Security engineer" />
        </Field>
        <Field label="Email">
          <Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
        </Field>
        <Field label="Location">
          <Input value={form.location} onChange={(e) => set("location", e.target.value)} />
        </Field>
        <Field label="LinkedIn">
          <Input value={form.linkedin_url} onChange={(e) => set("linkedin_url", e.target.value)} placeholder="linkedin.com/in/your-name" />
        </Field>
        <Field label="GitHub (optional)">
          <Input value={form.github_url} onChange={(e) => set("github_url", e.target.value)} placeholder="github.com/your-name" />
        </Field>
        <Field label="Skills" className="col-span-2">
          <TagInput label="Skills" value={form.skills} onChange={(v) => set("skills", v)} placeholder="Python, Linux, Burp Suite" />
        </Field>
        <Field label="Roles you want" className="col-span-2">
          <TagInput label="Roles you want" value={form.target_roles} onChange={(v) => set("target_roles", v)} placeholder="Penetration tester" />
        </Field>
      </div>
      <Button type="submit" className="mt-5" loading={save.isPending}>
        Save
      </Button>
    </form>
  );
}

export default function Onboarding({ status, onFinish }: { status: OnboardingStatus; onFinish: () => void }) {
  const [step, setStep] = useState(status.vault_initialized ? 2 : 0);
  const qc = useQueryClient();
  const finish = useAction(() => api("/onboarding/complete", { method: "POST" }), {
    success: "You're set up",
    onSuccess: () => {
      onFinish();
      qc.invalidateQueries();
    },
  });
  const blocked = step === 1 && !status.vault_initialized;
  const last = step === STEPS.length - 1;

  return (
    <div className="flex h-full flex-col">
      <div className="mx-auto flex w-full max-w-[640px] items-center gap-2 px-8 pt-10">
        {STEPS.map((label, i) => (
          <div key={label} className="flex-1" title={label}>
            <div className={cn("h-[3px] rounded-full", i < step ? "bg-act" : i === step ? "bg-fg" : "bg-raised")} />
            <p className={cn("mt-2 text-[11.5px]", i === step ? "text-fg" : "text-faint")}>{label}</p>
          </div>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[640px] px-8 py-10">
          {step === 0 && <Intro dataDir={status.data_dir} />}
          {step === 1 && <VaultStep status={status} onDone={() => setStep(2)} />}
          {step === 2 && (
            <>
              <h1 className="text-[26px] font-semibold tracking-[-0.02em]">Add your keys</h1>
              <p className="mt-2 text-[14px] leading-relaxed text-muted">All optional. Add only what you'll use. You can change them later in Settings.</p>
              <EncryptedNote className="mt-5" />
              <div className="mt-3">
                <CredentialList />
              </div>
              <details className="mt-2 text-[13px] text-muted">
                <summary className="cursor-pointer text-fg">Where do I get the Google sign-in file?</summary>
                <ol className="mt-2 list-decimal space-y-1 pl-5 leading-relaxed selectable">
                  <li>Open console.cloud.google.com and create a project of your own.</li>
                  <li>In APIs and services, enable the Gmail API.</li>
                  <li>Set up the OAuth consent screen as External and add yourself as a test user.</li>
                  <li>Create credentials, choose OAuth client ID, then Desktop app.</li>
                  <li>Download the JSON file and load it above.</li>
                </ol>
              </details>
            </>
          )}
          {step === 3 && (
            <>
              <h1 className="text-[26px] font-semibold tracking-[-0.02em]">Connect Gmail</h1>
              <p className="mt-2 text-[14px] leading-relaxed text-muted">For your daily digest and for application emails you approve. You can skip this and only use job search.</p>
              <div className="mt-6">
                <GmailConnect />
              </div>
            </>
          )}
          {step === 4 && <ProfileStep />}
        </div>
      </div>
      <div className="mx-auto flex w-full max-w-[640px] items-center justify-between px-8 pb-8 pt-3">
        <Button variant="ghost" disabled={step === 0 || (step === 2 && status.vault_initialized)} onClick={() => setStep(step - 1)}>
          Back
        </Button>
        {last ? (
          <Button variant="primary" size="lg" onClick={() => finish.mutate()} loading={finish.isPending} disabled={!status.vault_initialized}>
            Start using Huntly
          </Button>
        ) : (
          <Button variant={blocked ? "secondary" : "primary"} size="lg" disabled={blocked} onClick={() => setStep(step + 1)}>
            {step === 0 ? "Get started" : step >= 2 ? "Continue" : "Next"}
          </Button>
        )}
      </div>
    </div>
  );
}
