import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Card";
import { describeError } from "@/lib/utils/errors";
import { useAuth } from "./AuthProvider";
import { AuthBrand } from "./AuthBrand";

export function LoginPage() {
  const { status, login, expiredNotice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/app";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "authenticated") return <Navigate to={from} replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login({ username: username.trim(), password });
      navigate(from, { replace: true });
    } catch (err) {
      setError(describeError(err).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <div className="card auth__card">
        <AuthBrand />
        <p className="auth__sub">Sign in to keep your conversations and evidence history.</p>
        {expiredNotice ? <Alert tone="warning">Your session expired. Please sign in again.</Alert> : null}
        <form onSubmit={onSubmit} noValidate>
          <Input label="Username or email" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          <Input label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          {error ? <Alert tone="danger">{error}</Alert> : null}
          <Button type="submit" variant="primary" block loading={busy}>Sign in</Button>
        </form>
        <p style={{ margin: 0, fontSize: 14, color: "var(--text-muted)" }}>
          New here? <Link to="/signup">Create an account</Link>
        </p>
      </div>
    </main>
  );
}
