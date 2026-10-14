import { Check, FileInput, FileText, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { CvImportDialog, CvUploadButton, useParseDoc } from "@/components/CvImport";
import { DocActions } from "@/components/DocActions";
import { TagInput } from "@/components/TagInput";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Badge, EmptyState, ErrorState, Segmented, Skeleton, Switch } from "@/components/ui/misc";
import { api, type Doc, type Education, type Experience, type Profile, type ProfileResponse, type Project } from "@/lib/api";
import { qk, useAction, useDocuments, useProfile } from "@/lib/queries";
import { cn, formatBytes, formatDate } from "@/lib/utils";

const emptyExp: Experience = { title: "", company: "", location: "", start: "", end: "", highlights: [] };
const emptyEdu: Education = { institution: "", qualification: "", start: "", end: "", details: "" };
const emptyProj: Project = { name: "", description: "", url: "", technologies: [] };

const SECTIONS = [
  { id: "basics", label: "About you" },
  { id: "skills", label: "Summary and skills" },
  { id: "experience", label: "Experience" },
  { id: "education", label: "Education" },
  { id: "projects", label: "Projects" },
  { id: "extras", label: "Certifications and languages" },
  { id: "prefs", label: "What you're looking for" },
  { id: "documents", label: "Files" },
] as const;
type SectionId = (typeof SECTIONS)[number]["id"];

function Entries<T>({ items, onChange, empty, addLabel, render }: { items: T[]; onChange: (v: T[]) => void; empty: T; addLabel: string; render: (item: T, set: (v: T) => void) => React.ReactNode }) {
  return (
    <div className="space-y-4">
      {items.map((item, i) => (
        <div key={i} className="relative rounded-[10px] bg-panel p-4 pr-12 ring-1 ring-inset ring-line/70">
          {render(item, (v) => onChange(items.map((x, j) => (j === i ? v : x))))}
          <Button size="icon-sm" variant="ghost" className="absolute right-3 top-3" aria-label="Remove entry" onClick={() => onChange(items.filter((_, j) => j !== i))}>
            <Trash2 />
          </Button>
        </div>
      ))}
      <Button onClick={() => onChange([...items, structuredClone(empty)])}>
        <Plus /> {addLabel}
      </Button>
    </div>
  );
}

function Documents() {
  const docs = useDocuments();
  const [kind, setKind] = useState<"" | Doc["kind"]>("");
  const [toDelete, setToDelete] = useState<Doc | null>(null);
  const { parse, review, close } = useParseDoc();
  const del = useAction((id: number) => api(`/documents/${id}`, { method: "DELETE" }), { success: "File deleted", invalidate: [qk.documents], onSuccess: () => setToDelete(null) });
  const list = (docs.data ?? []).filter((d) => !kind || d.kind === kind);
  const kindLabel = { base_cv: "Your CV", tailored_cv: "Tailored CV", cover_letter: "Cover letter" };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          value={kind}
          onChange={setKind}
          options={[
            { value: "", label: "All" },
            { value: "base_cv", label: "Your CVs" },
            { value: "tailored_cv", label: "Tailored" },
            { value: "cover_letter", label: "Letters" },
          ]}
        />
        <span className="ml-auto">
          <CvUploadButton label="Upload a CV" />
        </span>
      </div>
      <p className="mt-2 text-[12.5px] text-faint">PDF or Word, up to 10 MB. Huntly reads your CV on this computer to fill in your profile, and keeps the file in your local Huntly folder.</p>
      <div className="mt-5">
        {docs.isPending ? (
          <Skeleton className="h-40" />
        ) : docs.isError ? (
          <ErrorState error={docs.error} onRetry={() => docs.refetch()} />
        ) : list.length ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
            {list.map((d) => (
              <div key={d.id} className="group flex flex-col rounded-[10px] bg-panel p-4 ring-1 ring-inset ring-line/70">
                <div className="flex items-start gap-3">
                  <span className={cn("flex h-11 w-9 shrink-0 items-end justify-center rounded-[3px] pb-1 text-[9.5px] font-bold", d.format === "pdf" ? "bg-[#f3d7d2] text-[#8a2b20]" : "bg-[#d6e0f5] text-[#25407a]")}>
                    {d.format.toUpperCase()}
                  </span>
                  <span className="min-w-0">
                    <span className="line-clamp-2 text-[13px] font-medium leading-snug">{d.title}</span>
                    <span className="mt-0.5 block text-[12px] text-muted">{kindLabel[d.kind]}</span>
                  </span>
                </div>
                <div className="mt-auto flex items-center pt-4 text-[12px] text-faint">
                  {formatDate(d.created_at)}, {formatBytes(d.size)}
                  {d.meta?.source === "groq" ? <Badge className="ml-2">AI wording</Badge> : null}
                  <span className="ml-auto flex">
                    {d.kind === "base_cv" ? (
                      <Button size="icon-sm" variant="ghost" aria-label={`Fill profile from ${d.title}`} title="Fill my profile from this CV" onClick={() => parse.mutate(d)} loading={parse.isPending && parse.variables?.id === d.id}>
                        <FileInput />
                      </Button>
                    ) : null}
                    <DocActions doc={d} />
                    <Button size="icon-sm" variant="ghost" aria-label={`Delete ${d.title}`} onClick={() => setToDelete(d)}>
                      <Trash2 />
                    </Button>
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={FileText} className="px-0" title="No files yet" description="Upload the CV you already use, or make tailored ones from an application." />
        )}
      </div>
      {review ? <CvImportDialog doc={review.doc} parsed={review.parsed} onClose={close} /> : null}
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Delete this file?"
        description={`“${toDelete?.title}” will be removed from your computer. Emails that attach it will need another file.`}
        confirmLabel="Delete file"
        tone="danger"
        loading={del.isPending}
        onConfirm={() => toDelete && del.mutate(toDelete.id)}
      />
    </div>
  );
}

export default function CvLibrary() {
  const profile = useProfile();
  const [p, setP] = useState<Profile | null>(null);
  const [section, setSection] = useState<SectionId>("basics");
  useEffect(() => {
    if (profile.data && !p) setP(structuredClone(profile.data.profile));
  }, [profile.data, p]);
  const save = useAction(() => api<ProfileResponse>("/profile", { method: "PUT", json: p }), { success: "Profile saved. Scores updated.", invalidate: [qk.profile, ["jobs"], ["analytics"]] });

  if (profile.isError) return <ErrorState error={profile.error} onRetry={() => profile.refetch()} />;
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => p && setP({ ...p, [k]: v });
  const dirty = !!p && !!profile.data && JSON.stringify(p) !== JSON.stringify(profile.data.profile);
  const c = profile.data?.completeness;
  const filled: Partial<Record<SectionId, boolean>> = p
    ? { basics: !!p.full_name && !!p.email && !!p.linkedin_url, skills: !!p.summary && p.skills.length >= 3, experience: p.experience.length > 0, education: p.education.length > 0, projects: p.projects.length > 0, extras: p.certifications.length + p.languages.length > 0, prefs: p.target_roles.length > 0 }
    : {};

  return (
    <div className="flex h-full">
      <nav className="w-[248px] shrink-0 border-r border-line/70 px-4 pt-6" aria-label="Profile sections">
        <h1 className="page-title px-2">CV and profile</h1>
        <p className="mt-1 px-2 text-[12.5px] leading-relaxed text-muted">Your CVs and letters are built only from what you write here.</p>
        <div className="mt-4 px-2">
          <CvUploadButton label="Import from my CV" />
        </div>
        {c ? (
          <div className="mt-4 px-2">
            <div className="flex justify-between text-[12px] text-muted">
              <span>Profile complete</span>
              <span className="tabular-nums text-fg">{c.score}%</span>
            </div>
            <div className="mt-1.5 h-[5px] rounded-full bg-raised">
              <div className="h-full rounded-full bg-act" style={{ width: `${c.score}%` }} />
            </div>
          </div>
        ) : null}
        <ul className="mt-5 space-y-0.5">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => setSection(s.id)}
                className={cn("flex w-full items-center gap-2 rounded-[7px] px-2 py-1.5 text-left text-[13px]", section === s.id ? "bg-raised text-fg" : "text-muted hover:bg-panel hover:text-fg")}
              >
                <span className="flex-1">{s.label}</span>
                {filled[s.id] ? <Check className="size-3.5 text-ok" /> : null}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="px-9 py-7">
            {!p ? (
              <Skeleton className="h-96" />
            ) : section === "documents" ? (
              <>
                <h2 className="mb-5 text-[18px] font-semibold tracking-tight">Files</h2>
                <Documents />
              </>
            ) : (
              <>
                <h2 className="text-[18px] font-semibold tracking-tight">{SECTIONS.find((s) => s.id === section)?.label}</h2>
                {section === "skills" || section === "experience" ? (
                  <p className="mt-1 max-w-[62ch] text-[13px] text-muted">Only include what you have really done. If Groq is on, any wording that adds something not written here is thrown away.</p>
                ) : null}
                <div className="mt-6">
                  {section === "basics" && (
                    <div className="grid grid-cols-2 gap-x-5 gap-y-4 2xl:grid-cols-3">
                      <Field label="Full name">
                        <Input value={p.full_name} onChange={(e) => set("full_name", e.target.value)} />
                      </Field>
                      <Field label="Headline" hint="How you describe yourself in one line">
                        <Input value={p.headline} onChange={(e) => set("headline", e.target.value)} placeholder="Security engineer" />
                      </Field>
                      <Field label="Email">
                        <Input type="email" value={p.email} onChange={(e) => set("email", e.target.value)} />
                      </Field>
                      <Field label="Phone">
                        <Input value={p.phone} onChange={(e) => set("phone", e.target.value)} />
                      </Field>
                      <Field label="Location">
                        <Input value={p.location} onChange={(e) => set("location", e.target.value)} />
                      </Field>
                      <Field label="LinkedIn" hint="Recruiters and ATS systems look for this">
                        <Input value={p.linkedin_url} onChange={(e) => set("linkedin_url", e.target.value)} placeholder="linkedin.com/in/your-name" />
                      </Field>
                      <Field label="GitHub">
                        <Input value={p.github_url} onChange={(e) => set("github_url", e.target.value)} placeholder="github.com/your-name" />
                      </Field>
                      <Field label="Website or portfolio">
                        <Input value={p.portfolio_url} onChange={(e) => set("portfolio_url", e.target.value)} placeholder="yourname.dev" />
                      </Field>
                      <Field label="Other links" className="col-span-2 2xl:col-span-3">
                        <TagInput label="Other links" value={p.links} onChange={(v) => set("links", v)} placeholder="https://" />
                      </Field>
                    </div>
                  )}
                  {section === "skills" && (
                    <div className="space-y-5">
                      <Field label="Summary">
                        <Textarea value={p.summary} onChange={(e) => set("summary", e.target.value)} className="min-h-32 text-[14px]" />
                      </Field>
                      <Field label="Skills" hint="Press Enter or type a comma after each. These drive matching.">
                        <TagInput label="Skills" value={p.skills} onChange={(v) => set("skills", v)} placeholder="Python, Linux, Burp Suite" />
                      </Field>
                    </div>
                  )}
                  {section === "experience" && (
                    <Entries
                      items={p.experience}
                      empty={emptyExp}
                      addLabel="Add a role"
                      onChange={(v) => set("experience", v)}
                      render={(e, update) => (
                        <div className="grid grid-cols-2 gap-3">
                          <Input value={e.title} onChange={(ev) => update({ ...e, title: ev.target.value })} placeholder="Job title" aria-label="Job title" />
                          <Input value={e.company} onChange={(ev) => update({ ...e, company: ev.target.value })} placeholder="Company" aria-label="Company" />
                          <Input value={e.location} onChange={(ev) => update({ ...e, location: ev.target.value })} placeholder="Location" aria-label="Location" />
                          <div className="flex gap-2">
                            <Input value={e.start} onChange={(ev) => update({ ...e, start: ev.target.value })} placeholder="From" aria-label="Start date" />
                            <Input value={e.end} onChange={(ev) => update({ ...e, end: ev.target.value })} placeholder="To, or Present" aria-label="End date" />
                          </div>
                          <Textarea
                            className="col-span-2 min-h-24"
                            value={e.highlights.join("\n")}
                            onChange={(ev) => update({ ...e, highlights: ev.target.value.split("\n") })}
                            onBlur={() => update({ ...e, highlights: e.highlights.map((h) => h.trim()).filter(Boolean) })}
                            placeholder="One achievement per line"
                            aria-label="Achievements"
                          />
                        </div>
                      )}
                    />
                  )}
                  {section === "education" && (
                    <Entries
                      items={p.education}
                      empty={emptyEdu}
                      addLabel="Add education"
                      onChange={(v) => set("education", v)}
                      render={(e, update) => (
                        <div className="grid grid-cols-2 gap-3">
                          <Input value={e.qualification} onChange={(ev) => update({ ...e, qualification: ev.target.value })} placeholder="Qualification" aria-label="Qualification" />
                          <Input value={e.institution} onChange={(ev) => update({ ...e, institution: ev.target.value })} placeholder="School or university" aria-label="Institution" />
                          <Input value={e.start} onChange={(ev) => update({ ...e, start: ev.target.value })} placeholder="From" aria-label="Start" />
                          <Input value={e.end} onChange={(ev) => update({ ...e, end: ev.target.value })} placeholder="To" aria-label="End" />
                        </div>
                      )}
                    />
                  )}
                  {section === "projects" && (
                    <Entries
                      items={p.projects}
                      empty={emptyProj}
                      addLabel="Add a project"
                      onChange={(v) => set("projects", v)}
                      render={(pr, update) => (
                        <div className="grid grid-cols-2 gap-3">
                          <Input value={pr.name} onChange={(ev) => update({ ...pr, name: ev.target.value })} placeholder="Project name" aria-label="Project name" />
                          <Input value={pr.url} onChange={(ev) => update({ ...pr, url: ev.target.value })} placeholder="Link" aria-label="Project link" />
                          <Textarea className="col-span-2 min-h-16" value={pr.description} onChange={(ev) => update({ ...pr, description: ev.target.value })} placeholder="What it does and what you did" aria-label="Description" />
                          <div className="col-span-2">
                            <TagInput label="Technologies" value={pr.technologies} onChange={(v) => update({ ...pr, technologies: v })} placeholder="Technologies used" />
                          </div>
                        </div>
                      )}
                    />
                  )}
                  {section === "extras" && (
                    <div className="space-y-5">
                      <Field label="Certifications">
                        <TagInput label="Certifications" value={p.certifications} onChange={(v) => set("certifications", v)} placeholder="OSCP, CompTIA Security+" />
                      </Field>
                      <Field label="Languages">
                        <TagInput label="Languages" value={p.languages} onChange={(v) => set("languages", v)} placeholder="English, Yoruba" />
                      </Field>
                    </div>
                  )}
                  {section === "prefs" && (
                    <div className="space-y-5">
                      <Field label="Roles you want" hint="Job titles that should score highest">
                        <TagInput label="Target roles" value={p.target_roles} onChange={(v) => set("target_roles", v)} placeholder="Penetration tester" />
                      </Field>
                      <Field label="Places you'd work">
                        <TagInput label="Preferred locations" value={p.preferred_locations} onChange={(v) => set("preferred_locations", v)} placeholder="Lagos" />
                      </Field>
                      <label className="flex items-center gap-3 text-[13.5px]">
                        <Switch checked={p.remote_only} onCheckedChange={(v) => set("remote_only", v)} /> Remote jobs only
                      </label>
                      <Field label="Seniority" hint="For example junior, mid, senior, lead">
                        <TagInput label="Seniority" value={p.seniority} onChange={(v) => set("seniority", v)} />
                      </Field>
                      <Field label="Skip jobs that mention" hint="Matching jobs drop to a score of 10 or less">
                        <TagInput label="Excluded keywords" value={p.exclude_keywords} onChange={(v) => set("exclude_keywords", v)} />
                      </Field>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
        {section !== "documents" ? (
          <div className="flex items-center justify-end gap-2 border-t border-line/70 px-9 py-3">
            {dirty ? <span className="mr-auto text-[12.5px] text-warn">You have unsaved changes</span> : null}
            <Button variant="ghost" disabled={!dirty} onClick={() => profile.data && setP(structuredClone(profile.data.profile))}>
              Discard
            </Button>
            <Button variant="primary" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
              Save profile
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
