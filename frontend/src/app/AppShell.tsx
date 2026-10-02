import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Menu as MenuIcon, MessageSquareText, PanelLeft, Plus, Search, Wrench } from "lucide-react";
import { appConfig } from "@/app/config";
import { Brand } from "@/components/layout/Brand";
import { IconButton } from "@/components/ui/Button";
import { Drawer, Sheet } from "@/components/ui/Overlay";
import { Avatar } from "@/components/ui/Avatar";
import { Menu } from "@/components/ui/Menu";
import { useAuth } from "@/features/auth/AuthProvider";
import { ConversationSidebar } from "@/features/conversations/Sidebar";
import { EvidenceList, EvidencePane, EvidenceTools } from "@/features/evidence/EvidencePanel";
import { EvidenceProvider, useEvidence } from "@/features/evidence/EvidenceContext";
import { BREAKPOINTS, useMediaQuery } from "@/hooks/useMediaQuery";
import { ConnectionLine } from "./ConnectionStatus";
import { LogOut, Settings } from "lucide-react";

const COLLAPSE_KEY = "legal-lens.sidebar";

function TopBar({ onMenu, collapsed, onToggleSidebar }: { onMenu: () => void; collapsed: boolean; onToggleSidebar: () => void }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <header className="topbar">
      <IconButton label="Open conversations" className="topbar__menu" onClick={onMenu}><MenuIcon /></IconButton>
      <IconButton label={collapsed ? "Show sidebar" : "Hide sidebar"} className="topbar__collapse" onClick={onToggleSidebar} aria-pressed={!collapsed}><PanelLeft /></IconButton>
      <Brand />
      <nav className="topbar__nav" aria-label="Primary">
        <NavLink to="/app" end className="navlink"><MessageSquareText /><span>Research</span></NavLink>
        <NavLink to="/app/search" className="navlink"><Search /><span>Search</span></NavLink>
        {appConfig.diagnosticsEnabled ? <NavLink to="/app/diagnostics" className="navlink"><Wrench /><span>Diagnostics</span></NavLink> : null}
      </nav>
      <span className="topbar__spacer" />
      <IconButton label="New research" className="topbar__new" onClick={() => navigate("/app")}><Plus /></IconButton>
      {user ? (
        <Menu
          header={<>{user.username} · {user.role}{user.email ? <><br />{user.email}</> : null}</>}
          trigger={({ toggle, open, id }) => (
            <button type="button" className="btn btn--ghost" aria-haspopup="menu" aria-expanded={open} aria-controls={id} onClick={toggle} aria-label="Account menu">
              <Avatar name={user.username} size={24} />
              <span className="topbar__user-name">{user.username}</span>
            </button>
          )}
          items={[
            { label: "Settings", icon: <Settings />, onSelect: () => navigate("/app/settings") },
            { label: "Sign out", icon: <LogOut />, onSelect: () => { logout(); navigate("/login", { replace: true }); }, danger: true },
          ]}
        />
      ) : null}
    </header>
  );
}

function EvidenceOverlay() {
  const { drawerOpen, setDrawerOpen } = useEvidence();
  const phone = useMediaQuery(BREAKPOINTS.compact);
  const close = useCallback(() => setDrawerOpen(false), [setDrawerOpen]);
  if (phone) {
    return <Sheet open={drawerOpen} title="Evidence" onClose={close} tools={<EvidenceTools />}><EvidenceList /></Sheet>;
  }
  return <Drawer side="right" open={drawerOpen} title="Evidence" onClose={close} tools={<EvidenceTools />}><EvidenceList /></Drawer>;
}

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(COLLAPSE_KEY) === "collapsed";
    } catch {
      return false;
    }
  });
  const location = useLocation();
  const isResearch = location.pathname === "/app" || location.pathname.startsWith("/app/chat");
  useEffect(() => setMenuOpen(false), [location.pathname]);
  const toggleSidebar = () => {
    setCollapsed((c) => {
      try {
        window.localStorage.setItem(COLLAPSE_KEY, c ? "open" : "collapsed");
      } catch {
        /* ignore */
      }
      return !c;
    });
  };
  return (
    <EvidenceProvider>
      <div className={`shell${collapsed ? " shell--collapsed" : ""}`}>
        <TopBar onMenu={() => setMenuOpen(true)} collapsed={collapsed} onToggleSidebar={toggleSidebar} />
        <ConversationSidebar />
        <div className="main">
          <div className="workspace">
            <ConnectionLine />
            <Outlet />
          </div>
          {isResearch ? <EvidencePane /> : null}
        </div>
      </div>
      <Drawer open={menuOpen} title="Conversations" onClose={() => setMenuOpen(false)}>
        <ConversationSidebar onNavigate={() => setMenuOpen(false)} />
      </Drawer>
      <EvidenceOverlay />
    </EvidenceProvider>
  );
}
