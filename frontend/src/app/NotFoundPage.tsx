import { Link } from "react-router-dom";
import { Brand } from "@/components/layout/Brand";

export function NotFoundPage() {
  return (
    <main className="center" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, minHeight: "100%", justifyContent: "center" }}>
      <Brand asLink={false} />
      <h1>Page not found</h1>
      <p style={{ margin: 0 }}>The page you asked for does not exist.</p>
      <Link className="btn btn--primary" to="/app">Go to Legal Lens</Link>
    </main>
  );
}
