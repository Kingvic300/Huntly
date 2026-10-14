import { ExternalLink, FolderOpen } from "lucide-react";
import { toast } from "sonner";
import type { Doc } from "@/lib/api";
import { openPath, revealPath } from "@/lib/platform";
import { Button } from "./ui/button";

export function DocActions({ doc }: { doc: Pick<Doc, "path" | "title"> }) {
  const run = (fn: (p: string) => Promise<void>) => fn(doc.path).catch((e) => toast.error(`Couldn't open the file: ${e instanceof Error ? e.message : e}`, { description: doc.path }));
  return (
    <div className="flex gap-0.5">
      <Button size="icon-sm" variant="ghost" aria-label={`Open ${doc.title}`} title="Open" onClick={() => run(openPath)}>
        <ExternalLink />
      </Button>
      <Button size="icon-sm" variant="ghost" aria-label={`Show ${doc.title} in its folder`} title="Show in folder" onClick={() => run(revealPath)}>
        <FolderOpen />
      </Button>
    </div>
  );
}
