import { useNavigate } from "react-router-dom";
import { Menu } from "@/components/ui/Menu";
import { useAuth } from "./AuthProvider";

export function AccountMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  const initial = user.username.slice(0, 1).toUpperCase();
  return (
    <Menu
      label="Account menu"
      trigger={
        <span className="row" style={{ gap: 8 }}>
          <span aria-hidden="true" style={{ width: 26, height: 26, borderRadius: "50%", background: "var(--accent)", color: "var(--on-accent)",
            display: "inline-grid", placeItems: "center", fontWeight: 700, fontSize: 13 }}>{initial}</span>
          <span style={{ maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis" }}>{user.username}</span>
        </span>
      }
      header={<span>{user.username} · {user.role}{user.email ? <><br />{user.email}</> : null}</span>}
      items={[
        { label: "Settings", onSelect: () => navigate("/app/settings") },
        { label: "Sign out", onSelect: () => { logout(); navigate("/login", { replace: true }); }, danger: true },
      ]}
    />
  );
}
