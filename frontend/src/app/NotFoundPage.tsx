import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <main className="center">
      <h1 style={{ fontSize: 22 }}>Page not found</h1>
      <p>The page you asked for does not exist.</p>
      <Link className="btn btn--primary" to="/app">Go to Legal Lens</Link>
    </main>
  );
}
