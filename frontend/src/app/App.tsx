import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Brand } from "@/components/layout/Brand";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { SignupPage } from "@/features/auth/SignupPage";
import { ChatView } from "@/features/chat/ChatView";
import { SourcePage } from "@/features/evidence/SourcePage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { AppShell } from "./AppShell";
import { NotFoundPage } from "./NotFoundPage";
import { appConfig } from "./config";

// Heavier, less frequent views load on demand.
const SearchPage = lazy(() => import("@/features/search/SearchPage").then((m) => ({ default: m.SearchPage })));
const DiagnosticsPage = lazy(() => import("@/features/diagnostics/DiagnosticsPage").then((m) => ({ default: m.DiagnosticsPage })));

export function LoadingScreen({ label = "Loading" }: { label?: string }) {
  return (
    <div className="loading-screen" role="status" aria-live="polite">
      <Brand asLink={false} large />
      <span>{label}…</span>
    </div>
  );
}

export function App() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <Routes>
        <Route path="/" element={<Navigate to="/app" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/app" element={<AppShell />}>
            <Route index element={<ChatView />} />
            <Route path="chat/:conversationId" element={<ChatView />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="sources/:documentId" element={<SourcePage />} />
            <Route path="settings" element={<SettingsPage />} />
            {appConfig.diagnosticsEnabled ? <Route path="diagnostics" element={<DiagnosticsPage />} /> : null}
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
