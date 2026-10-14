import * as React from "react";
import { cn } from "@/lib/utils";

const base =
  "w-full rounded-[var(--radius-control)] bg-ink px-2.5 text-[13.5px] text-fg ring-1 ring-inset ring-line placeholder:text-faint transition-shadow hover:ring-line-strong focus:outline-none focus:ring-2 focus:ring-act/70 disabled:opacity-50 aria-[invalid=true]:ring-bad/70";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn(base, "h-8", className)} {...props} />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cn(base, "min-h-20 py-2 leading-relaxed", className)} {...props} />
));
Textarea.displayName = "Textarea";

const chevron =
  "bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%239aa1af%22 stroke-width=%222.2%22><path d=%22m6 9 6 6 6-6%22/></svg>')] bg-[right_9px_center] bg-no-repeat";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(({ className, children, ...props }, ref) => (
  <select ref={ref} className={cn(base, chevron, "h-8 appearance-none pr-7", className)} {...props}>
    {children}
  </select>
));
Select.displayName = "Select";

export function Field({ label, hint, error, children, className }: { label: string; hint?: React.ReactNode; error?: string | null; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <span className="text-[12.5px] font-medium text-muted">{label}</span>
      {children}
      {error ? (
        <span className="text-[12px] text-bad" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span className="text-[12px] text-faint">{hint}</span>
      ) : null}
    </div>
  );
}
