import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, MemoryRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { DEMO, tokens } from "./lib/api";
import { AuthProvider } from "./lib/auth";
import { registerSW } from "./lib/push";

try {
  const t = localStorage.getItem("sportai.theme");
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
} catch { /* almacenamiento no disponible */ }

// En la demo (página estática) no hay URL propia: la navegación vive en memoria.
const Router = DEMO ? MemoryRouter : BrowserRouter;
if (DEMO && !tokens.access) tokens.set("demo", "demo");

const qc = new QueryClient({
  defaultOptions: { queries: { retry: (n, err: any) => err?.status !== 401 && err?.status !== 403 && err?.status !== 404 && n < 3, refetchOnWindowFocus: true, staleTime: 15_000 } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <Router>
        <AuthProvider><App /></AuthProvider>
      </Router>
    </QueryClientProvider>
  </React.StrictMode>,
);

if (import.meta.env.PROD && !DEMO) registerSW();
