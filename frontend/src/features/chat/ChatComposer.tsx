import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/Button";
import type { RetrievalProfile } from "@/types/api";

interface Props {
  busy: boolean;
  onSend: (text: string, options: { profile: RetrievalProfile | null }) => void;
  onStop: () => void;
  initialText?: string;
  autoFocus?: boolean;
}

const MAX = 4000;

export function ChatComposer({ busy, onSend, onStop, initialText = "", autoFocus }: Props) {
  const [text, setText] = useState(initialText);
  const [profile, setProfile] = useState<RetrievalProfile | "">("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (initialText) setText(initialText);
  }, [initialText]);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
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
          <label htmlFor="composer-input" className="visually-hidden">Ask a legal question</label>
          <textarea id="composer-input" ref={ref} className="composer__input" rows={1} value={text} maxLength={MAX + 200}
            placeholder="Ask a legal question about Indian law…" onChange={(e) => setText(e.target.value)} onKeyDown={onKey}
            disabled={busy} data-testid="composer-input" />
          {busy ? (
            <Button variant="danger" size="sm" onClick={onStop} aria-label="Stop generating">Stop</Button>
          ) : (
            <Button type="submit" variant="primary" size="sm" disabled={!valid} aria-label="Send question" data-testid="send-button">Send</Button>
          )}
        </div>
        <div className="composer__hint">
          <span>Enter to send · Shift+Enter for a new line{text.length > MAX ? ` · too long (${text.length}/${MAX})` : ""}</span>
          <label>
            <span className="visually-hidden">Retrieval profile</span>
            <select value={profile} onChange={(e) => setProfile(e.target.value as RetrievalProfile | "")} className="input" style={{ padding: "2px 6px", fontSize: 12, width: "auto" }} aria-label="Retrieval profile">
              <option value="">Adaptive routing</option>
              <option value="FAST">FAST</option>
              <option value="BALANCED">BALANCED</option>
              <option value="DEEP">DEEP</option>
            </select>
          </label>
        </div>
      </div>
    </form>
  );
}
