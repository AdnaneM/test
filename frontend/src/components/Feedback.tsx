import type { ReactNode } from "react";
import { useToasts } from "../toast";
import { IconEmpty } from "./Icons";

export function EmptyState({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="empty card">
      <div className="empty-icon">{icon ?? <IconEmpty width={36} height={36} />}</div>
      <p className="empty-title">{title}</p>
      {hint && <p className="empty-hint">{hint}</p>}
    </div>
  );
}

export function ErrorBanner({ message, onRetry, onDemo }: { message: string; onRetry?: () => void; onDemo?: () => void }) {
  return (
    <div className="error card" role="alert">
      <p className="error-title">Impossible de charger les données</p>
      <p className="error-msg">{message}</p>
      <div className="error-actions">
        {onRetry && (
          <button type="button" className="btn btn-primary" onClick={onRetry}>
            Réessayer
          </button>
        )}
        {onDemo && (
          <button type="button" className="btn btn-ghost" onClick={onDemo}>
            Activer le mode démo
          </button>
        )}
      </div>
    </div>
  );
}

export function Skeleton({ rows = 3, height = 150 }: { rows?: number; height?: number }) {
  return (
    <div className="stack" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton card" style={{ height }} />
      ))}
    </div>
  );
}

export function LoadingBar({ active }: { active: boolean }) {
  return <div className={`loading-bar${active ? " is-active" : ""}`} aria-hidden="true" />;
}

export function Toasts() {
  const items = useToasts();
  return (
    <div className="toasts" aria-live="polite" aria-atomic="false">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`}>
          {t.message}
        </div>
      ))}
    </div>
  );
}
