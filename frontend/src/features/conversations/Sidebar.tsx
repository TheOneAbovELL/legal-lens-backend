import { useMemo, useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { Info, LogOut, MoreHorizontal, Pencil, Plus, Search, Settings, Trash2 } from "lucide-react";
import { Button, IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Overlay";
import { Input } from "@/components/ui/Field";
import { Menu } from "@/components/ui/Menu";
import { Skeleton } from "@/components/ui/Feedback";
import { Avatar } from "@/components/ui/Avatar";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/features/auth/AuthProvider";
import { describeError } from "@/lib/utils/errors";
import { relativeTime } from "@/lib/utils/format";
import type { ConversationOut } from "@/types/api";
import { useConversationList, useConversationMutations } from "./useConversations";

export type GroupKey = "Today" | "Yesterday" | "Previous 7 days" | "Older";

/** Group conversations by their last activity, most recent first inside each group. */
export function groupConversations(list: ConversationOut[], now: number = Date.now()): { key: GroupKey; items: ConversationOut[] }[] {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const today = start.getTime();
  const day = 86_400_000;
  const groups: Record<GroupKey, ConversationOut[]> = { Today: [], Yesterday: [], "Previous 7 days": [], Older: [] };
  for (const c of list) {
    const t = new Date(c.updated_at).getTime();
    const key: GroupKey = t >= today ? "Today" : t >= today - day ? "Yesterday" : t >= today - 7 * day ? "Previous 7 days" : "Older";
    groups[key].push(c);
  }
  return (Object.keys(groups) as GroupKey[]).map((key) => ({ key, items: groups[key] })).filter((g) => g.items.length > 0);
}

export function ConversationSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const list = useConversationList();
  const { rename, remove } = useConversationMutations();
  const { notify } = useToast();
  const { user, logout } = useAuth();
  const [query, setQuery] = useState("");
  const [renaming, setRenaming] = useState<ConversationOut | null>(null);
  const [deleting, setDeleting] = useState<ConversationOut | null>(null);
  const [about, setAbout] = useState(false);
  const [title, setTitle] = useState("");

  const go = (path: string) => {
    navigate(path);
    onNavigate?.();
  };
  const filtered = useMemo(() => {
    const items = list.data?.conversations ?? [];
    const q = query.trim().toLowerCase();
    return q ? items.filter((c) => c.title.toLowerCase().includes(q)) : items;
  }, [list.data, query]);
  const groups = useMemo(() => groupConversations(filtered), [filtered]);

  const submitRename = async () => {
    if (!renaming || !title.trim()) return;
    try {
      await rename.mutateAsync({ id: renaming.id, title: title.trim() });
      setRenaming(null);
    } catch (error) {
      notify({ tone: "danger", title: "Rename failed", message: describeError(error).message });
    }
  };
  const submitDelete = async () => {
    if (!deleting) return;
    try {
      await remove.mutateAsync(deleting.id);
      if (conversationId === deleting.id) go("/app");
      setDeleting(null);
    } catch (error) {
      notify({ tone: "danger", title: "Delete failed", message: describeError(error).message });
    }
  };

  return (
    <nav className="sidebar" aria-label="Conversations">
      <div className="sb__top">
        <Button variant="primary" block icon={<Plus />} onClick={() => go("/app")}>New research</Button>
        <div className="sb__search">
          <Search aria-hidden="true" />
          <label htmlFor="sb-search" className="sr-only">Search conversations</label>
          <input id="sb-search" className="input" placeholder="Search conversations" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      </div>

      <div className="sb__list">
        {list.isPending ? (
          <div style={{ padding: 12 }}><Skeleton lines={4} /></div>
        ) : list.isError ? (
          <div className="sb__empty" role="status">
            History is unavailable right now.
            <div style={{ marginTop: 8 }}><Button variant="secondary" size="sm" onClick={() => list.refetch()}>Retry</Button></div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="sb__empty">{query ? "No conversations match." : "No conversations yet. Your research will appear here."}</div>
        ) : (
          groups.map((group) => (
            <div key={group.key}>
              <div className="t-section sb__group">{group.key}</div>
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {group.items.map((c) => {
                  const active = c.id === conversationId;
                  return (
                    <li key={c.id} className={`conv${active ? " conv--active" : ""}`}>
                      <NavLink to={`/app/chat/${c.id}`} className="conv__link" onClick={onNavigate} aria-current={active ? "page" : undefined}>
                        <span className="conv__title">{c.title}</span>
                        <span className="conv__meta">{relativeTime(c.updated_at)}</span>
                      </NavLink>
                      <div className="conv__menu">
                        <Menu
                          trigger={({ toggle, open, id }) => (
                            <IconButton label={`Options for ${c.title}`} size="sm" aria-haspopup="menu" aria-expanded={open} aria-controls={id} onClick={toggle}>
                              <MoreHorizontal />
                            </IconButton>
                          )}
                          items={[
                            { label: "Rename", icon: <Pencil />, onSelect: () => { setRenaming(c); setTitle(c.title); } },
                            { label: "Delete", icon: <Trash2 />, onSelect: () => setDeleting(c), danger: true },
                          ]}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        )}
      </div>

      <div className="sb__foot">
        <NavLink to="/app/settings" className="navlink" onClick={onNavigate}><Settings /><span>Settings</span></NavLink>
        <button type="button" className="navlink" onClick={() => setAbout(true)}><Info /><span>About Legal Lens</span></button>
        {user ? (
          <Menu
            align="left"
            header={<>{user.username} · {user.role}{user.email ? <><br />{user.email}</> : null}</>}
            trigger={({ toggle, open, id }) => (
              <button type="button" className="sb__user" aria-haspopup="menu" aria-expanded={open} aria-controls={id} onClick={toggle} aria-label="Account menu">
                <Avatar name={user.username} size={24} />
                <span className="sb__user-name">{user.username}</span>
              </button>
            )}
            items={[
              { label: "Settings", icon: <Settings />, onSelect: () => go("/app/settings") },
              { label: "Sign out", icon: <LogOut />, onSelect: () => { logout(); navigate("/login", { replace: true }); }, danger: true },
            ]}
          />
        ) : null}
      </div>

      <Dialog open={Boolean(renaming)} title="Rename conversation" onClose={() => setRenaming(null)}
        actions={<><Button variant="secondary" onClick={() => setRenaming(null)}>Cancel</Button><Button variant="primary" onClick={submitRename} loading={rename.isPending}>Save</Button></>}>
        <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void submitRename(); } }} />
      </Dialog>
      <Dialog open={Boolean(deleting)} title="Delete this conversation?" onClose={() => setDeleting(null)}
        actions={<><Button variant="secondary" onClick={() => setDeleting(null)}>Cancel</Button><Button variant="danger" onClick={submitDelete} loading={remove.isPending}>Delete</Button></>}>
        <p style={{ margin: 0 }}>“{deleting?.title}” and its messages will be permanently removed.</p>
      </Dialog>
      <Dialog open={about} title="About Legal Lens" onClose={() => setAbout(false)}
        actions={<Button variant="primary" onClick={() => setAbout(false)}>Close</Button>}>
        <p style={{ marginTop: 0 }}>Legal Lens answers questions about Indian law from retrieved, cited sources. Every claim in an
          answer points to a passage you can open and read.</p>
        <p style={{ margin: 0 }}>It provides legal information for research and education — not legal advice, and never a prediction
          of how a case will be decided.</p>
      </Dialog>
    </nav>
  );
}
