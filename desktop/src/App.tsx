import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, ServerCrash } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AppShell } from "./components/layout/AppShell";
import { Button } from "./components/ui/button";
import { api, waitForCore, type OnboardingStatus } from "./lib/api";
import { onShellEvent } from "./lib/platform";
import { qk } from "./lib/queries";
import Analytics from "./pages/Analytics";
import Applications from "./pages/Applications";
import Approvals from "./pages/Approvals";
import CvLibrary from "./pages/CvLibrary";
import Jobs from "./pages/Jobs";
import Onboarding from "./pages/Onboarding";
import Overview from "./pages/Overview";
import SettingsPage from "./pages/Settings";
import Sources from "./pages/Sources";
import Unlock from "./pages/Unlock";

function Boot({ children }: { children: React.ReactNode }) {
  const core = useQuery({ queryKey: ["boot"], queryFn: () => waitForCore(), retry: false, staleTime: Infinity });
  if (core.isPending) return <Splash label="Starting Huntly…" />;
  if (core.isError)
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <ServerCrash className="size-6 text-bad" />
        <p className="text-[15px] font-semibold">Huntly's background service didn't start</p>
        <p className="max-w-md text-[13px] text-muted selectable">{(core.error as Error).message}</p>
        <p className="max-w-md text-[12.5px] text-faint">Details are in ~/.local/share/huntly/logs/core.log</p>
        <Button size="sm" onClick={() => core.refetch()}>
          Try again
        </Button>
      </div>
    );
  return <>{children}</>;
}

export function Splash({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center gap-2 text-[13px] text-muted">
      <Loader2 className="size-4 animate-spin text-act" /> {label}
    </div>
  );
}

function Gate() {
  const [setupSession, setSetupSession] = useState(false);
  const status = useQuery({
    queryKey: qk.onboarding,
    queryFn: () => api<OnboardingStatus>("/onboarding/status"),
    retry: 3,
    // Keep trying while the background service restarts.
    refetchInterval: (q) => (q.state.status === "error" ? 2000 : false),
  });
  const qc = useQueryClient();
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = async (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k !== "r" && k !== "l") return;
      e.preventDefault();
      try {
        if (k === "r") {
          await api("/collect", { method: "POST", json: {} });
          toast.success("Searching your sources now");
          qc.invalidateQueries({ queryKey: qk.scheduler });
        } else {
          await api("/vault/lock", { method: "POST" });
          qc.invalidateQueries();
        }
      } catch (err) {
        toast.error((err as Error).message);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [qc]);

  useEffect(() => {
    const subs: Promise<() => void>[] = [
      onShellEvent("navigate", (path) => navigate(path.split("#")[0])),
      onShellEvent("menu", async (id) => {
        try {
          if (id === "collect") {
            await api("/collect", { method: "POST", json: {} });
            toast.success("Collection started");
            qc.invalidateQueries({ queryKey: qk.scheduler });
          } else if (id === "lock") {
            await api("/vault/lock", { method: "POST" });
            qc.invalidateQueries();
          }
        } catch (e) {
          toast.error((e as Error).message);
        }
      }),
    ];
    return () => subs.forEach((p) => p.then((un) => un()));
  }, [navigate, qc]);

  if (status.data && !status.data.vault_initialized && !setupSession) setSetupSession(true);
  if (status.isPending) return <Splash label="Loading…" />;
  if (status.isError) return <Splash label={`${(status.error as Error).message}. Reconnecting…`} />;
  const s = status.data;
  // Setup runs once: until the vault exists, or while finishing the wizard in the session
  // that created it. Later launches go straight to unlock and the app.
  if (!s.vault_initialized || setupSession) return <Onboarding status={s} onFinish={() => setSetupSession(false)} />;
  if (!s.vault_unlocked) return <Unlock />;
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/applications" element={<Applications />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/cv" element={<CvLibrary />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}

export default function App() {
  return (
    <Boot>
      <Gate />
    </Boot>
  );
}
