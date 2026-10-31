import { useEffect, useRef, useState } from "react";
import { createHttpClient, humanError } from "../api";
import { fmtTime } from "../format";
import { normalizeSettings, type Settings } from "../settings";
import { IconClose } from "./Icons";

interface Props {
  settings: Settings;
  onSave: (s: Settings) => void;
  onClose: () => void;
}

type TestState = { kind: "idle" } | { kind: "loading" } | { kind: "ok"; message: string } | { kind: "error"; message: string };

export function SettingsSheet({ settings, onSave, onClose }: Props) {
  const [draft, setDraft] = useState<Settings>(settings);
  const [showKey, setShowKey] = useState(false);
  const [test, setTest] = useState<TestState>({ kind: "idle" });
  const firstField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    firstField.current?.focus({ preventScroll: true });
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  async function testConnection(): Promise<void> {
    setTest({ kind: "loading" });
    try {
      const n = normalizeSettings(draft);
      const h = await createHttpClient({ baseUrl: n.apiBase, apiKey: n.apiKey }).health();
      const when = h.time ? ` · ${fmtTime(h.time)}` : "";
      setTest({ kind: "ok", message: `Connecté · ${h.status} · v${h.version}${when}` });
    } catch (e) {
      setTest({ kind: "error", message: humanError(e) });
    }
  }

  function save(): void {
    onSave(normalizeSettings(draft));
    onClose();
  }

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="settings-title" onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <h2 id="settings-title">Réglages</h2>
          <button type="button" className="icon-btn" aria-label="Fermer" onClick={onClose}>
            <IconClose />
          </button>
        </header>

        <label className="field">
          <span className="field-label">URL de l'API</span>
          <input
            ref={firstField}
            type="url"
            inputMode="url"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            placeholder="Même origine (par défaut)"
            value={draft.apiBase}
            onChange={(e) => setDraft({ ...draft, apiBase: e.target.value })}
          />
          <small>Laisser vide si l'API est servie sur le même domaine (/api). Exemple : https://edgebet.exemple.fr</small>
        </label>

        <label className="field">
          <span className="field-label">Clé API</span>
          <div className="input-row">
            <input
              type={showKey ? "text" : "password"}
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              placeholder="Optionnelle en lecture"
              value={draft.apiKey}
              onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
            />
            <button type="button" className="btn btn-text" onClick={() => setShowKey((s) => !s)}>
              {showKey ? "Masquer" : "Afficher"}
            </button>
          </div>
          <small>Envoyée dans l'en-tête X-API-Key pour marquer les paris (joué / passé).</small>
        </label>

        <div className="field switch-row">
          <div>
            <span className="field-label">Mode démo</span>
            <small>Données fictives intégrées, sans backend. Les actions restent en mémoire.</small>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={draft.demo}
            aria-label="Mode démo"
            className={`switch${draft.demo ? " on" : ""}`}
            onClick={() => setDraft({ ...draft, demo: !draft.demo })}
          >
            <span className="knob" />
          </button>
        </div>

        <div className="test-row">
          <button type="button" className="btn btn-ghost" onClick={testConnection} disabled={test.kind === "loading"}>
            {test.kind === "loading" ? "Test en cours…" : "Tester la connexion"}
          </button>
          {test.kind === "ok" && <span className="test-result pos">{test.message}</span>}
          {test.kind === "error" && <span className="test-result neg">{test.message}</span>}
        </div>

        <footer className="sheet-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Annuler
          </button>
          <button type="button" className="btn btn-primary" onClick={save}>
            Enregistrer
          </button>
        </footer>
      </div>
    </div>
  );
}
