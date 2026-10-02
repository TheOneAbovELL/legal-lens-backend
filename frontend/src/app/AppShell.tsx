import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { appConfig } from "@/app/config";
import { Button } from "@/components/ui/Button";
import { Drawer } from "@/components/ui/Dialog";
import { AccountMenu } from "@/features/auth/AccountMenu";
import { BrandMark } from "@/features/auth/AuthBrand";
import { EvidenceList, EvidencePanel } from "@/features/citations/EvidencePanel";
import { EvidenceProvider, useEvidence } from "@/features/citations/EvidenceContext";
import { ConversationSidebar } from "@/features/conversations/Sidebar";
import { ConnectionBadge, ConnectionBanner } from "./ConnectionStatus";

function TopBar({ onMenu }: { onMenu: () => void }) {
  return (
    <header className="topbar">
      <Button variant="ghost" icon aria-label="Open conversations" className="topbar__menu" onClick={onMenu}>☰</Button>
      <Link to="/app" className="brand"><BrandMark /> Legal Lens</Link>
      <nav className="topbar__nav" aria-label="Primary">
        <NavLink to="/app" end className="navlink">Chat</NavLink>
        <NavLink to="/app/search" className="navlink">Search</NavLink>
        {appConfig.diagnosticsEnabled ? <NavLink to="/app/diagnostics" className="navlink">Diagnostics</NavLink> : null}
      </nav>
      <span className="topbar__spacer" />
      <ConnectionBadge />
      <AccountMenu />
    </header>
  );
}

function EvidenceDrawer() {
  const { drawerOpen, setDrawerOpen } = useEvidence();
  return (
    <Drawer open={drawerOpen} title="Sources" onClose={() => setDrawerOpen(false)}>
      <EvidenceList />
    </Drawer>
  );
}

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const isChat = location.pathname === "/app" || location.pathname.startsWith("/app/chat");
  useEffect(() => setMenuOpen(false), [location.pathname]);
  return (
    <EvidenceProvider>
      <div className="shell">
        <TopBar onMenu={() => setMenuOpen(true)} />
        <ConversationSidebar />
        <div className="main">
          <div className="main__content">
            <ConnectionBanner />
            <Outlet />
          </div>
          {isChat ? <EvidencePanel /> : null}
        </div>
      </div>
      <Drawer open={menuOpen} side="left" title="Conversations" onClose={() => setMenuOpen(false)}>
        <ConversationSidebar onNavigate={() => setMenuOpen(false)} />
      </Drawer>
      <EvidenceDrawer />
    </EvidenceProvider>
  );
}
