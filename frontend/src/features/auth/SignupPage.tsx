import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Feedback";
import { describeError } from "@/lib/utils/errors";
import type { UserRole } from "@/types/api";
import { AuthLayout } from "./AuthLayout";
import { useAuth } from "./AuthProvider";

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
    <AuthLayout title="Create your account" subtitle="Your conversations and their evidence stay private to you.">
      <form onSubmit={onSubmit} noValidate>
        <Input label="Username" autoComplete="username" value={values.username} error={errors.username}
          onChange={(e) => setValues({ ...values, username: e.target.value })} required autoFocus />
        <Input label="Email (optional)" type="email" autoComplete="email" value={values.email} error={errors.email}
          onChange={(e) => setValues({ ...values, email: e.target.value })} />
        <Input label="Password" type="password" autoComplete="new-password" value={values.password} error={errors.password}
          hint="At least 8 characters, mixing letters with digits or symbols." onChange={(e) => setValues({ ...values, password: e.target.value })} required />
        <Select id="signup-role" label="I am a" value={values.role} onChange={(e) => setValues({ ...values, role: e.target.value as UserRole })}>
          <option value="citizen">Citizen</option>
          <option value="advocate">Advocate</option>
          <option value="researcher">Researcher</option>
        </Select>
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <Button type="submit" variant="primary" size="lg" block loading={busy}>Create account</Button>
      </form>
      <p className="auth__alt">Already registered? <Link to="/login">Sign in</Link></p>
    </AuthLayout>
  );
}
