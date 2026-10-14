import { FileUp } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { api, type Doc, type ParsedCv, type Profile, type ProfileResponse } from "@/lib/api";
import { qk, useAction, useProfile } from "@/lib/queries";
import { Button } from "./ui/button";
import { Dialog, DialogContent } from "./ui/dialog";
import { Segmented } from "./ui/misc";

const LABELS: Partial<Record<keyof Profile, string>> = {
  full_name: "Name",
  headline: "Headline",
  email: "Email",
  phone: "Phone",
  location: "Location",
  linkedin_url: "LinkedIn",
  github_url: "GitHub",
  portfolio_url: "Website",
  links: "Other links",
  summary: "Summary",
  skills: "Skills",
  experience: "Experience",
  education: "Education",
  projects: "Projects",
  certifications: "Certifications",
  languages: "Languages",
};

function preview(key: keyof Profile, value: unknown): string {
  if (Array.isArray(value)) {
    if (key === "experience") return (value as Profile["experience"]).map((e) => [e.title, e.company].filter(Boolean).join(" at ") + (e.highlights.length ? ` (${e.highlights.length} ${e.highlights.length === 1 ? "point" : "points"})` : "")).join("; ");
    if (key === "education") return (value as Profile["education"]).map((e) => [e.qualification, e.institution].filter(Boolean).join(", ")).join("; ");
    if (key === "projects") return (value as Profile["projects"]).map((p) => p.name).join(", ");
    return (value as string[]).join(", ");
  }
  return String(value ?? "");
}

function isEmpty(v: unknown) {
  return v == null || v === "" || (Array.isArray(v) && v.length === 0);
}

/** Review what was read from a CV and choose what to copy into the profile. */
export function CvImportDialog({ doc, parsed, onClose }: { doc: Doc; parsed: ParsedCv; onClose: () => void }) {
  const profile = useProfile();
  const current = profile.data?.profile;
  const keys = useMemo(() => (Object.keys(LABELS) as (keyof Profile)[]).filter((k) => !isEmpty(parsed.fields[k])), [parsed]);
  const [mode, setMode] = useState<"fill" | "replace">("fill");
  const [picked, setPicked] = useState<Set<keyof Profile>>(() => new Set(keys));

  const merged = useMemo(() => {
    if (!current) return null;
    const next: Profile = structuredClone(current);
    for (const k of picked) {
      const v = parsed.fields[k];
      if (isEmpty(v)) continue;
      if (mode === "replace" || isEmpty(current[k])) (next as Record<string, unknown>)[k] = v;
    }
    return next;
  }, [current, picked, mode, parsed]);

  const save = useAction(() => api<ProfileResponse>("/profile", { method: "PUT", json: merged }), {
    success: "Profile updated from your CV",
    invalidate: [qk.profile, ["jobs"]],
    onSuccess: onClose,
  });

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title={`Fill your profile from ${doc.title}`}
        description="Read on this computer. Check each item, then choose how to apply it. Nothing changes until you save."
        className="w-[min(720px,94vw)]"
        footer={
          <>
            <Segmented
              className="mr-auto"
              value={mode}
              onChange={setMode}
              options={[
                { value: "fill", label: "Only fill empty fields" },
                { value: "replace", label: "Replace existing" },
              ]}
            />
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="primary" disabled={!picked.size || !merged} loading={save.isPending} onClick={() => save.mutate()}>
              Save to profile
            </Button>
          </>
        }
      >
        {parsed.warnings.map((w) => (
          <p key={w} className="mb-2 text-[12.5px] text-warn">
            {w}
          </p>
        ))}
        {!keys.length ? <p className="text-[13px] text-muted">Nothing usable was found in this file.</p> : null}
        <div className="divide-y divide-line/60">
          {keys.map((k) => {
            const has = current && !isEmpty(current[k]);
            const skipped = mode === "fill" && has;
            return (
              <label key={k} className="flex items-start gap-3 py-2.5">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-[#8fa4ff]"
                  checked={picked.has(k)}
                  onChange={(e) => {
                    const n = new Set(picked);
                    if (e.target.checked) n.add(k);
                    else n.delete(k);
                    setPicked(n);
                  }}
                />
                <span className="w-28 shrink-0 text-[13px] font-medium">{LABELS[k]}</span>
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-3 text-[13px] text-fg/90 selectable">{preview(k, parsed.fields[k])}</span>
                  {skipped ? <span className="mt-0.5 block text-[12px] text-faint">You already have this. Choose Replace existing to overwrite it.</span> : null}
                </span>
              </label>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Upload a CV and immediately offer to read it into the profile. */
export function CvUploadButton({ variant = "secondary", label = "Upload your CV" }: { variant?: "primary" | "secondary"; label?: string }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [review, setReview] = useState<{ doc: Doc; parsed: ParsedCv } | null>(null);
  const upload = useAction(
    async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      form.append("title", file.name.replace(/\.[^.]+$/, ""));
      const doc = await api<Doc>("/documents", { method: "POST", body: form });
      const parsed = await api<ParsedCv>(`/documents/${doc.id}/parse`, { method: "POST" });
      return { doc, parsed };
    },
    { invalidate: [qk.documents], onSuccess: (r) => setReview(r) },
  );
  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload.mutate(f);
          e.target.value = "";
        }}
      />
      <Button variant={variant} onClick={() => fileRef.current?.click()} loading={upload.isPending}>
        <FileUp /> {label}
      </Button>
      {review ? <CvImportDialog doc={review.doc} parsed={review.parsed} onClose={() => setReview(null)} /> : null}
    </>
  );
}

export function useParseDoc() {
  const [review, setReview] = useState<{ doc: Doc; parsed: ParsedCv } | null>(null);
  const parse = useAction(async (doc: Doc) => ({ doc, parsed: await api<ParsedCv>(`/documents/${doc.id}/parse`, { method: "POST" }) }), { onSuccess: (r) => setReview(r) });
  return { parse, review, close: () => setReview(null) };
}
