import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { CheckCircle2, Info, OctagonAlert, X } from "lucide-react";
import { IconButton } from "./Button";

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
    setToasts((list) => [...list.slice(-2), { ...toast, id }]);
    window.setTimeout(() => dismiss(id), toast.tone === "danger" ? 7000 : 3200);
  }, [dismiss]);
  const api = useMemo(() => ({ notify }), [notify]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region" aria-live="polite" aria-relevant="additions">
        {toasts.map((t) => {
          const Icon = t.tone === "danger" ? OctagonAlert : t.tone === "success" ? CheckCircle2 : Info;
          return (
            <div key={t.id} className={`toast toast--${t.tone}`} role={t.tone === "danger" ? "alert" : "status"}>
              <Icon aria-hidden="true" />
              <div className="toast__body">
                <div>{t.title}</div>
                {t.message ? <div className="toast__msg">{t.message}</div> : null}
              </div>
              <IconButton label="Dismiss notification" size="sm" onClick={() => dismiss(t.id)}><X /></IconButton>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
