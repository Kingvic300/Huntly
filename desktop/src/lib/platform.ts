/** Thin wrappers around Tauri APIs that degrade gracefully outside the desktop shell (tests, vite preview). */
export const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export async function openUrl(url: string) {
  if (!/^https?:\/\//i.test(url) && !/^mailto:/i.test(url)) return;
  if (isTauri) {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(url);
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

export async function openPath(path: string) {
  if (!isTauri) throw new Error("Opening files requires the desktop app");
  const { openPath } = await import("@tauri-apps/plugin-opener");
  await openPath(path);
}

export async function revealPath(path: string) {
  if (!isTauri) throw new Error("Revealing files requires the desktop app");
  const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
  await revealItemInDir(path);
}

export async function onShellEvent(name: "menu" | "navigate", cb: (payload: string) => void) {
  if (!isTauri) return () => {};
  const { listen } = await import("@tauri-apps/api/event");
  return listen<string>(name, (e) => cb(e.payload));
}
