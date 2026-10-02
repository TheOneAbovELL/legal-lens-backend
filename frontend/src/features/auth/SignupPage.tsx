import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Card";
import { describeError } from "@/lib/utils/errors";
import type { UserRole } from "@/types/api";
import { useAuth } from "./AuthProvider";
import { AuthBrand } from "./AuthBrand";

const USERNAME = /^[A-Za-z0-9_.-]{3,64}$/;
const EMAIL = /^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$/;

export function validateSignup(values: { username: string; email: string; password: string }): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!USERNAME.test(values.username)) errors.username = "3–64 characters: letters, digits, dot, dash or underscore.";
  if (values.email && !EMAIL.test(values.email)) errors.email = "Enter a valid email address.";
  const bytes = new TextEncoder().encode(values.password).length;
  if (values.password.length < 8 || bytes > 72) errors.password = "8–72 characters.";
  else if (/^\d+$/.test(values.password) || /^[A-Za-z]+$/.test(values.password)) errors.password = "Mix letters with digits or symbols.";
  return errors;
}

export function SignupPage() {
  const { status, signup } = useAuth();
  const navigate = useNavigate();
  const [values, setValues] = useState({ username: "", email: "", password: "", role: "citizen" as UserRole });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "authenticated") return <Navigate to="/app" replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const found = validateSignup(values);
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    setError(null);
    try {
      await signup({ username: values.username, email: values.email || null, password: values.password, role: values.role });
      navigate("/app", { replace: true });
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
        <p className="auth__sub">Create an account. Your conversations stay private to you.</p>
        <form onSubmit={onSubmit} noValidate>
          <Input label="Username" autoComplete="username" value={values.username} error={errors.username}
            onChange={(e) => setValues({ ...values, username: e.target.value })} required />
          <Input label="Email (optional)" type="email" autoComplete="email" value={values.email} error={errors.email}
            onChange={(e) => setValues({ ...values, email: e.target.value })} />
          <Input label="Password" type="password" autoComplete="new-password" value={values.password} error={errors.password}
            onChange={(e) => setValues({ ...values, password: e.target.value })} required />
          <div className="field">
            <label className="field__label" htmlFor="signup-role">I am a</label>
            <select id="signup-role" className="input" value={values.role} onChange={(e) => setValues({ ...values, role: e.target.value as UserRole })}>
              <option value="citizen">Citizen</option>
              <option value="advocate">Advocate</option>
              <option value="researcher">Researcher</option>
            </select>
          </div>
          {error ? <Alert tone="danger">{error}</Alert> : null}
          <Button type="submit" variant="primary" block loading={busy}>Create account</Button>
        </form>
        <p style={{ margin: 0, fontSize: 14, color: "var(--text-muted)" }}>
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </main>
  );
}
