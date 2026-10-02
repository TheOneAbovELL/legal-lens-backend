import { useState } from "react";
import { Link } from "react-router-dom";
import { appConfig } from "@/app/config";
import { useBackendStatus } from "@/app/ConnectionStatus";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Field";
import { StatusText } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/features/auth/AuthProvider";
import { applyTheme, clearLocalData, getDefaultProfile, getTheme, setDefaultProfile, type Theme } from "@/lib/preferences";
import type { RetrievalProfile } from "@/types/api";

function Section({ title, desc, children }: { title: string; desc: string; children: React.ReactNode }) {
  return (
    <section className="settings__section" aria-labelledby={`s-${title}`}>
      <div>
        <h2 id={`s-${title}`} className="settings__title">{title}</h2>
        <p className="settings__desc">{desc}</p>
      </div>
      <div className="settings__body">{children}</div>
    </section>
  );
}

export function SettingsPage() {
  const { user, logout } = useAuth();
  const { notify } = useToast();
  const backend = useBackendStatus();
  const [theme, setTheme] = useState<Theme>(getTheme);
  const [profile, setProfile] = useState<RetrievalProfile | "">(() => getDefaultProfile() ?? "");

  const pickTheme = (t: Theme) => {
    setTheme(t);
    applyTheme(t);
  };
  const pickProfile = (p: RetrievalProfile | "") => {
    setProfile(p);
    setDefaultProfile(p || null);
  };
  const health = backend.offline ? "unavailable" : backend.notReady ? "degraded" : backend.loading ? "unknown" : "healthy";

  return (
    <div className="page">
      <div className="page__col page__col--narrow">
        <div className="page__head">
          <h1 className="t-title">Settings</h1>
          <p className="page__lead">Preferences are stored on this device. Nothing here exposes backend configuration.</p>
        </div>

        <Section title="Account" desc="Who you are signed in as.">
          <dl className="kv">
            <dt>Username</dt><dd>{user?.username}</dd>
            <dt>Email</dt><dd>{user?.email ?? "—"}</dd>
            <dt>Role</dt><dd style={{ textTransform: "capitalize" }}>{user?.role}</dd>
          </dl>
          <div><Button variant="secondary" size="sm" onClick={logout}>Sign out</Button></div>
        </Section>

        <Section title="Appearance" desc="Light and dark are designed separately; system follows your OS.">
          <div className="seg" role="group" aria-label="Theme">
            {(["system", "light", "dark"] as Theme[]).map((t) => (
              <button key={t} type="button" className="seg__btn" aria-pressed={theme === t} onClick={() => pickTheme(t)} style={{ textTransform: "capitalize" }}>{t}</button>
            ))}
          </div>
        </Section>

        <Section title="Conversation" desc="Default retrieval depth for new questions. Adaptive lets Legal Lens choose from the question.">
          <Select label="Retrieval depth" value={profile} onChange={(e) => pickProfile(e.target.value as RetrievalProfile | "")}>
            <option value="">Adaptive (recommended)</option>
            <option value="FAST">Fast — single provision look-ups</option>
            <option value="BALANCED">Balanced — comparisons</option>
            <option value="DEEP">Deep — multi-aspect research</option>
          </Select>
        </Section>

        <Section title="Privacy" desc="Signed-in conversations are stored with your account; anonymous requests are never stored.">
          <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--ink-2)" }}>
            Answers are generated only from retrieved sources. Legal Lens does not keep provider prompts, and this device
            stores only your session token and the preferences above.
          </p>
          <div>
            <Button variant="secondary" size="sm" onClick={() => { clearLocalData(); pickTheme("system"); setProfile(""); notify({ tone: "success", title: "Local preferences cleared" }); }}>
              Clear local preferences
            </Button>
          </div>
        </Section>

        {appConfig.diagnosticsEnabled ? (
          <Section title="Developer" desc="Development build only.">
            <div className="row">
              <span className="t-meta">Backend</span>
              <StatusText health={health} />
              <Link to="/app/diagnostics" className="btn btn--secondary btn--sm">Open diagnostics</Link>
            </div>
          </Section>
        ) : null}

        <p className="t-meta">Client build {appConfig.version}. Legal information, not legal advice.</p>
      </div>
    </div>
  );
}
