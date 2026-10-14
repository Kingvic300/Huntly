import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";

export default function Unlock() {
  const [pw, setPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/vault/unlock", { method: "POST", json: { password: pw } });
      setPw("");
      await qc.invalidateQueries();
    } catch (err) {
      setError(err instanceof ApiError ? (err.status === 401 ? "That password isn't right. Try again." : err.message) : "Couldn't unlock Huntly");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-[360px]">
        <svg viewBox="0 0 24 24" className="size-10" aria-hidden>
          <rect width="24" height="24" rx="6" fill="#252a33" />
          <path d="M7 17V7m10 10V7M7 12h10" stroke="#8fa4ff" strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="17" cy="7" r="2.2" fill="#f2b84b" />
        </svg>
        <h1 className="mt-6 text-[24px] font-semibold tracking-[-0.015em]">Unlock Huntly</h1>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">Your master password decrypts your saved keys. It never leaves this computer.</p>
        <Input
          type="password"
          autoFocus
          className="mt-6 h-10 text-[14px]"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          placeholder="Master password"
          aria-label="Master password"
          aria-invalid={!!error}
          autoComplete="current-password"
        />
        {error ? (
          <p role="alert" className="mt-2 text-[12.5px] text-bad">
            {error}
          </p>
        ) : null}
        <Button type="submit" variant="primary" size="lg" className="mt-4 w-full" loading={busy} disabled={!pw}>
          Unlock
        </Button>
        <p className="mt-6 text-[12px] leading-relaxed text-faint">
          Forgot it? Nobody can recover it, including Huntly's maintainers. To start over, delete vault.json in your Huntly folder and enter your keys again.
        </p>
      </form>
    </div>
  );
}
