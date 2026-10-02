import { Navigate, Outlet, useLocation } from "react-router-dom";
import { LoadingScreen } from "@/app/App";
import { useAuth } from "./AuthProvider";

/** Guards /app: unauthenticated users go to /login and return to the intended route afterwards. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <LoadingScreen label="Checking your session" />;
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}
