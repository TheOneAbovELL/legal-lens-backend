import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { Citation } from "@/types/api";

export interface SelectedCitation {
  messageId: string;
  citation: Citation;
}

interface EvidenceState {
  /** Citations of the message currently shown in the evidence panel. */
  citations: Citation[];
  messageId: string | null;
  question: string | null;
  selected: SelectedCitation | null;
  drawerOpen: boolean;
  show: (messageId: string, citations: Citation[], question: string | null) => void;
  select: (messageId: string, citation: Citation, openDrawer?: boolean) => void;
  /** Move the selection within the current message's citations; wraps around. */
  step: (delta: 1 | -1) => void;
  clear: () => void;
  setDrawerOpen: (open: boolean) => void;
}

const EvidenceCtx = createContext<EvidenceState | null>(null);

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [citations, setCitations] = useState<Citation[]>([]);
  const [messageId, setMessageId] = useState<string | null>(null);
  const [question, setQuestion] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedCitation | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const show = useCallback((id: string, list: Citation[], q: string | null) => {
    setMessageId(id);
    setCitations(list);
    setQuestion(q);
    setSelected((s) => (s && s.messageId === id ? s : null));
  }, []);
  const select = useCallback((id: string, citation: Citation, openDrawer = false) => {
    setSelected({ messageId: id, citation });
    if (openDrawer) setDrawerOpen(true);
  }, []);
  const step = useCallback((delta: 1 | -1) => {
    setSelected((s) => {
      if (!messageId || citations.length === 0) return s;
      const idx = s ? citations.findIndex((c) => c.citation_id === s.citation.citation_id) : -1;
      const next = ((idx < 0 ? (delta > 0 ? 0 : citations.length - 1) : idx + delta) + citations.length) % citations.length;
      return { messageId, citation: citations[next]! };
    });
  }, [citations, messageId]);
  const clear = useCallback(() => {
    setCitations([]);
    setMessageId(null);
    setQuestion(null);
    setSelected(null);
  }, []);

  const value = useMemo<EvidenceState>(() => ({ citations, messageId, question, selected, drawerOpen, show, select, step, clear, setDrawerOpen }),
    [citations, messageId, question, selected, drawerOpen, show, select, step, clear]);
  return <EvidenceCtx.Provider value={value}>{children}</EvidenceCtx.Provider>;
}

export function useEvidence(): EvidenceState {
  const ctx = useContext(EvidenceCtx);
  if (!ctx) throw new Error("useEvidence must be used inside EvidenceProvider");
  return ctx;
}
