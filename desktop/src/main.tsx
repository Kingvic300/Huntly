import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App";
import { TooltipProvider } from "./components/ui/misc";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 5000 } },
});

// Suppress the browser context menu outside editable fields so the app feels native.
document.addEventListener("contextmenu", (e) => {
  const t = e.target as HTMLElement;
  if (!t.closest("input, textarea, .selectable")) e.preventDefault();
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <HashRouter>
          <App />
        </HashRouter>
        <Toaster
          theme="dark"
          position="bottom-right"
          toastOptions={{ classNames: { toast: "!bg-raised !border-line-strong !text-fg !text-[13px] !font-sans !rounded-[10px]", description: "!text-muted" } }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
