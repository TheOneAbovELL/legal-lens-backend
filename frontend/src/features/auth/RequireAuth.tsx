import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "./AuthProvider";

/** Guards /app: unauthenticated users go to /login and return to the intended route afterwards. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") {
    return (
      <div className="center" aria-busy="true">
        <Spinner label="Checking your session" /> <span>Checking your session…</span>
      </div>
    );
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}
