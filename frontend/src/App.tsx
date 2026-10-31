import { useCallback, useMemo, useState } from "react";
import { createHttpClient, type ApiClient } from "./api";
import { Toasts } from "./components/Feedback";
import { GridView } from "./components/GridView";
import { HistoryView } from "./components/HistoryView";
import { IconGear, IconLogo } from "./components/Icons";
import { SettingsSheet } from "./components/SettingsSheet";
import { StatsView } from "./components/StatsView";
import { TabBar, type Tab } from "./components/TabBar";
import { createMockClient } from "./mock";
import { useSettings, type Settings } from "./settings";
import { toast } from "./toast";

function createClient(s: Settings): ApiClient {
  return s.demo ? createMockClient() : createHttpClient({ baseUrl: s.apiBase, apiKey: s.apiKey });
}

export default function App() {
  const [settings, setSettings] = useSettings();
  const client = useMemo(() => createClient(settings), [settings]);
  const [tab, setTab] = useState<Tab>("grid");
  const [visited, setVisited] = useState<Record<Tab, boolean>>({ grid: true, history: false, stats: false });
  const [sheetOpen, setSheetOpen] = useState(false);

  function changeTab(t: Tab): void {
    setTab(t);
    setVisited((v) => (v[t] ? v : { ...v, [t]: true }));
    window.scrollTo({ top: 0 });
  }

  const enableDemo = useCallback(() => {
    setSettings({ ...settings, demo: true });
    toast("Mode démo activé : données fictives.", "success");
  }, [settings, setSettings]);

  const closeSheet = useCallback(() => setSheetOpen(false), []);

  const viewProps = { client, demo: settings.demo, onEnableDemo: enableDemo };

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <IconLogo />
            <span>EdgeBet</span>
            {settings.demo && <span className="pill">Démo</span>}
          </div>
          <button type="button" className="icon-btn" aria-label="Réglages" onClick={() => setSheetOpen(true)}>
            <IconGear width={22} height={22} />
          </button>
        </div>
      </header>

      <main className="app">
        <div hidden={tab !== "grid"}>
          <GridView {...viewProps} />
        </div>
        {visited.history && (
          <div hidden={tab !== "history"}>
            <HistoryView {...viewProps} />
          </div>
        )}
        {visited.stats && (
          <div hidden={tab !== "stats"}>
            <StatsView {...viewProps} />
          </div>
        )}
      </main>

      <TabBar tab={tab} onChange={changeTab} />

      {sheetOpen && (
        <SettingsSheet
          settings={settings}
          onSave={(s) => {
            setSettings(s);
            toast("Réglages enregistrés.", "success");
          }}
          onClose={closeSheet}
        />
      )}
      <Toasts />
    </>
  );
}
