import { X } from "lucide-react";
import { useState } from "react";

export function TagInput({ value, onChange, placeholder, label }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string; label: string }) {
  const [draft, setDraft] = useState("");
  const add = (raw: string) => {
    const items = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .filter((s) => !value.some((v) => v.toLowerCase() === s.toLowerCase()));
    if (items.length) onChange([...value, ...items]);
    setDraft("");
  };
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-[var(--radius-control)] bg-ink px-1.5 py-1.5 ring-1 ring-inset ring-line focus-within:ring-2 focus-within:ring-act/70">
      {value.map((t) => (
        <span key={t} className="inline-flex h-6 items-center gap-1 rounded-[5px] bg-raised pl-2 pr-0.5 text-[12.5px]">
          {t}
          <button type="button" onClick={() => onChange(value.filter((x) => x !== t))} className="rounded p-0.5 text-faint hover:text-fg" aria-label={`Remove ${t}`}>
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        aria-label={label}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add(draft);
          } else if (e.key === "Backspace" && !draft && value.length) onChange(value.slice(0, -1));
        }}
        onBlur={() => draft && add(draft)}
        onPaste={(e) => {
          const text = e.clipboardData.getData("text");
          if (text.includes(",")) {
            e.preventDefault();
            add(text);
          }
        }}
        placeholder={value.length ? "Add more" : placeholder}
        className="h-6 min-w-28 flex-1 bg-transparent px-1 text-[13.5px] placeholder:text-faint focus:outline-none"
      />
    </div>
  );
}
