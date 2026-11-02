import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { AuthProvider } from "./lib/auth";
import { registerSW } from "./lib/push";

try {
  const t = localStorage.getItem("sportai.theme");
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
} catch { /* almacenamiento no disponible */ }

const qc = new QueryClient({
  defaultOptions: { queries: { retry: (n, err: any) => err?.status !== 401 && err?.status !== 403 && err?.status !== 404 && n < 3, refetchOnWindowFocus: true, staleTime: 15_000 } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthProvider><App /></AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);

if (import.meta.env.PROD) registerSW();
