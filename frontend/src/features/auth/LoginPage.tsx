import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Feedback";
import { describeError } from "@/lib/utils/errors";
import { AuthLayout } from "./AuthLayout";
import { useAuth } from "./AuthProvider";

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
    <AuthLayout title="Sign in" subtitle="Continue your research with your conversations and evidence history.">
      {expiredNotice ? <Notice tone="warn">Your session expired. Please sign in again.</Notice> : null}
      <form onSubmit={onSubmit} noValidate>
        <Input label="Username or email" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
        <Input label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <Button type="submit" variant="primary" size="lg" block loading={busy}>Continue</Button>
      </form>
      <p className="auth__alt">New to Legal Lens? <Link to="/signup">Create an account</Link></p>
    </AuthLayout>
  );
}
