import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

export interface Toast {
  id: number;
  tone: "info" | "success" | "danger";
  title: string;
  message?: string;
}

interface ToastApi {
  notify: (toast: Omit<Toast, "id">) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);
  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((t) => t.id !== id)), []);
  const notify = useCallback((toast: Omit<Toast, "id">) => {
    const id = ++counter.current;
    setToasts((list) => [...list.slice(-3), { ...toast, id }]);
    window.setTimeout(() => dismiss(id), toast.tone === "danger" ? 8000 : 4000);
  }, [dismiss]);
  const api = useMemo(() => ({ notify }), [notify]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region" aria-live="polite" aria-relevant="additions">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.tone}`} role={t.tone === "danger" ? "alert" : "status"}>
            <div style={{ flex: 1 }}>
              <strong>{t.title}</strong>
              {t.message ? <div style={{ fontSize: 14, color: "var(--text-muted)" }}>{t.message}</div> : null}
            </div>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => dismiss(t.id)} aria-label="Dismiss notification">✕</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
