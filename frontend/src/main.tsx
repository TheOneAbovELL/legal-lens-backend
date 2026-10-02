import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/app/App";
import { AppProviders } from "@/app/providers";
import { applyTheme } from "@/features/auth/SettingsPage";
import "@/styles/global.css";

try {
  applyTheme(window.localStorage.getItem("legal-lens.theme"));
} catch {
  /* storage unavailable */
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <AppProviders>
      <App />
    </AppProviders>
  </StrictMode>,
);
