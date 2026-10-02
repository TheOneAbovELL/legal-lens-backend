import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Spinner } from "@/components/ui/Spinner";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { SettingsPage } from "@/features/auth/SettingsPage";
import { SignupPage } from "@/features/auth/SignupPage";
import { ChatView } from "@/features/chat/ChatView";
import { SourcePage } from "@/features/citations/SourcePage";
import { AppShell } from "./AppShell";
import { NotFoundPage } from "./NotFoundPage";
import { appConfig } from "./config";

// Heavy, rarely used views load on demand.
const SearchPage = lazy(() => import("@/features/search/SearchPage").then((m) => ({ default: m.SearchPage })));
const DiagnosticsPage = lazy(() => import("@/features/diagnostics/DiagnosticsPage").then((m) => ({ default: m.DiagnosticsPage })));

function Loading() {
  return <div className="center" aria-busy="true"><Spinner /></div>;
}

export function App() {
  return (
    <Suspense fallback={<Loading />}>
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
