import type { ReactNode } from "react";
import { IconGrid, IconHistory, IconStats } from "./Icons";

export type Tab = "grid" | "history" | "stats";

const TABS: { id: Tab; label: string; icon: ReactNode }[] = [
  { id: "grid", label: "Grille", icon: <IconGrid width={22} height={22} /> },
  { id: "history", label: "Historique", icon: <IconHistory width={22} height={22} /> },
  { id: "stats", label: "Stats", icon: <IconStats width={22} height={22} /> },
];

export function TabBar({ tab, onChange }: { tab: Tab; onChange: (t: Tab) => void }) {
  return (
    <nav className="tabbar" aria-label="Navigation principale">
      <div className="tabbar-inner">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className="tab"
            aria-current={tab === t.id ? "page" : undefined}
            onClick={() => onChange(t.id)}
          >
            {t.icon}
            <span>{t.label}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}
