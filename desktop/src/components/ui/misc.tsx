import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { AlertTriangle, type LucideIcon } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

/** A bordered region. Hierarchy comes from background steps, not shadows. */
export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <section className={cn("rounded-[var(--radius-pane)] bg-panel ring-1 ring-inset ring-line/70", className)} {...props} />;
}

export function PanelHeader({ title, description, actions, className }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return (
    <header className={cn("flex items-center justify-between gap-3 px-4 pb-2 pt-3.5", className)}>
      <div className="min-w-0">
        <h2 className="section-title">{title}</h2>
        {description ? <p className="mt-0.5 text-[12.5px] text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

const badgeTones = {
  neutral: "bg-raised text-muted",
  act: "bg-act/14 text-act",
  ok: "bg-ok/12 text-ok",
  warn: "bg-warn/12 text-warn",
  bad: "bg-bad/12 text-bad",
  heat: "bg-heat/14 text-heat",
};

export function Badge({ tone = "neutral", className, ...props }: React.HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof badgeTones }) {
  return <span className={cn("inline-flex h-[20px] items-center gap-1 whitespace-nowrap rounded-[var(--radius-chip)] px-1.5 text-[11.5px] font-medium [&_svg]:size-3", badgeTones[tone], className)} {...props} />;
}

export function Dot({ tone }: { tone: "ok" | "bad" | "warn" | "act" | "idle" }) {
  const c = { ok: "bg-ok", bad: "bg-bad", warn: "bg-warn", act: "bg-act", idle: "bg-faint" }[tone];
  return <span className={cn("inline-block size-[7px] shrink-0 rounded-full", c)} aria-hidden />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-raised", className)} />;
}

export function EmptyState({ icon: Icon, title, description, action, className }: { icon?: LucideIcon; title: string; description?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-start justify-center gap-1.5 px-8 py-12", className)}>
      {Icon ? <Icon className="mb-2 size-5 text-faint" strokeWidth={1.75} /> : null}
      <p className="text-[14px] font-semibold">{title}</p>
      {description ? <p className="max-w-[46ch] text-[13px] leading-relaxed text-muted">{description}</p> : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-3 px-8 py-10">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-bad" />
      <div>
        <p className="text-[14px] font-semibold">This didn't load</p>
        <p className="mt-1 max-w-[56ch] text-[13px] text-muted selectable">{msg}</p>
        {onRetry ? (
          <Button size="sm" onClick={onRetry} className="mt-3">
            Try again
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        "relative inline-flex h-5 w-[34px] shrink-0 cursor-pointer items-center rounded-full bg-line transition-colors data-[state=checked]:bg-act disabled:cursor-not-allowed disabled:opacity-45",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="block size-4 translate-x-0.5 rounded-full bg-fg transition-transform data-[state=checked]:translate-x-[16px] data-[state=checked]:bg-act-ink" />
    </SwitchPrimitive.Root>
  );
}

export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;
/** Segmented control: tabs read as one object. */
export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("inline-flex items-center gap-0.5 rounded-[var(--radius-control)] bg-panel p-0.5 ring-1 ring-inset ring-line", className)} {...props} />;
}
export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn("h-7 rounded-[5px] px-3 text-[12.5px] font-medium text-muted transition-colors hover:text-fg data-[state=active]:bg-raised data-[state=active]:text-fg", className)}
      {...props}
    />
  );
}

/** Same look as TabsList, driven by plain state (for filters). */
export function Segmented<T extends string>({ value, onChange, options, className }: { value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode }[]; className?: string }) {
  return (
    <div role="radiogroup" className={cn("inline-flex items-center gap-0.5 rounded-[var(--radius-control)] bg-panel p-0.5 ring-1 ring-inset ring-line", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn("flex h-7 items-center gap-1.5 rounded-[5px] px-2.5 text-[12.5px] font-medium transition-colors", value === o.value ? "bg-raised text-fg" : "text-muted hover:text-fg")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Tooltip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactNode; side?: "top" | "right" | "bottom" | "left" }) {
  return (
    <TooltipPrimitive.Root delayDuration={250}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content side={side} sideOffset={6} className="z-50 max-w-xs rounded-md bg-fg px-2 py-1 text-[12px] font-medium text-ink">
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
export const TooltipProvider = TooltipPrimitive.Provider;

/**
 * Match ring: how well a job fits your profile (built from your CV), 0 to 100. The ring
 * fills clockwise and turns a deeper amber as the match rises, so a list scans by shape.
 */
export function MatchRing({ score, size = "md", className }: { score: number; size?: "sm" | "md" | "lg"; className?: string }) {
  const s = Math.max(0, Math.min(100, score));
  const { px, stroke, text } = {
    sm: { px: 30, stroke: 3, text: "text-[10.5px]" },
    md: { px: 40, stroke: 3.5, text: "text-[12.5px]" },
    lg: { px: 72, stroke: 6, text: "text-[22px] tracking-tight" },
  }[size];
  const r = (px - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const arc = s >= 75 ? "text-heat" : s >= 50 ? "text-heat/75" : s >= 30 ? "text-heat-dim" : "text-faint";
  return (
    <span role="img" aria-label={`Match ${Math.round(s)} out of 100`} className={cn("relative inline-flex shrink-0 items-center justify-center", className)} style={{ width: px, height: px }}>
      <svg width={px} height={px} viewBox={`0 0 ${px} ${px}`} className="-rotate-90" aria-hidden="true">
        <circle cx={px / 2} cy={px / 2} r={r} fill="none" strokeWidth={stroke} stroke="var(--color-line)" />
        {s >= 1 ? (
          <circle
            cx={px / 2}
            cy={px / 2}
            r={r}
            fill="none"
            strokeWidth={stroke}
            strokeLinecap="round"
            stroke="currentColor"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - s / 100)}
            className={cn(arc, "transition-[stroke-dashoffset] duration-500")}
          />
        ) : null}
      </svg>
      <span className={cn("absolute font-semibold leading-none tabular-nums", text, s >= 75 ? "text-heat" : s >= 50 ? "text-fg" : "text-muted")}>{Math.round(s)}</span>
    </span>
  );
}

export function PageHeader({ title, description, actions, children }: { title: string; description?: React.ReactNode; actions?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="px-7 pb-4 pt-6">
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="page-title">{title}</h1>
          {description ? <p className="mt-1 max-w-[70ch] text-[13px] text-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
      {children ? <div className="mt-4">{children}</div> : null}
    </div>
  );
}
