import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowUp, Square } from "lucide-react";
import { IconButton } from "@/components/ui/Button";
import { getDefaultProfile } from "@/lib/preferences";
import type { RetrievalProfile } from "@/types/api";

interface Props {
  busy: boolean;
  onSend: (text: string, options: { profile: RetrievalProfile | null }) => void;
  onStop: () => void;
  initialText?: string;
  autoFocus?: boolean;
  placeholder?: string;
}

const MAX = 4000;

export function ChatComposer({ busy, onSend, onStop, initialText = "", autoFocus, placeholder }: Props) {
  const [text, setText] = useState(initialText);
  const [profile, setProfile] = useState<RetrievalProfile | "">(() => getDefaultProfile() ?? "");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (initialText) setText(initialText);
  }, [initialText]);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [text]);
  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  const valid = text.trim().length > 0 && text.length <= MAX;
  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!valid || busy) return;
    onSend(text.trim(), { profile: profile || null });
    setText("");
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form className="composer" onSubmit={submit} aria-label="Ask a legal question">
      <div className="composer__inner">
        <div className="composer__box">
          <label htmlFor="composer-input" className="sr-only">Ask a legal question</label>
          <textarea id="composer-input" ref={ref} className="composer__input" rows={1} value={text} maxLength={MAX + 200}
            placeholder={placeholder ?? "Ask a legal question…"} onChange={(e) => setText(e.target.value)} onKeyDown={onKey}
            disabled={busy} data-testid="composer-input" />
          {busy ? (
            <IconButton label="Stop generating" variant="secondary" onClick={onStop}><Square /></IconButton>
          ) : (
            <IconButton label="Send question" variant="primary" type="submit" disabled={!valid} data-testid="send-button"><ArrowUp /></IconButton>
          )}
        </div>
        <div className="composer__meta">
          <span>
            <span className="kbd">Enter</span> to send · <span className="kbd">Shift</span>+<span className="kbd">Enter</span> for a new line
            {text.length > MAX ? ` · too long (${text.length}/${MAX})` : ""}
          </span>
          <label>
            <span className="sr-only">Retrieval depth</span>
            <select className="select" value={profile} onChange={(e) => setProfile(e.target.value as RetrievalProfile | "")} aria-label="Retrieval depth">
              <option value="">Adaptive depth</option>
              <option value="FAST">Fast</option>
              <option value="BALANCED">Balanced</option>
              <option value="DEEP">Deep</option>
            </select>
          </label>
        </div>
      </div>
    </form>
  );
}
