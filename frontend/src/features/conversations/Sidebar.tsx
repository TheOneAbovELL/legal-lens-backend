import { useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Field";
import { Menu } from "@/components/ui/Menu";
import { Skeleton } from "@/components/ui/Card";
import { useToast } from "@/components/ui/Toast";
import { describeError } from "@/lib/utils/errors";
import { relativeTime } from "@/lib/utils/format";
import type { ConversationOut } from "@/types/api";
import { useConversationList, useConversationMutations } from "./useConversations";

export function ConversationSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const list = useConversationList();
  const { rename, remove } = useConversationMutations();
  const { notify } = useToast();
  const [renaming, setRenaming] = useState<ConversationOut | null>(null);
  const [deleting, setDeleting] = useState<ConversationOut | null>(null);
  const [title, setTitle] = useState("");

  const go = (path: string) => {
    navigate(path);
    onNavigate?.();
  };

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
      <div className="sidebar__head">
        <Button variant="primary" block onClick={() => go("/app")}>+ New chat</Button>
      </div>
      <div className="sidebar__section">Recent</div>
      {list.isPending ? (
        <div style={{ padding: 12 }}><Skeleton lines={4} /></div>
      ) : list.isError ? (
        <div className="sidebar__empty" role="status">
          Conversation history is temporarily unavailable.
          <div style={{ marginTop: 8 }}><Button size="sm" onClick={() => list.refetch()}>Retry</Button></div>
        </div>
      ) : list.data.conversations.length === 0 ? (
        <div className="sidebar__empty">Your conversations will appear here.</div>
      ) : (
        <ul className="sidebar__list">
          {list.data.conversations.map((c) => (
            <li key={c.id} className={`conv${c.id === conversationId ? " conv--active" : ""}`}>
              <NavLink to={`/app/chat/${c.id}`} className="conv__link" onClick={onNavigate} aria-current={c.id === conversationId ? "page" : undefined}>
                <span className="conv__title">{c.title}</span>
                <span className="conv__date">{relativeTime(c.updated_at)}</span>
              </NavLink>
              <div className="conv__menu">
                <Menu label={`Options for ${c.title}`} trigger="⋯" items={[
                  { label: "Rename", onSelect: () => { setRenaming(c); setTitle(c.title); } },
                  { label: "Delete", onSelect: () => setDeleting(c), danger: true },
                ]} />
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="sidebar__foot">Legal information, not legal advice.</div>

      <Dialog open={Boolean(renaming)} title="Rename conversation" onClose={() => setRenaming(null)}
        actions={<><Button onClick={() => setRenaming(null)}>Cancel</Button><Button variant="primary" onClick={submitRename} loading={rename.isPending}>Save</Button></>}>
        <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void submitRename(); } }} />
      </Dialog>
      <Dialog open={Boolean(deleting)} title="Delete conversation?" onClose={() => setDeleting(null)}
        actions={<><Button onClick={() => setDeleting(null)}>Cancel</Button><Button variant="danger" onClick={submitDelete} loading={remove.isPending}>Delete</Button></>}>
        <p style={{ margin: 0 }}>“{deleting?.title}” and its messages will be permanently deleted.</p>
      </Dialog>
    </nav>
  );
}
