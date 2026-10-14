import { useQueryClient } from "@tanstack/react-query";
import { BarChart3, Bell, Briefcase, FileUser, Lock, MailCheck, Radar, Rss, Search, Settings, Sun, User } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { api, type Job } from "@/lib/api";
import { qk, useAction, useGmail, useHealth, useNotifications, usePipeline, useProfile, useScheduler } from "@/lib/queries";
import { cn, formatDate, relativeTime, titleCase } from "@/lib/utils";
import { Button } from "../ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "../ui/dropdown";
import { Logo } from "../Logo";
import { Dot, HeatMeter } from "../ui/misc";

export const NAV = [
  { to: "/", label: "Today", icon: Sun, key: "1" },
  { to: "/jobs", label: "Discover", icon: Radar, key: "2" },
  { to: "/applications", label: "Applications", icon: Briefcase, key: "3" },
  { to: "/approvals", label: "Approvals", icon: MailCheck, key: "4" },
  { to: "/cv", label: "Profile", icon: FileUser, key: "5" },
  { to: "/sources", label: "Sources", icon: Rss, key: "6" },
  { to: "/analytics", label: "Insights", icon: BarChart3, key: "7" },
];

/** Where each pipeline stage lives in the app. */
export const STAGE_LINK: Record<string, string> = {
  new: "/jobs?status=new",
  shortlisted: "/jobs?status=saved",
  preparing: "/applications",
  awaiting_approval: "/approvals",
  applied: "/applications",
  interviewing: "/applications",
  offer: "/applications",
};

function Rail() {
  const pipeline = usePipeline();
  const pending = pipeline.data?.stages.find((s) => s.id === "awaiting_approval")?.count ?? 0;
  const item = (to: string, label: string, Icon: typeof Sun, key: string, badge?: number) => (
    <NavLink
      key={to}
      to={to}
      end={to === "/"}
      title={`${label} (Ctrl+${key})`}
      className={({ isActive }) =>
        cn(
          "relative flex w-full flex-col items-center gap-1 rounded-[8px] px-1 py-2 text-[11px] font-medium transition-colors",
          isActive ? "bg-raised text-fg" : "text-faint hover:bg-panel hover:text-fg",
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon className={cn("size-[19px]", isActive && "text-act")} strokeWidth={1.8} />
          <span className="max-w-full truncate">{label}</span>
          {badge ? <span className="absolute right-2 top-1.5 min-w-4 rounded-full bg-act px-1 text-center text-[10px] font-semibold leading-4 text-act-ink">{badge}</span> : null}
        </>
      )}
    </NavLink>
  );
  return (
    <nav aria-label="Main" className="flex w-[96px] shrink-0 flex-col items-center gap-1 border-r border-line/70 px-2 py-3">
      {NAV.map((n) => item(n.to, n.label, n.icon, n.key, n.to === "/approvals" ? pending : undefined))}
      <div className="mt-auto w-full">{item("/settings", "Settings", Settings, ",")}</div>
    </nav>
  );
}

type SearchResults = { jobs: Job[]; applications: { id: number; title: string; company: string; status: string }[]; approvals: { id: number; subject: string; status: string }[] };

function CommandSearch() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<SearchResults | null>(null);
  const [cursor, setCursor] = useState(0);
  const ref = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      if (e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current?.focus();
        ref.current?.select();
      } else if (e.key === ",") {
        e.preventDefault();
        navigate("/settings");
      } else {
        const n = NAV.find((x) => x.key === e.key);
        if (n) {
          e.preventDefault();
          navigate(n.to);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  useEffect(() => {
    if (q.trim().length < 2) {
      setResults(null);
      return;
    }
    const t = setTimeout(() => {
      api<SearchResults>(`/search?q=${encodeURIComponent(q.trim())}`)
        .then((r) => {
          setResults(r);
          setCursor(0);
        })
        .catch(() => setResults(null));
    }, 160);
    return () => clearTimeout(t);
  }, [q]);

  const rows = useMemo(() => {
    if (!results) return [];
    return [
      ...results.jobs.map((j) => ({ key: `j${j.id}`, href: `/jobs?id=${j.id}`, title: j.title, sub: j.company ?? "", lead: <HeatMeter score={j.score} size="sm" /> })),
      ...results.applications.map((a) => ({ key: `a${a.id}`, href: `/applications?id=${a.id}`, title: a.title, sub: `Application, ${titleCase(a.status).toLowerCase()}`, lead: <Briefcase className="size-3.5 text-muted" /> })),
      ...results.approvals.map((a) => ({ key: `m${a.id}`, href: `/approvals?id=${a.id}`, title: a.subject, sub: `Email, ${a.status}`, lead: <MailCheck className="size-3.5 text-muted" /> })),
    ];
  }, [results]);

  const go = (href: string) => {
    navigate(href);
    setOpen(false);
    setQ("");
    ref.current?.blur();
  };

  return (
    <div className="relative w-[460px] max-w-[42vw]">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-[15px] -translate-y-1/2 text-faint" />
      <input
        ref={ref}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "Escape") ref.current?.blur();
          if (e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, rows.length - 1));
          if (e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
          if (e.key === "Enter" && rows[cursor]) go(rows[cursor].href);
        }}
        placeholder="Find a job, company or email"
        aria-label="Search"
        className="h-8 w-full rounded-[8px] bg-panel pl-9 pr-16 text-[13px] ring-1 ring-inset ring-line placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-act/60"
      />
      <span className="pointer-events-none absolute right-2 top-1/2 flex -translate-y-1/2 gap-1">
        <span className="key">Ctrl</span>
        <span className="key">K</span>
      </span>
      {open && results ? (
        <div className="absolute left-0 right-0 top-10 z-40 max-h-[420px] overflow-y-auto rounded-[10px] bg-raised p-1 ring-1 ring-line-strong">
          {!rows.length ? <p className="px-3 py-5 text-[13px] text-muted">Nothing matches “{q}”.</p> : null}
          {rows.map((r, i) => (
            <button
              key={r.key}
              onMouseDown={() => go(r.href)}
              onMouseEnter={() => setCursor(i)}
              className={cn("flex w-full items-center gap-3 rounded-[7px] px-2.5 py-2 text-left", i === cursor && "bg-hover")}
            >
              <span className="flex w-12 justify-start">{r.lead}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px]">{r.title}</span>
                <span className="block truncate text-[12px] text-muted">{r.sub}</span>
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Notifications() {
  const n = useNotifications();
  const markAll = useAction(() => api("/notifications/read-all", { method: "POST" }), { invalidate: [qk.notifications] });
  const tone = (l: string) => (l === "error" ? "bad" : l === "warning" ? "warn" : l === "success" ? "ok" : "act") as "bad" | "warn" | "ok" | "act";
  return (
    <DropdownMenu onOpenChange={(o) => !o && n.data?.unread && markAll.mutate()}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Notifications, ${n.data?.unread ?? 0} unread`} className="relative">
          <Bell className="!size-[17px]" strokeWidth={1.8} />
          {n.data?.unread ? <span className="absolute right-1 top-1 min-w-4 rounded-full bg-act px-1 text-[10px] font-semibold leading-4 text-act-ink">{n.data.unread}</span> : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-[340px] p-0">
        <p className="px-3.5 pb-2 pt-3 text-[13px] font-semibold">Notifications</p>
        <div className="max-h-96 overflow-y-auto px-1 pb-1">
          {!n.data?.items.length ? <p className="px-2.5 pb-4 pt-1 text-[13px] text-muted">Nothing new.</p> : null}
          {n.data?.items.map((item) => (
            <div key={item.id} className="flex gap-3 rounded-[7px] px-2.5 py-2 hover:bg-hover">
              <span className="mt-[7px]">{item.read ? <Dot tone="idle" /> : <Dot tone={tone(item.level)} />}</span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] leading-snug">{item.title}</p>
                {item.body ? <p className="mt-0.5 line-clamp-2 text-[12px] text-muted">{item.body}</p> : null}
                <p className="mt-0.5 text-[11.5px] text-faint">{relativeTime(item.ts)}</p>
              </div>
            </div>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UserMenu() {
  const profile = useProfile();
  const health = useHealth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const lock = useAction(() => api("/vault/lock", { method: "POST" }), { onSuccess: () => qc.invalidateQueries() });
  const name = profile.data?.profile.full_name || "You";
  const initials = useMemo(
    () =>
      name
        .split(/\s+/)
        .map((p) => p[0])
        .slice(0, 2)
        .join("")
        .toUpperCase(),
    [name],
  );
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex size-8 items-center justify-center rounded-full bg-act/18 text-[12px] font-semibold text-act ring-1 ring-act/30 hover:bg-act/25" aria-label="Account menu">
          {initials}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>
          <span className="block text-[13px] font-semibold text-fg">{name}</span>
          <span className="text-[12px]">Huntly {health.data?.version}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/cv")}>
          <User /> Edit profile
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/settings")}>
          <Settings /> Settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => lock.mutate()}>
          <Lock /> Lock Huntly
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function TitleBar() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(t);
  }, []);
  return (
    <header className="flex h-[52px] shrink-0 items-center gap-4 border-b border-line/70 px-4">
      <div className="flex w-[80px] items-center">
        <Logo size={26} />
      </div>
      <CommandSearch />
      <div className="ml-auto flex items-center gap-2">
        <time className="mr-2 text-[12.5px] text-muted" title="All schedules follow Africa/Lagos time">
          {new Intl.DateTimeFormat("en-GB", { timeZone: "Africa/Lagos", weekday: "long", day: "numeric", month: "long" }).format(now)},{" "}
          <span className="text-fg">{new Intl.DateTimeFormat("en-GB", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit" }).format(now)}</span> WAT
        </time>
        <Notifications />
        <UserMenu />
      </div>
    </header>
  );
}

function StatusBar() {
  const gmail = useGmail();
  const sched = useScheduler();
  const qc = useQueryClient();
  const wasCollecting = useRef(false);
  // When a background search finishes, refresh everything it may have changed.
  useEffect(() => {
    const now = !!sched.data?.collecting;
    if (wasCollecting.current && !now) {
      for (const key of [["jobs"], ["sources"], ["analytics"], qk.pipeline, qk.notifications]) qc.invalidateQueries({ queryKey: key });
    }
    wasCollecting.current = now;
  }, [sched.data?.collecting, qc]);
  const health = useHealth();
  const pipeline = usePipeline();
  const next = sched.data?.jobs?.find((j) => j.id === "collect")?.next_run;
  const lastRun = sched.data?.runs?.find((r) => r.kind === "collect");
  const failing = pipeline.data?.failing_sources ?? 0;
  return (
    <footer className="flex h-7 shrink-0 items-center gap-5 border-t border-line/70 bg-panel/60 px-4 text-[11.5px] text-muted">
      <NavLink to="/settings" className="flex items-center gap-1.5 hover:text-fg">
        <Dot tone={gmail.data?.connected ? "ok" : "idle"} />
        {gmail.data?.connected ? gmail.data.email ?? "Gmail connected" : "Gmail not connected"}
      </NavLink>
      <span className="flex items-center gap-1.5">
        <Dot tone={sched.data?.collecting ? "act" : !sched.data?.running ? "bad" : lastRun?.status === "error" ? "warn" : "ok"} />
        <span>
          {sched.data?.collecting
            ? "Looking for jobs now"
            : next
              ? `Next search ${formatDate(next, { hour: "2-digit", minute: "2-digit" })}`
              : "Automatic search off"}
          {lastRun && !sched.data?.collecting ? <span className="text-faint">, last ran {relativeTime(lastRun.finished_at ?? lastRun.started_at)}</span> : null}
        </span>
      </span>
      {failing ? (
        <NavLink to="/sources" className="flex items-center gap-1.5 text-warn hover:underline">
          {failing} source{failing > 1 ? "s" : ""} failing
        </NavLink>
      ) : null}
      <span className="ml-auto flex items-center gap-1.5" title="Credentials are encrypted on this computer. Nothing is sent to the Huntly maintainers.">
        <Lock className="size-3" /> Keys encrypted locally
      </span>
      <span className="text-faint">No telemetry</span>
      <span className="text-faint">v{health.data?.version}</span>
    </footer>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <TitleBar />
      <div className="flex min-h-0 flex-1">
        <Rail />
        <div className="flex min-w-0 flex-1 flex-col">
          <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
        </div>
      </div>
      <StatusBar />
    </div>
  );
}
