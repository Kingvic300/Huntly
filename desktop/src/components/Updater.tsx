/**
 * Background updates, like a messaging app: check GitHub Releases quietly, download the
 * signed update in the background, then offer a one-click restart. Updates are verified
 * against the public key built into the app, so only releases signed by the maintainers'
 * key can install. No data about you is sent; the request is a plain file download.
 */
import { Download, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { isTauri } from "@/lib/platform";
import { useSettings } from "@/lib/queries";
import { Button } from "./ui/button";

const CHECK_EVERY_MS = 6 * 60 * 60 * 1000;

type State =
  | { kind: "idle" }
  | { kind: "downloading"; version: string; progress: number | null }
  | { kind: "ready"; version: string; notes?: string }
  | { kind: "error"; message: string };

export function useUpdater() {
  const [state, setState] = useState<State>({ kind: "idle" });
  const busy = useRef(false);

  const check = useCallback(async (manual = false) => {
    if (!isTauri || busy.current) return null;
    busy.current = true;
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (!update) return null;
      let total = 0;
      let done = 0;
      setState({ kind: "downloading", version: update.version, progress: null });
      await update.download((e) => {
        if (e.event === "Started") total = e.data.contentLength ?? 0;
        if (e.event === "Progress") {
          done += e.data.chunkLength;
          setState({ kind: "downloading", version: update.version, progress: total ? Math.round((100 * done) / total) : null });
        }
      });
      setState({ kind: "ready", version: update.version, notes: update.body });
      pending.current = update;
      return update.version;
    } catch (e) {
      if (manual) setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });
      return null;
    } finally {
      busy.current = false;
    }
  }, []);

  const pending = useRef<{ install: () => Promise<void> } | null>(null);
  const restart = useCallback(async () => {
    if (!pending.current) return;
    await pending.current.install();
    const { relaunch } = await import("@tauri-apps/plugin-process");
    await relaunch();
  }, []);

  return { state, setState, check, restart };
}

/** Bottom banner shown once an update has been downloaded. */
export function UpdateBanner() {
  const settings = useSettings();
  const { state, setState, check, restart } = useUpdater();
  const [dismissed, setDismissed] = useState(false);
  const [installing, setInstalling] = useState(false);
  const enabled = settings.data ? settings.data.auto_update !== false : false;

  useEffect(() => {
    if (!enabled) return;
    const first = setTimeout(() => check(), 20_000); // let the app settle first
    const timer = setInterval(() => check(), CHECK_EVERY_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [enabled, check]);

  if (state.kind !== "ready" || dismissed) return null;
  return (
    <div role="status" className="fixed bottom-10 left-1/2 z-40 flex -translate-x-1/2 items-center gap-3 rounded-[10px] bg-raised px-4 py-2.5 ring-1 ring-line-strong">
      <Download className="size-4 text-act" />
      <span className="text-[13px]">
        Huntly {state.version} is ready. <span className="text-muted">Restart to finish updating.</span>
      </span>
      <Button
        size="sm"
        variant="primary"
        loading={installing}
        onClick={async () => {
          setInstalling(true);
          try {
            await restart();
          } catch (e) {
            setInstalling(false);
            setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });
          }
        }}
      >
        <RefreshCw /> Restart now
      </Button>
      <Button size="icon-sm" variant="ghost" aria-label="Later" onClick={() => setDismissed(true)}>
        <X />
      </Button>
    </div>
  );
}
