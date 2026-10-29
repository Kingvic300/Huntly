import { ShieldAlert } from "lucide-react";
import { LEVEL_LABEL, type Job } from "@/lib/api";
import { cn, relativeTime } from "@/lib/utils";
import { MatchRing, Tooltip } from "./ui/misc";

/** One lead in a list. The match ring sits on the left so lists scan by shape. */
export function JobRow({ job, active, onClick, compact }: { job: Job; active?: boolean; onClick?: () => void; compact?: boolean }) {
  const where = job.remote && !/remote/i.test(job.location ?? "") ? [job.location, "Remote"].filter(Boolean).join(", ") : job.location ?? "";
  return (
    <button
      onClick={onClick}
      aria-current={active || undefined}
      className={cn(
        "relative flex w-full items-center gap-4 px-5 text-left transition-colors",
        compact ? "py-2.5" : "py-3",
        active ? "bg-raised" : "hover:bg-panel",
        job.status === "dismissed" && "opacity-50",
      )}
    >
      {active ? <span className="absolute inset-y-2 left-0 w-[3px] rounded-r bg-act" /> : null}
      <span className="flex w-[36px] shrink-0 justify-center">
        <MatchRing score={job.score} size="sm" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className={cn("truncate text-[13.5px]", job.status === "new" ? "font-semibold" : "font-medium")}>{job.title}</span>
          {job.flagged_injection ? (
            <Tooltip content="This posting contains text aimed at AI assistants. Huntly treats it as plain data.">
              <ShieldAlert className="size-3.5 shrink-0 text-warn" />
            </Tooltip>
          ) : null}
        </span>
        <span className="mt-0.5 flex gap-3 text-[12.5px] text-muted">
          <span className="max-w-[55%] shrink-0 truncate">{job.company ?? "Company not listed"}</span>
          {where ? <span className={cn("min-w-0 truncate", job.remote ? "text-act/90" : "text-faint")}>{where}</span> : null}
          {job.seniority ? <span className="shrink-0 text-faint">{LEVEL_LABEL[job.seniority]}</span> : null}
        </span>
      </span>
      {!compact ? <span className="shrink-0 text-right text-[12px] text-faint">{relativeTime(job.posted_at ?? job.discovered_at)}</span> : null}
    </button>
  );
}
