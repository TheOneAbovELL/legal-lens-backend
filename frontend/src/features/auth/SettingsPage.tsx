import { useEffect, useState } from "react";
import { appConfig } from "@/app/config";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useAuth } from "./AuthProvider";

const THEME_KEY = "legal-lens.theme";

export function applyTheme(theme: string | null): void {
  if (theme === "dark" || theme === "light") document.documentElement.setAttribute("data-theme", theme);
  else document.documentElement.removeAttribute("data-theme");
}

export function SettingsPage() {
  const { user, logout } = useAuth();
  const [theme, setTheme] = useState<string>(() => {
    try {
      return window.localStorage.getItem(THEME_KEY) ?? "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
    applyTheme(theme === "system" ? null : theme);
    try {
      window.localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  return (
    <div className="page">
      <div className="page__inner" style={{ maxWidth: 640 }}>
        <h1>Settings</h1>
        <Card>
          <h2 style={{ fontSize: 15, margin: "0 0 10px" }}>Account</h2>
          <dl className="kv">
            <dt>Username</dt><dd>{user?.username}</dd>
            <dt>Email</dt><dd>{user?.email ?? "–"}</dd>
            <dt>Role</dt><dd>{user?.role}</dd>
          </dl>
          <div style={{ marginTop: 12 }}><Button variant="danger" size="sm" onClick={logout}>Sign out</Button></div>
        </Card>
        <Card>
          <h2 style={{ fontSize: 15, margin: "0 0 10px" }}>Appearance</h2>
          <div className="field">
            <label className="field__label" htmlFor="theme">Theme</label>
            <select id="theme" className="input" value={theme} onChange={(e) => setTheme(e.target.value)} style={{ maxWidth: 240 }}>
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </div>
        </Card>
        <Card>
          <h2 style={{ fontSize: 15, margin: "0 0 10px" }}>About</h2>
          <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 14 }}>
            Legal Lens provides legal information grounded in indexed sources. It is not legal advice and never predicts case
            outcomes. Client build {appConfig.version}.
          </p>
        </Card>
      </div>
    </div>
  );
}
